import base64
import logging
import os
import re
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.authentication import CustomJWTAuthentication
from .models import ChatMessage, ChatThread, SuratRequest, SuratStatus
from .services.email_service import send_surat_via_gmail_admin
from .services.manual_handlers import resolve_official_approver
from .services.pdf_generator_safe import generate_and_save_official_pdf, clean_letter_body_text
from .services.signature_storage import resolve_signature_path_and_uri, humanize_jabatan, clean_fakultas_name

logger = logging.getLogger(__name__)


def _is_custom_surat(surat_req: SuratRequest) -> bool:
    kode = str(getattr(getattr(surat_req, "kode_surat", None), "kode_surat", "") or "")
    return kode.upper().startswith("CUSTOM")


def _user_owns_surat(user, surat_req: SuratRequest) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    student_user_id = getattr(getattr(surat_req, "student", None), "user_id", None)
    return student_user_id is not None and student_user_id == user.pk


def _user_can_view_surat(user, surat_req: SuratRequest) -> bool:
    if _user_owns_surat(user, surat_req):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if hasattr(user, "lecturer_profile") and not _is_custom_surat(surat_req):
        return True
    return False


def _resolve_signer(surat_req: SuratRequest):
    """(nama, nip, jabatan) penandatangan: override payload -> dosen yang meng-ACC -> pejabat resmi mahasiswa."""
    payload = surat_req.payload_data or {}
    lec = None
    approved = surat_req.approvals.filter(status="APPROVED").select_related("approver__user").order_by("-step_order").first()
    if approved:
        lec = approved.approver
    if lec is None:
        st = surat_req.student
        kode = getattr(getattr(surat_req, "kode_surat", None), "kode_surat", None)
        lec = resolve_official_approver(st, kode)
    user = getattr(lec, "user", None)
    jab = (getattr(lec, "jabatan_struktural", None) or [""])[0] if lec else ""
    return (
        surat_req.signer_nama_override or payload.get("_signer_nama") or getattr(user, "nama", "") or "Pejabat Penandatangan",
        surat_req.signer_nip_override or payload.get("_signer_nip") or getattr(user, "nip_nim", "") or "-",
        payload.get("_signer_jabatan") or jab,
    )


def _build_official_a4_html(surat_req: SuratRequest) -> str:
    student = surat_req.student
    prodi_nama = getattr(getattr(student, "prodi", None), "nama_prodi", None) or "Teknik Informatika"
    fakultas_nama = clean_fakultas_name(getattr(getattr(student, "fakultas", None), "nama_fakultas", None) or "Sains dan Teknologi")
    semester_mhs = getattr(student, "semester_aktif", "-")
    tahun_akademik = getattr(student, "tahun_akademik", "-")
    nomor_resmi = surat_req.nomor_surat_resmi or f"{surat_req.id:03d}/{surat_req.kode_surat.kode_surat}/FT/2026"
    payload = surat_req.payload_data or {}
    nama_surat = str(payload.get("judul_surat") or surat_req.kode_surat.nama_surat or "SURAT KETERANGAN RESMI")
    raw_isi = (
        (surat_req.final_approved_content or "").strip()
        or (surat_req.ai_original_draft or "").strip()
        or f"Dengan ini menerangkan bahwa {student.user.nama} (NIM {student.nim}) mengajukan {nama_surat}."
    )
    isi_html = clean_letter_body_text(raw_isi)
    paragraphs_html = "".join(
        f"<p style='text-align: justify; text-indent: 28px; margin: 0 0 10px 0; line-height: 1.55;'>{p.strip()}</p>"
        for p in isi_html.splitlines()
        if p.strip()
    ) or f"<p style='text-align: justify;'>{isi_html}</p>"
    tanggal_surat = timezone.now().strftime("%d %B %Y")
    qr_url = surat_req.qr_verification_code or nomor_resmi
    from .services.pdf_generator_safe import _build_qr_img_html
    qr_img_html = _build_qr_img_html(qr_url)
    qr_token = str(qr_url).rstrip("/").split("/")[-1][:8].upper()
    signer_nama, signer_nip, signer_jabatan = _resolve_signer(surat_req)
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: A4 portrait; margin: 18mm 20mm; }}
  html, body {{
    width: 210mm;
    min-height: 297mm;
    margin: 0 auto;
    padding: 16mm 18mm;
    box-sizing: border-box;
    font-family: 'Times New Roman', Times, serif;
    font-size: 11.5pt;
    line-height: 1.5;
    color: #000000;
    background: #ffffff;
  }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ vertical-align: top; }}
