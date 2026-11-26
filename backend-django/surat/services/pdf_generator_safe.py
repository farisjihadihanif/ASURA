import io
import os
import re
from typing import Dict, Any
from django.conf import settings
from django.utils import timezone
from .signature_storage import (
    resolve_signature_path_and_uri,
    humanize_jabatan,
    clean_fakultas_name,
)
from .custom_letter_ai import generate_custom_letter_body, _strip_redundant_header_footer
def _build_qr_img_html(url: str) -> str:
    """QR code verifikasi sebagai gambar base64 (tanpa teks URL panjang yang menabrak/membekukan layout)."""
    try:
        import base64
        import io as _io
        import qrcode

        qr = qrcode.QRCode(box_size=6, border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(url)
        qr.make(fit=True)
        buf = _io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"<img src='data:image/png;base64,{data}' style='width: 92px; height: 92px;' />"
    except Exception:
        return ""


def clean_letter_body_text(raw_isi: str, is_custom: bool = False) -> str:
    text = str(raw_isi or "").replace("`", "").strip()
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text).replace("*", "")
    if is_custom:
        text = _strip_redundant_header_footer(text)
        cleaned_paras = [re.sub(r"\s{2,}", " ", p).strip() for p in text.splitlines() if p.strip()]
        return "\n".join(cleaned_paras).strip()
    slop_patterns = [
        r"Mahasiswa yang bersangkutan senantiasa menunjukkan iktikad baik[^.]*\.",
        r"Yang bersangkutan merupakan mahasiswa yang berkelakuan baik dan mematuhi[^.]*\.",
        r"Surat keterangan ini diberikan kepada mahasiswa bersangkutan untuk dipergunakan sebagai Mahasiswa Aktif serta melengkapi berkas administrasi yang dipersyaratkan\.",
    ]
    for pat in slop_patterns:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    cleaned_paras = []
    for para in text.splitlines():
        p = re.sub(r"\s{2,}", " ", para).strip()
        if not p:
            continue
        if re.match(r"^(Demikianlah?\s+surat|Atas\s+perhatian\s+dan\s+kerja\s*samanya)", p, flags=re.IGNORECASE):
            continue
        cleaned_paras.append(p)
    return "\n".join(cleaned_paras).strip()
