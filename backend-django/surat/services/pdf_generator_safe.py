import os
import re
import shutil
import tempfile
from typing import Dict, Any
from django.conf import settings
from django.utils import timezone
def _build_pure_python_pdf(lines: list[str]) -> bytes:
    """Membuat berkas PDF 1.4 A4 resmi secara mandiri tanpa dependensi eksternal."""
    def esc(s: str) -> str:
        safe = s.encode("latin-1", "replace").decode("latin-1")
        return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content_ops = ["BT", "/F1 11 Tf", "55 785 Td", "15 TL"]
    for idx, line in enumerate(lines[:46]):
        if idx == 0:
            content_ops.append(f"/F2 12 Tf ({esc(line)}) Tj /F1 11 Tf")
        else:
            content_ops.append(f"T* ({esc(line)}) Tj")
    content_ops.append("ET")
    stream_bytes = "\n".join(content_ops).encode("latin-1", "replace")
    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii") + stream_bytes + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>\nendobj\n",
        b"6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Times-Bold >>\nendobj\n",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_pos = len(pdf)
    pdf.extend(f"xref\n0 {len(objs) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)
def generate_and_save_official_pdf(context_data: Dict[str, Any]) -> str:
    nomor_surat = str(context_data.get("nomor_surat") or "-")
    nama_mhs = str(context_data.get("nama_mahasiswa") or "-")
    nim_mhs = str(context_data.get("nim") or "-")
    prodi_mhs = str(context_data.get("program_studi") or "-")
    fakultas_mhs = str(context_data.get("fakultas") or "Sains dan Teknologi")
    semester_mhs = str(context_data.get("semester_aktif") or "-")
    tahun_akademik = str(context_data.get("tahun_akademik") or "-")
    raw_isi = str(context_data.get("final_approved_content") or context_data.get("isi_surat") or "")
    isi_clean = re.sub(r"\*\*(.*?)\*\*", r"\1", raw_isi).replace("*", "").replace("`", "")
    isi_html = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", raw_isi).replace("*", "")
    payload = context_data.get("payload") or {}
    nama_surat = str(
        payload.get("judul_surat")
        or context_data.get("nama_surat")
        or "SURAT KETERANGAN RESMI"
    )
    tanggal_surat = str(context_data.get("tanggal_surat") or timezone.now().strftime("%d %B %Y"))
    kota_surat = str(context_data.get("kota_surat") or os.environ.get("UNIVERSITY_CITY", "Yogyakarta"))
    jabatan_pejabat = str(context_data.get("jabatan_penandatangan") or f"Dekan Fakultas {fakultas_mhs}")
    nama_pejabat = str(context_data.get("nama_penandatangan") or "Dr. Joel Evans, M.T.")
    nip_pejabat = str(context_data.get("nip_penandatangan") or "198001012005011001")
    qr_url = str(context_data.get("qr_verification_code") or context_data.get("qr_code_url") or nomor_surat)
    paragraphs_html = "".join(
        f"<p style='text-align: justify; margin: 0 0 10px 0;'>{p.strip()}</p>"
        for p in isi_html.splitlines()
        if p.strip()
    ) or f"<p>{isi_html}</p>"
    html_doc = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: Times, serif; font-size: 11.5pt; color: #000000;">
  <div style="text-align: center; border-bottom: 2px solid #000000; padding-bottom: 8px; margin-bottom: 14px;">
    <div style="font-size: 12pt; font-weight: bold;">KEMENTERIAN AGAMA REPUBLIK INDONESIA</div>
    <div style="font-size: 13pt; font-weight: bold;">UNIVERSITAS ISLAM NEGERI SUNAN KALIJAGA</div>
    <div style="font-size: 12pt; font-weight: bold;">FAKULTAS {fakultas_mhs.upper()}</div>
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
    <tr><td>Fakultas</td><td>: {fakultas_mhs}</td></tr>
    <tr><td>Semester / T.A.</td><td>: {semester_mhs} / {tahun_akademik}</td></tr>
  </table>
  <div>{paragraphs_html}</div>
  <p>Demikian surat ini dibuat untuk dipergunakan sebagaimana mestinya.</p>
  <br/>
  <table style="width: 100%;">
    <tr>
      <td style="width: 50%; font-size: 8.5pt; color: #333333;">
        <b>TERVERIFIKASI ELEKTRONIK (ASURA)</b><br/>
        Kode Verifikasi: {qr_url}
      </td>
      <td style="width: 50%;">
        {kota_surat}, {tanggal_surat}<br/>
        {jabatan_pejabat},<br/><br/><br/>
        <b><u>{nama_pejabat}</u></b><br/>
        NIP. {nip_pejabat}
      </td>
    </tr>
  </table>
</body>
</html>"""
    pdf_bytes = None
    try:
        from xhtml2pdf import pisa
        import io
        buf = io.BytesIO()
        res = pisa.CreatePDF(html_doc, dest=buf, encoding="utf-8")
        if not res.err and buf.getvalue():
            pdf_bytes = buf.getvalue()
    except Exception:
        pdf_bytes = None
    if not pdf_bytes:
        import textwrap
        plain_lines = [
            "KEMENTERIAN AGAMA RI - UIN SUNAN KALIJAGA YOGYAKARTA",
            f"FAKULTAS {fakultas_mhs.upper()}",
            "-" * 74,
            f"{nama_surat.upper()} (Nomor: {nomor_surat})",
            "",
            f"Penandatangan : {nama_pejabat} (NIP. {nip_pejabat})",
            f"Jabatan       : {jabatan_pejabat}",
            "",
            f"Nama Mahasiswa: {nama_mhs}",
            f"NIM           : {nim_mhs}",
            f"Program Studi : {prodi_mhs}",
            f"Semester/T.A. : {semester_mhs} / {tahun_akademik}",
            "",
        ]
        for para in isi_clean.splitlines():
            if para.strip():
                plain_lines.extend(textwrap.wrap(para.strip(), width=78))
                plain_lines.append("")
        plain_lines.extend([
            "Demikian surat ini dibuat untuk dipergunakan sebagaimana mestinya.",
            "",
            f"{kota_surat}, {tanggal_surat}",
            f"{nama_pejabat} (NIP. {nip_pejabat})",
            f"Verifikasi ASURA: {qr_url}",
        ])
        pdf_bytes = _build_pure_python_pdf(plain_lines)
    pdf_dir = os.path.join(settings.BASE_DIR, "media", "generated_pdf")
    os.makedirs(pdf_dir, exist_ok=True)
    nomor_clean = nomor_surat.replace("/", "_")
    surat_id = context_data.get("id") or context_data.get("surat_request_id")
    named_path = os.path.join(pdf_dir, f"surat_{nomor_clean}.pdf")
    with open(named_path, "wb") as f_out:
        f_out.write(pdf_bytes)
    if surat_id:
        id_path = os.path.join(pdf_dir, f"surat_{surat_id}.pdf")
        with open(id_path, "wb") as f_id:
            f_id.write(pdf_bytes)
        return f"/api/surat/requests/{surat_id}/preview-pdf/"
    return f"/media/generated_pdf/surat_{nomor_clean}.pdf"
