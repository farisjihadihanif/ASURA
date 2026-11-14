"""Cek kelayakan mahasiswa untuk jenis surat tertentu.

Aturan di bawah memakai data profil mahasiswa yang sudah ada. Ambang batas yang belum
ditetapkan kampus bisa diubah lewat environment variable tanpa mengubah kode.
Jenis surat yang tidak ada di tabel ini dianggap layak.
"""
import os
from typing import Any, Callable, Dict, Optional

HABIS_TEORI_MIN_SKS = int(os.environ.get("HABIS_TEORI_MIN_SKS", "120"))


def _aktif(s: Any) -> Optional[str]:
    if str(getattr(s, "status_akademik", "") or "").upper() != "AKTIF":
        return "status akademik kamu saat ini bukan Aktif"
    return None


def _habis_teori(s: Any) -> Optional[str]:
    sks = int(getattr(s, "total_sks_lulus", 0) or 0)
    if sks < HABIS_TEORI_MIN_SKS:
        return f"SKS lulus kamu baru {sks}, sedangkan syarat minimal {HABIS_TEORI_MIN_SKS} SKS"
    return None


def _lulus(s: Any) -> Optional[str]:
    if str(getattr(s, "status_akademik", "") or "").upper() != "LULUS":
        return "data kelulusan/yudisium kamu belum tercatat di sistem"
    return None


def _tidak_beasiswa(s: Any) -> Optional[str]:
    if getattr(s, "status_beasiswa_aktif", False):
        return "kamu tercatat masih menerima beasiswa"
    return None


def _berkelakuan_baik(s: Any) -> Optional[str]:
    if getattr(s, "catatan_pelanggaran_etik", False) or not getattr(s, "status_disiplin_kampus", True):
        return "ada catatan pelanggaran/disiplin pada data kamu"
    return None


_RULES: Dict[str, Callable[[Any], Optional[str]]] = {
    "SK-MK": _aktif,
    "SK-HT": _habis_teori,
    "SK-LL": _lulus,
    "SK-TB": _tidak_beasiswa,
    "SK-BB": _berkelakuan_baik,
}


def check_eligibility(student: Any, kode_surat: str) -> Optional[str]:
    """Kembalikan pesan penolakan yang ramah, atau None bila layak."""
    rule = _RULES.get(str(kode_surat or "").strip().upper())
    reason = rule(student) if rule else None
    if not reason:
        return None
    return (
        f"Maaf, permohonan surat ini belum bisa diproses karena {reason}. "
        "Kalau menurutmu data itu keliru, hubungi bagian akademik untuk memperbaruinya."
    )
