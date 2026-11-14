import base64
import io
import os
import re
from typing import Optional
from django.conf import settings
def get_signature_dir() -> str:
    sig_dir = os.path.join(settings.BASE_DIR, "media", "signatures")
    os.makedirs(sig_dir, exist_ok=True)
    return sig_dir
def clean_fakultas_name(raw_fakultas: str) -> str:
    val = str(raw_fakultas or "").strip()
    val = re.sub(r"^(?:fakultas\s+)+", "", val, flags=re.IGNORECASE).strip()
    return val or "Sains dan Teknologi"
def humanize_jabatan(raw_jabatan: str, fakultas_nama: str = "Teknik") -> str:
    fak_clean = clean_fakultas_name(fakultas_nama)
    val = str(raw_jabatan or "").strip()
    if not val:
        return f"Dekan Fakultas {fak_clean}"
    upper = val.upper()
    mapping = {
        "DEKAN_FT": "Dekan Fakultas Teknik",
        "DEKAN_FST": "Dekan Fakultas Sains dan Teknologi",
        "DEKAN": f"Dekan Fakultas {fak_clean}",
        "WADEK_1": "Wakil Dekan Bidang Akademik",
        "WADEK_2": "Wakil Dekan Bidang Administrasi Umum",
        "WADEK_3": "Wakil Dekan Bidang Kemahasiswaan",
        "KAPRODI_IF": "Ketua Program Studi Informatika",
        "KAPRODI_TI": "Ketua Program Studi Teknik Informatika",
        "KAPRODI": "Ketua Program Studi",
        "DOSEN_PA": "Dosen Pembimbing Akademik",
        "DOSEN": "Dosen Wali / Pembimbing Akademik",
    }
    if upper in mapping:
        return mapping[upper]
    if "_" in val and val.isupper():
        return val.replace("_", " ").title()
    # Bersihkan jika terlanjur tertulis "Dekan Fakultas Fakultas Teknik"
    return re.sub(r"Fakultas\s+Fakultas\s+", "Fakultas ", val, flags=re.IGNORECASE)
def normalize_to_png_bytes(raw_bytes: bytes) -> Optional[bytes]:
    if not raw_bytes:
        return None
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw_bytes))
        if img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")
        # Pangkas margin transparan/putih berlebih agar goresan TTD tampil besar & proporsional
        if img.mode == "RGBA":
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
        else:
            gray = img.convert("L")
            inv = gray.point(lambda p: 255 if p < 245 else 0)
            bbox = inv.getbbox()
            if bbox:
                img = img.crop(bbox)
        img.thumbnail((460, 190))
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        if raw_bytes.startswith(b"\x89PNG") or raw_bytes.startswith(b"\xff\xd8"):
            return raw_bytes
        return None
def save_request_signature_file(surat_id: int, uploaded_file=None, data_uri: str = "", lecturer_id=None, save_to_profile: bool = False) -> Optional[str]:
    raw_bytes = None
    if uploaded_file is not None:
        try:
            uploaded_file.seek(0)
            raw_bytes = uploaded_file.read()
        except Exception:
            raw_bytes = None
    elif data_uri and "base64," in data_uri:
        try:
            b64_part = data_uri.split("base64,", 1)[1].strip()
            raw_bytes = base64.b64decode(b64_part)
        except Exception:
            raw_bytes = None
    png_bytes = normalize_to_png_bytes(raw_bytes) if raw_bytes else None
    if not png_bytes:
        return None
    sig_dir = get_signature_dir()
    req_sig_path = os.path.join(sig_dir, f"req_{surat_id}.png")
    with open(req_sig_path, "wb") as f:
        f.write(png_bytes)
    if save_to_profile and lecturer_id:
        prof_sig_path = os.path.join(sig_dir, f"lecturer_{lecturer_id}.png")
        with open(prof_sig_path, "wb") as f_prof:
            f_prof.write(png_bytes)
    return req_sig_path
def resolve_signature_path_and_uri(surat_id=None, lecturer=None, context_data: dict = None) -> tuple[Optional[str], Optional[str]]:
    ctx = context_data or {}
    sig_dir = get_signature_dir()
    for key in ("manual_signature_data_uri", "signature_data_uri", "signature_base64"):
        val = str(ctx.get(key) or "").strip()
        if val:
            if not val.startswith("data:image/"):
                val = f"data:image/png;base64,{val}"
            if surat_id:
                saved = save_request_signature_file(int(surat_id), data_uri=val)
                if saved and os.path.exists(saved):
                    with open(saved, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("ascii")
                    return os.path.abspath(saved), f"data:image/png;base64,{b64}"
    for key in ("manual_signature_path", "signature_image_path", "signature_path"):
        p = str(ctx.get(key) or "").strip()
        if p and os.path.exists(p) and os.path.getsize(p) > 0:
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return os.path.abspath(p), f"data:image/png;base64,{b64}"
    if surat_id:
        req_path = os.path.join(sig_dir, f"req_{surat_id}.png")
        if os.path.exists(req_path) and os.path.getsize(req_path) > 0:
            with open(req_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return os.path.abspath(req_path), f"data:image/png;base64,{b64}"
    if lecturer is not None:
        lec_id = getattr(lecturer, "id", None)
        if lec_id:
            prof_path = os.path.join(sig_dir, f"lecturer_{lec_id}.png")
            if os.path.exists(prof_path) and os.path.getsize(prof_path) > 0:
                with open(prof_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                return os.path.abspath(prof_path), f"data:image/png;base64,{b64}"
        for field_name in ("signature_image", "ttd_image", "signature", "tanda_tangan"):
            field_val = getattr(lecturer, field_name, None)
            if field_val:
                try:
                    fpath = getattr(field_val, "path", None)
                    if fpath and os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                        with open(fpath, "rb") as f:
                            png_b = normalize_to_png_bytes(f.read())
                        if png_b:
                            target_p = os.path.join(sig_dir, f"lecturer_{lec_id or 'default'}.png")
                            with open(target_p, "wb") as f_out:
                                f_out.write(png_b)
                            b64 = base64.b64encode(png_b).decode("ascii")
                            return os.path.abspath(target_p), f"data:image/png;base64,{b64}"
                except Exception:
                    pass
    return None, None
