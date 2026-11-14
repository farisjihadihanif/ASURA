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
def clean_letter_body_text(raw_isi: str) -> str:
    text = str(raw_isi or "").replace("`", "").strip()
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text).replace("*", "")
    # Hapus kalimat basa-basi klise AI (AI slop)
    slop_patterns = [
        r"Mahasiswa yang bersangkutan senantiasa menunjukkan iktikad baik[^.]*\.",
        r"Yang bersangkutan merupakan mahasiswa yang berkelakuan baik dan mematuhi[^.]*\.",
        r"Surat keterangan ini diberikan kepada mahasiswa bersangkutan untuk dipergunakan sebagai Mahasiswa Aktif serta melengkapi berkas administrasi yang dipersyaratkan\.",
    ]
    for pat in slop_patterns:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    # Pisahkan per paragraf dan buang paragraf penutup ganda dari LLM
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
    fakultas_clean = clean_fakultas_name(context_data.get("fakultas") or "Sains dan Teknologi")
    semester_mhs = str(context_data.get("semester_aktif") or "-")
    tahun_akademik = str(context_data.get("tahun_akademik") or "-")
    raw_isi = str(context_data.get("final_approved_content") or context_data.get("isi_surat") or "")
    isi_clean = clean_letter_body_text(raw_isi)
    payload = context_data.get("payload") or {}
    surat_id = context_data.get("id") or context_data.get("surat_request_id")
    nama_surat = str(
        payload.get("judul_surat")
        or context_data.get("nama_surat")
        or "SURAT KETERANGAN RESMI"
    )
    tanggal_surat = str(context_data.get("tanggal_surat") or timezone.now().strftime("%d %B %Y"))
    kota_surat = str(context_data.get("kota_surat") or os.environ.get("UNIVERSITY_CITY", "Yogyakarta"))
    raw_jabatan = (
        payload.get("_signer_jabatan")
        or context_data.get("jabatan_penandatangan")
        or f"Dekan Fakultas {fakultas_clean}"
    )
    jabatan_pejabat = humanize_jabatan(raw_jabatan, fakultas_clean)
    nama_pejabat = str(
        payload.get("_signer_nama")
        or context_data.get("nama_penandatangan")
        or "Dr. Joel Evans, M.T."
    )
    nip_pejabat = str(
        payload.get("_signer_nip")
        or context_data.get("nip_penandatangan")
        or "198001012005011001"
    )
    qr_url = str(context_data.get("qr_verification_code") or context_data.get("qr_code_url") or nomor_surat)
    sig_local_path, sig_data_uri = resolve_signature_path_and_uri(
        surat_id=surat_id,
        lecturer=context_data.get("lecturer"),
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
        f"<p style='text-align: justify; margin: 0 0 10px 0; line-height: 1.55;'>{p.strip()}</p>"
        for p in isi_clean.splitlines()
        if p.strip()
    ) or f"<p style='text-align: justify; line-height: 1.55;'>{isi_clean}</p>"
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
    <tr><td style="width: 150px;">Nama Mahasiswa</td><td>: <b>{nama_mhs}</b></td></tr>
    <tr><td>NIM</td><td>: {nim_mhs}</td></tr>
    <tr><td>Program Studi</td><td>: {prodi_mhs}</td></tr>
    <tr><td>Fakultas</td><td>: {fakultas_clean}</td></tr>
    <tr><td>Semester / T.A.</td><td>: {semester_mhs} / {tahun_akademik}</td></tr>
  </table>
  <div>{paragraphs_html}</div>
  <p>Demikian surat ini dibuat untuk dipergunakan sebagaimana mestinya.</p>
  <br/>
  <table style="width: 100%;">
    <tr>
      <td style="width: 50%; font-size: 8.5pt; color: #333333; vertical-align: bottom;">
        <b>TERVERIFIKASI ELEKTRONIK (ASURA)</b><br/>
        Kode Verifikasi: {qr_url}
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