def generate_and_save_official_pdf(context_data: Dict[str, Any]) -> str:
    nomor_surat = str(context_data.get("nomor_surat") or "-")
    nama_mhs = str(context_data.get("nama_mahasiswa") or "-")
    nim_mhs = str(context_data.get("nim") or "-")
    prodi_mhs = str(context_data.get("program_studi") or "-")
    fakultas_clean = clean_fakultas_name(context_data.get("fakultas") or "Teknik")
    semester_mhs = str(context_data.get("semester_aktif") or "-")
    tahun_akademik = str(context_data.get("tahun_akademik") or "-")
    raw_isi = str(context_data.get("final_approved_content") or context_data.get("isi_surat") or "")
    payload = context_data.get("payload") or {}
    surat_id = context_data.get("id") or context_data.get("surat_request_id")
    kode_surat = str(context_data.get("kode_surat") or payload.get("kode_surat") or "").upper()
    is_custom = bool(
        context_data.get("is_custom_personal")
        or payload.get("_is_custom_personal")
        or kode_surat.startswith("CUSTOM")
    )
    is_sakit = kode_surat == "CUSTOM-SAKIT" or "sakit" in str(context_data.get("nama_surat") or "").lower()
    isi_clean = clean_letter_body_text(raw_isi, is_custom=is_custom)
    if is_custom and (
        not isi_clean
        or "fakultas teknik universitas yang bersangkutan" in isi_clean.lower()
        or "mahasiswa bersangkutan" in isi_clean.lower()
        or "kelengkapan administratif" in isi_clean.lower()
    ):
        class _DummyStu:
            nim = nim_mhs
            class user:
                nama = nama_mhs
            class prodi:
                nama_prodi = prodi_mhs
        isi_clean = clean_letter_body_text(
            generate_custom_letter_body(
                _DummyStu(),
                payload_data=payload,
                user_prompt_context=str(context_data.get("nama_surat") or ""),
                kode_surat="CUSTOM-SAKIT" if is_sakit else "CUSTOM-UMUM",
            ),
            is_custom=True,
        )
    if is_custom:
        from .custom_letter_ai import derive_custom_title

        nama_surat = derive_custom_title(
            payload,
            fallback_text="",
            default="Surat Izin Sakit" if is_sakit else "Surat Pribadi",
        )
    else:
        nama_surat = str(
            payload.get("judul_surat")
            or context_data.get("nama_surat")
            or "SURAT KETERANGAN RESMI"
        )
    tujuan_surat = str(
        payload.get("dosen_tujuan")
        or payload.get("instansi_tujuan")
        or payload.get("nama_instansi_tujuan")
        or payload.get("penerima")
        or payload.get("tujuan")
        or ""
    ).strip()
    _bulan = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    _now = timezone.localtime(timezone.now()) if timezone.is_aware(timezone.now()) else timezone.now()
    tanggal_surat = str(context_data.get("tanggal_surat") or f"{_now.day} {_bulan[_now.month - 1]} {_now.year}")
    kota_surat = str(context_data.get("kota_surat") or os.environ.get("UNIVERSITY_CITY", "Yogyakarta"))
    sig_local_path, sig_data_uri = resolve_signature_path_and_uri(
        surat_id=surat_id,
        lecturer=None if is_custom else context_data.get("lecturer"),
        context_data={**payload, **context_data},
    )
    if sig_local_path and os.path.exists(sig_local_path):
        sig_block_html = (
            f"<div style='margin: 6px 0 4px 0;'>"
            f"<img src='{sig_local_path}' style='height: 92px; max-width: 230px; width: auto;' />"
            f"</div>"
        )
    elif sig_data_uri:
        sig_block_html = (
            f"<div style='margin: 6px 0 4px 0;'>"
            f"<img src='{sig_data_uri}' style='height: 92px; max-width: 230px; width: auto;' />"
            f"</div>"
        )
    else:
        sig_block_html = "<br/><br/><br/><br/>"
    paragraphs_html = "".join(
        f"<p style='text-align: justify; margin: 0 0 11px 0; line-height: 1.6;'>{p.strip()}</p>"
        for p in isi_clean.splitlines()
        if p.strip()
    ) or f"<p style='text-align: justify; line-height: 1.6;'>{isi_clean}</p>"
    if is_custom:
        # Format Surat Non-Formal & Surat Sakit:
        # 1) Tanpa Kop Surat & Tanpa Nomor Surat
        # 2) Tanggal di kanan atas, Yth. Penerima di kiri atas
        # 3) TTD Mahasiswa: Surat Sakit pakai Nama + NIM, Surat Custom Non-Formal hanya Nama saja
        yth_block = ""
        if tujuan_surat:
            yth_clean = re.sub(r"^(?:kepada\s+)?yth\.?\s*", "", tujuan_surat, flags=re.IGNORECASE).strip()
            yth_block = (
                f"<div style='margin-bottom: 18px; line-height: 1.5;'>"
                f"Kepada Yth.<br/>"
                f"<b>{yth_clean}</b><br/>"
                f"di Tempat"
                f"</div>"
            )
        requester_role = str(context_data.get("requester_role") or "STUDENT").upper()
        id_footer_label = "NIP." if requester_role == "LECTURER" else "NIM."
        nim_footer_html = f"<br/><span style='font-size: 10.5pt; color: #333333;'>{id_footer_label} {nim_mhs}</span>" if is_sakit else ""
        html_doc = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: Times, serif; font-size: 12pt; color: #000000; padding: 12px 22px;">
  {yth_block}
  <div style="text-align: center; margin: 10px 0 20px 0;">
    <div style="font-size: 13pt; font-weight: bold; text-decoration: underline;">{nama_surat.upper()}</div>
  </div>
  <div style="margin-bottom: 24px;">{paragraphs_html}</div>
  <br/>
  <table style="width: 100%;">
    <tr>
      <td style="width: 56%;"></td>
      <td style="width: 44%; text-align: left; vertical-align: top;">
        {kota_surat}, {tanggal_surat}<br/>
        Hormat saya,
        {sig_block_html}
        <b><u>{nama_mhs}</u></b>{nim_footer_html}
      </td>
    </tr>
  </table>