</style>
</head>
<body>
  <div style="text-align: center; border-bottom: 3px double #000; padding-bottom: 8px; margin-bottom: 16px;">
    <div style="font-size: 12pt; font-weight: bold;">KEMENTERIAN AGAMA REPUBLIK INDONESIA</div>
    <div style="font-size: 13.5pt; font-weight: bold;">UNIVERSITAS ISLAM NEGERI SUNAN KALIJAGA</div>
    <div style="font-size: 12pt; font-weight: bold;">FAKULTAS {fakultas_nama.upper()}</div>
    <div style="font-size: 9pt;">Jl. Marsda Adisucipto Yogyakarta 55281 | Laman: www.uin-suka.ac.id</div>
  </div>
  <div style="text-align: center; margin: 14px 0 18px 0;">
    <div style="font-size: 12.5pt; font-weight: bold; text-decoration: underline; text-transform: uppercase;">{nama_surat}</div>
    <div style="font-size: 11pt; margin-top: 2px;">Nomor: {nomor_resmi}</div>
  </div>
  <p style="margin: 0 0 6px 0;">Yang bertanda tangan di bawah ini:</p>
  <table style="margin-bottom: 12px;">
    <tr><td style="width: 155px; padding: 2px 0;">Nama</td><td style="width: 14px;">:</td><td><b>{signer_nama}</b></td></tr>
    <tr><td style="padding: 2px 0;">NIP</td><td>:</td><td>{signer_nip}</td></tr>
    <tr><td style="padding: 2px 0;">Jabatan</td><td>:</td><td>{humanize_jabatan(signer_jabatan, fakultas_nama)}</td></tr>
    <tr><td style="padding: 2px 0;">Instansi</td><td>:</td><td>UIN Sunan Kalijaga Yogyakarta</td></tr>
  </table>
  <p style="margin: 0 0 6px 0;">Dengan ini menerangkan bahwa:</p>
  <table style="margin-bottom: 14px;">
    <tr><td style="width: 155px; padding: 2px 0;">Nama Mahasiswa</td><td style="width: 14px;">:</td><td><b>{student.user.nama}</b></td></tr>
    <tr><td style="padding: 2px 0;">NIM</td><td>:</td><td>{student.nim}</td></tr>
    <tr><td style="padding: 2px 0;">Program Studi</td><td>:</td><td>{prodi_nama}</td></tr>
    <tr><td style="padding: 2px 0;">Fakultas</td><td>:</td><td>{fakultas_nama}</td></tr>
    <tr><td style="padding: 2px 0;">Semester / T.A.</td><td>:</td><td>{semester_mhs} / {tahun_akademik}</td></tr>
  </table>
  <div style="margin-top: 8px;">{paragraphs_html}</div>
  <p style="margin: 12px 0 22px 0; text-indent: 28px; text-align: justify;">
    Demikian surat ini dibuat dengan sebenarnya untuk dapat dipergunakan sebagaimana mestinya.
  </p>
  <table style="margin-top: 10px;">
    <tr>
      <td style="width: 48%; padding-right: 16px; vertical-align: bottom;">
        <div style="font-size: 7.5pt; color: #333;">
          {qr_img_html}<br/>
          <b>Ditandatangani secara elektronik (ASURA)</b><br/>
          Pindai QR untuk memeriksa keaslian.<br/>
          Kode: {qr_token}
        </div>
      </td>
      <td style="width: 52%; padding-left: 24px; text-align: left;">
        <div>Yogyakarta, {tanggal_surat}</div>
        <div>{humanize_jabatan(signer_jabatan, fakultas_nama)},</div>
        {(f"<div style='margin:6px 0;'><img src='{resolve_signature_path_and_uri(surat_id=surat_req.id, context_data=surat_req.payload_data)[1]}' style='height:92px;max-width:230px;width:auto;' /></div>" if resolve_signature_path_and_uri(surat_id=surat_req.id, context_data=surat_req.payload_data)[1] else "<br/><br/><br/>")}
        <div style="font-weight: bold; text-decoration: underline;">{signer_nama}</div>
        <div style="font-size: 10.5pt;">NIP. {signer_nip}</div>
      </td>
    </tr>
  </table>
