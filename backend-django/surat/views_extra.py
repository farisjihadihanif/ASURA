import base64
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
from .models import ChatMessage, ChatThread, SuratRequest, SuratStatus
from .services.email_service import send_surat_via_gmail_admin
from .services.pdf_generator_safe import generate_and_save_official_pdf, clean_letter_body_text
from .services.signature_storage import resolve_signature_path_and_uri, humanize_jabatan, clean_fakultas_name
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
    <tr><td style="width: 155px; padding: 2px 0;">Nama</td><td style="width: 14px;">:</td><td><b>Dr. Joel Evans, M.T.</b></td></tr>
    <tr><td style="padding: 2px 0;">NIP</td><td>:</td><td>198001012005011001</td></tr>
    <tr><td style="padding: 2px 0;">Jabatan</td><td>:</td><td>Dekan Fakultas {fakultas_nama}</td></tr>
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
        <div style="border: 1px solid #888; padding: 8px; font-size: 8.5pt; color: #333; background: #fafafa;">
          <b>TERVERIFIKASI ELEKTRONIK (ASURA)</b><br/>
          Dokumen resmi diterbitkan melalui Sistem Persuratan ASURA.<br/>
          Kode Verifikasi: {qr_url}
        </div>
      </td>
      <td style="width: 52%; padding-left: 24px; text-align: left;">
        <div>Yogyakarta, {tanggal_surat}</div>
        <div>{humanize_jabatan((surat_req.payload_data or {{}}).get("_signer_jabatan") or "", fakultas_nama)},</div>
        {(f"<div style='margin:6px 0;'><img src='{resolve_signature_path_and_uri(surat_id=surat_req.id, context_data=surat_req.payload_data)[1]}' style='height:92px;max-width:230px;width:auto;' /></div>" if resolve_signature_path_and_uri(surat_id=surat_req.id, context_data=surat_req.payload_data)[1] else "<br/><br/><br/>")}
        <div style="font-weight: bold; text-decoration: underline;">{(surat_req.payload_data or {{}}).get("_signer_nama") or "Dr. Joel Evans, M.T."}</div>
        <div style="font-size: 10.5pt;">NIP. {(surat_req.payload_data or {{}}).get("_signer_nip") or "198001012005011001"}</div>
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
            }
        )
    return target_pdf
def _append_chat_feedback(surat_req: SuratRequest, text: str) -> None:
    try:
        thread = ChatThread.objects.filter(latest_surat_request=surat_req).order_by("-updated_at").first()
        if not thread:
            msg = ChatMessage.objects.filter(surat_request=surat_req).select_related("thread").first()
            thread = msg.thread if msg else None
        if thread:
            ChatMessage.objects.create(
                thread=thread,
                sender="assistant",
                text=text,
            )
    except Exception:
        pass
@method_decorator(xframe_options_exempt, name="dispatch")
class SuratPreviewPdfAPIView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    def get(self, request, pk: int):
        surat_req = (
            SuratRequest.objects.select_related(
                "student", "student__user", "student__prodi", "student__fakultas", "kode_surat"
            )
            .filter(pk=pk)
            .first()
        )
        if not surat_req:
            return Response({"error": "Surat tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)
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
        resp["Content-Disposition"] = f'inline; filename="surat_{nomor_clean}.pdf"'
        resp["Content-Security-Policy"] = "frame-ancestors 'self' http://localhost:* http://127.0.0.1:*"
        return resp
class SuratDownloadPdfAPIView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    def get(self, request, pk: int):
        resp = SuratPreviewPdfAPIView().get(request, pk)
        if hasattr(resp, "headers") and "Content-Disposition" in resp:
            resp["Content-Disposition"] = resp["Content-Disposition"].replace("inline;", "attachment;")
        return resp
class SuratMarkPrintedAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        surat_req = SuratRequest.objects.select_related("kode_surat").filter(pk=pk).first()
        if not surat_req:
            return Response({"error": "Surat tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)
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
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk: int):
        surat_req = SuratRequest.objects.select_related("kode_surat", "student", "student__user").filter(pk=pk).first()
        if not surat_req:
            return Response({"error": "Surat tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)
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