</body>
</html>"""
    else:
        raw_jabatan = (
            payload.get("_signer_jabatan")
            or context_data.get("jabatan_penandatangan")
            or f"Dekan Fakultas {fakultas_clean}"
        )
        jabatan_pejabat = humanize_jabatan(raw_jabatan, fakultas_clean)
        nama_pejabat = str(
            payload.get("_signer_nama")
            or context_data.get("nama_penandatangan")
            or "Pejabat Penandatangan"
        )
        nip_pejabat = str(
            payload.get("_signer_nip")
            or context_data.get("nip_penandatangan")
            or "-"
        )
        qr_url = str(context_data.get("qr_verification_code") or context_data.get("qr_code_url") or nomor_surat)
        qr_img_html = _build_qr_img_html(qr_url)
        qr_token = qr_url.rstrip("/").split("/")[-1][:8].upper()
        html_doc = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: Times, serif; font-size: 11.5pt; color: #000000;">
  <div style="text-align: center; border-bottom: 2px solid #000000; padding-bottom: 8px; margin-bottom: 14px;">
    <div style="font-size: 12pt; font-weight: bold;">KEMENTERIAN AGAMA REPUBLIK INDONESIA</div>
    <div style="font-size: 13pt; font-weight: bold;">UNIVERSITAS ISLAM NEGERI SUNAN KALIJAGA</div>
    <div style="font-size: 12pt; font-weight: bold;">FAKULTAS {fakultas_clean.upper()}</div>
    <div style="font-size: 9pt;">Jl. Marsda Adisucipto Yogyakarta 55281 | www.uin-suka.ac.id</div>
  </div>
  <div style="text-align: center; margin: 12px 0 16px 0;">
    <div style="font-size: 12pt; font-weight: bold; text-decoration: underline;">{nama_surat.upper()}</div>
    <div style="font-size: 10.5pt;">Nomor: {nomor_surat}</div>
  </div>
  <p>Yang bertanda tangan di bawah ini:</p>
  <table style="width: 100%; margin-bottom: 10px;">
    <tr><td style="width: 150px;">Nama</td><td>: <b>{nama_pejabat}</b></td></tr>
    <tr><td>NIP</td><td>: {nip_pejabat}</td></tr>
    <tr><td>Jabatan</td><td>: {jabatan_pejabat}</td></tr>
  </table>
  <p>Menerangkan dengan sesungguhnya bahwa:</p>
  <table style="width: 100%; margin-bottom: 12px;">
    {(
        f"<tr><td style='width: 150px;'>Nama</td><td>: <b>{nama_mhs}</b></td></tr>"
        f"<tr><td>NIP</td><td>: {nim_mhs}</td></tr>"
        f"<tr><td>Program Studi</td><td>: {prodi_mhs}</td></tr>"
        f"<tr><td>Fakultas</td><td>: {fakultas_clean}</td></tr>"
        + (f"<tr><td>Jabatan</td><td>: {context_data.get('jabatan_pemohon')}</td></tr>" if context_data.get('jabatan_pemohon') else "")
        if str(context_data.get("requester_role") or "STUDENT").upper() == "LECTURER"
        else
        f"<tr><td style='width: 150px;'>Nama Mahasiswa</td><td>: <b>{nama_mhs}</b></td></tr>"
        f"<tr><td>NIM</td><td>: {nim_mhs}</td></tr>"
        f"<tr><td>Program Studi</td><td>: {prodi_mhs}</td></tr>"
        f"<tr><td>Fakultas</td><td>: {fakultas_clean}</td></tr>"
        f"<tr><td>Semester / T.A.</td><td>: {semester_mhs} / {tahun_akademik}</td></tr>"
    )}
  </table>
  <div>{paragraphs_html}</div>
  <p>Demikian surat ini dibuat untuk dipergunakan sebagaimana mestinya.</p>
  <br/>
  <table style="width: 100%;">
    <tr>
      <td style="width: 50%; font-size: 7.5pt; color: #333333; vertical-align: bottom;">
        {qr_img_html}<br/>
        <b>Ditandatangani secara elektronik (ASURA)</b><br/>
        Pindai QR untuk memeriksa keaslian.<br/>
        Kode: {qr_token}
      </td>
      <td style="width: 50%; vertical-align: top;">
        {kota_surat}, {tanggal_surat}<br/>
        {jabatan_pejabat},
        {sig_block_html}
        <b><u>{nama_pejabat}</u></b><br/>
        NIP. {nip_pejabat}
      </td>
    </tr>
  </table>
</body>
</html>"""
    from xhtml2pdf import pisa
    buf = io.BytesIO()
    res = pisa.CreatePDF(html_doc, dest=buf, encoding="utf-8")
    if res.err or not buf.getvalue():
        raise RuntimeError(f"xhtml2pdf gagal merender PDF (err={res.err})")
    pdf_bytes = buf.getvalue()
    pdf_dir = os.path.join(settings.BASE_DIR, "media", "generated_pdf")
    os.makedirs(pdf_dir, exist_ok=True)
    nomor_clean = nomor_surat.replace("/", "_")
    named_path = os.path.join(pdf_dir, f"surat_{nomor_clean}.pdf")
    with open(named_path, "wb") as f_out:
        f_out.write(pdf_bytes)
    if surat_id:
        id_path = os.path.join(pdf_dir, f"surat_{surat_id}.pdf")
        with open(id_path, "wb") as f_id:
            f_id.write(pdf_bytes)
        return f"/api/surat/requests/{surat_id}/preview-pdf/"
    return f"/media/generated_pdf/surat_{nomor_clean}.pdf"