</body>
</html>"""
def _ensure_pdf_on_disk(surat_req: SuratRequest) -> str:
    pdf_dir = os.path.join(settings.BASE_DIR, "media", "generated_pdf")
    os.makedirs(pdf_dir, exist_ok=True)
    target_pdf = os.path.join(pdf_dir, f"surat_{surat_req.id}.pdf")
    if not (os.path.exists(target_pdf) and os.path.getsize(target_pdf) > 0):
        student = surat_req.student
        prodi_nama = getattr(getattr(student, "prodi", None), "nama_prodi", None) or "Teknik Informatika"
        fakultas_nama = clean_fakultas_name(getattr(getattr(student, "fakultas", None), "nama_fakultas", None) or "Sains dan Teknologi")
        nomor_resmi = surat_req.nomor_surat_resmi or f"{surat_req.id:03d}/{surat_req.kode_surat.kode_surat}/FT/2026"
        effective_content = (
            (surat_req.final_approved_content or "").strip()
            or (surat_req.ai_original_draft or "").strip()
            or f"Dengan ini menerangkan bahwa {student.user.nama} (NIM {student.nim}) mengajukan {surat_req.kode_surat.nama_surat}."
        )
        generate_and_save_official_pdf(
            {
                "id": surat_req.id,
                "surat_request_id": surat_req.id,
                "kode_surat": surat_req.kode_surat.kode_surat,
                "is_custom_personal": str(surat_req.kode_surat.kode_surat or "").upper().startswith("CUSTOM"),
                "nomor_surat": nomor_resmi,
                "nama_surat": surat_req.kode_surat.nama_surat,
                "nama_mahasiswa": student.user.nama,
                "nim": student.nim,
                "program_studi": prodi_nama,
                "fakultas": fakultas_nama,
                "semester_aktif": getattr(student, "semester_aktif", "-"),
                "tahun_akademik": getattr(student, "tahun_akademik", "-"),
                "final_approved_content": effective_content,
                "isi_surat": effective_content,
                "payload": surat_req.payload_data or {},
                "qr_verification_code": surat_req.qr_verification_code or nomor_resmi,
                "nama_penandatangan": _resolve_signer(surat_req)[0],
                "nip_penandatangan": _resolve_signer(surat_req)[1],
                "jabatan_penandatangan": _resolve_signer(surat_req)[2],
            }
        )
    return target_pdf
def _append_chat_feedback(surat_req: SuratRequest, text: str) -> None:
    try:
        thread = getattr(surat_req, "chat_thread", None)
        if thread is None:
            thread = ChatThread.objects.filter(surat_requests=surat_req).order_by("-updated_at").first()
        if thread is not None:
            ChatMessage.objects.create(
                thread=thread,
                sender="assistant",
                message=text,
            )
    except Exception as exc:
        logger.warning(
            "Gagal menambahkan pesan umpan balik chat untuk surat_request=%s: %s",
            getattr(surat_req, "id", None),
            exc,
        )


def _build_pdf_preview_response(request, pk: int, attachment: bool = False):
    surat_req = (
        SuratRequest.objects.select_related(
            "student", "student__user", "student__prodi", "student__fakultas", "kode_surat"
        )
        .filter(pk=pk)
        .first()
    )
    if not surat_req:
        return Response({"error": "Surat tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)
    if not _user_can_view_surat(request.user, surat_req):
        return Response(
            {"error": "Anda tidak memiliki izin untuk mengakses dokumen surat ini."},
            status=status.HTTP_403_FORBIDDEN,
        )
    target_pdf = _ensure_pdf_on_disk(surat_req)
    nomor_clean = str(surat_req.nomor_surat_resmi or f"req_{pk}").replace("/", "_")
    with open(target_pdf, "rb") as f_pdf:
        pdf_bytes = f_pdf.read()
    if request.query_params.get("encoding") == "base64" or request.query_params.get("as_base64") == "1":
        return Response(
            {
                "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                "print_html": _build_official_a4_html(surat_req),
                "filename": f"surat_{nomor_clean}.pdf",
            },
            status=status.HTTP_200_OK,
        )
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    disposition = "attachment" if attachment else "inline"
    resp["Content-Disposition"] = f'{disposition}; filename="surat_{nomor_clean}.pdf"'
    resp["Content-Security-Policy"] = "frame-ancestors 'self' http://localhost:* http://127.0.0.1:*"
    return resp


@method_decorator(xframe_options_exempt, name="dispatch")
class SuratPreviewPdfAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        return _build_pdf_preview_response(request, pk, attachment=False)


class SuratDownloadPdfAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        return _build_pdf_preview_response(request, pk, attachment=True)


class SuratMarkPrintedAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        surat_req = SuratRequest.objects.select_related(
            "kode_surat", "student", "student__user", "student__prodi", "student__fakultas"
        ).filter(pk=pk).first()
        if not surat_req:
            return Response({"error": "Surat tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)
        if not _user_owns_surat(request.user, surat_req):
            return Response(
                {"error": "Anda tidak memiliki izin untuk mencetak dokumen surat ini."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not _is_custom_surat(surat_req) and surat_req.status not in (
            SuratStatus.APPROVED,
            SuratStatus.SENT,
            SuratStatus.PRINTED,
        ):
            return Response(
                {"error": "Surat resmi belum disetujui sehingga belum siap dicetak."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _ensure_pdf_on_disk(surat_req)
        surat_req.status = SuratStatus.PRINTED
        surat_req.save(update_fields=["status"])
        _append_chat_feedback(
            surat_req,
            f"🖨️ Dokumen resmi **{surat_req.kode_surat.nama_surat}** "
            f"(No. `{surat_req.nomor_surat_resmi or surat_req.id}`) telah dicetak ke printer.",
        )
        return Response(
            {
                "status": "PRINTED",
                "message": "Dokumen resmi telah dicetak ke printer.",
            },
            status=status.HTTP_200_OK,
        )


class SuratDeliverEmailAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        surat_req = SuratRequest.objects.select_related(
            "kode_surat", "student", "student__user", "student__prodi", "student__fakultas"
        ).filter(pk=pk).first()
        if not surat_req:
            return Response({"error": "Surat tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)
        if not _user_owns_surat(request.user, surat_req):
            return Response(
                {"error": "Anda tidak memiliki izin untuk mengirim dokumen surat ini."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not _is_custom_surat(surat_req) and surat_req.status not in (
            SuratStatus.APPROVED,
            SuratStatus.SENT,
            SuratStatus.PRINTED,
        ):
            return Response(
                {"error": "Surat resmi belum disetujui sehingga belum dapat dikirim ke email."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recipient_email = str(request.data.get("recipient_email") or "").strip()
        if not recipient_email:
            return Response({"error": "Alamat email tujuan wajib diisi."}, status=status.HTTP_400_BAD_REQUEST)
        target_pdf = _ensure_pdf_on_disk(surat_req)
        subject = f"Dokumen Resmi: {surat_req.kode_surat.nama_surat} ({surat_req.nomor_surat_resmi or surat_req.id})"
        body = (
            f"Yth. Penerima,\n\n"
            f"Berikut kami lampirkan dokumen resmi {surat_req.kode_surat.nama_surat} "
            f"atas nama {surat_req.student.user.nama} (NIM: {surat_req.student.nim}).\n\n"
            f"Terima kasih,\nASURA Persuratan Kampus"
        )
        res = send_surat_via_gmail_admin(
            recipient_email=recipient_email,
            subject=subject,
            body_message=body,
            pdf_path=target_pdf,
        )
        if res.get("status") != "SUCCESS":
            return Response(
                {"error": res.get("message", "Gagal mengirim email.")},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        surat_req.status = SuratStatus.SENT
        surat_req.target_destination_address = recipient_email
        surat_req.save(update_fields=["status", "target_destination_address"])
        _append_chat_feedback(
            surat_req,
            f"✉️ Dokumen resmi **{surat_req.kode_surat.nama_surat}** "
            f"(No. `{surat_req.nomor_surat_resmi or surat_req.id}`) berhasil dikirim ke email **{recipient_email}**.",
        )
        return Response(
            {
                "status": "SENT",
                "message": f"Dokumen berhasil dikirim ke {recipient_email}.",
            },
            status=status.HTTP_200_OK,
        )


class SuratUploadSignatureAPIView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        from .services.signature_storage import save_request_signature_file
        from .services.pdf_generator_safe import generate_and_save_official_pdf
        surat_req = SuratRequest.objects.select_related(
            "student", "student__user", "student__prodi", "student__fakultas", "kode_surat"
        ).filter(pk=pk).first()
        if not surat_req:
            return Response({"error": "Surat tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)
        if not _user_owns_surat(request.user, surat_req):
            return Response(
                {"error": "Anda tidak memiliki izin untuk mengunggah tanda tangan pada surat ini."},
                status=status.HTTP_403_FORBIDDEN,
            )
        sig_file = request.FILES.get("signature_image") or request.FILES.get("file")
        data_uri = str(request.data.get("signature_data_uri") or "")
        saved_path = save_request_signature_file(
            surat_id=surat_req.id,
            uploaded_file=sig_file,
            data_uri=data_uri,
        )
        if not saved_path:
            return Response(
                {"error": "File gambar tanda tangan tidak valid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pdata = dict(surat_req.payload_data or {})
        pdata["_manual_signature_path"] = saved_path
        surat_req.payload_data = pdata
        surat_req.save(update_fields=["payload_data"])
        st = surat_req.student
        is_custom = _is_custom_surat(surat_req)
        signer_nama, signer_nip, signer_jabatan = _resolve_signer(surat_req)
        generate_and_save_official_pdf({
            "id": surat_req.id,
            "surat_request_id": surat_req.id,
            "kode_surat": surat_req.kode_surat.kode_surat,
            "is_custom_personal": is_custom,
            "nomor_surat": surat_req.nomor_surat_resmi or (
                f"CUSTOM/{surat_req.id:03d}/2026"
                if is_custom
                else f"{surat_req.id:03d}/{surat_req.kode_surat.kode_surat}/FT/2026"
            ),
            "nama_surat": pdata.get("judul_surat") or surat_req.kode_surat.nama_surat,
            "nama_mahasiswa": st.user.nama,
            "nim": st.nim,
            "program_studi": getattr(getattr(st, "prodi", None), "nama_prodi", None) or "Informatika",
            "fakultas": getattr(getattr(st, "fakultas", None), "nama_fakultas", None) or "Teknik",
            "semester_aktif": getattr(st, "semester_aktif", "-"),
            "tahun_akademik": getattr(st, "tahun_akademik", "-"),
            "final_approved_content": surat_req.final_approved_content or surat_req.ai_original_draft or "",
            "isi_surat": surat_req.final_approved_content or surat_req.ai_original_draft or "",
            "payload": pdata,
            "qr_verification_code": surat_req.qr_verification_code or f"ASURA-{surat_req.id}",
            "nama_penandatangan": signer_nama,
            "nip_penandatangan": signer_nip,
            "jabatan_penandatangan": signer_jabatan,
        })
        return Response(
            {
                "status": "OK",
                "message": "Tanda tangan berhasil dipasang ke dokumen PDF.",
            },
            status=status.HTTP_200_OK,
        )
