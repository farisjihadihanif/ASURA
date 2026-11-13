import re
from typing import Optional
from surat.models import SuratType
from .campus_catalog import ensure_campus_surat_types
CATEGORY_WORDS = {"izin", "ijin", "keterangan", "pengantar", "rekomendasi"}

STOP_WORDS = {
    "surat", "dan", "yang", "untuk", "saya", "buatkan", "bikin",
    "mohon", "minta", "tolong", "pengajuan", "permohonan", "keperluan",
    "mau", "ingin", "butuh", "adalah", "di", "ke", "dari", "ini", "itu",
    "keterangan", "izin", "ijin", "pengantar", "rekomendasi",
}
EXPLICIT_PHRASE_MAPPINGS = [
    (r'\b(masih\s+kuliah|aktif\s+kuliah|kuliah\s+aktif)\b', 'SK-MK'),
    (r'\b(berkelakuan\s+baik)\b', 'SK-BB'),
    (r'\b(habis\s+teori)\b', 'SK-HT'),
    (r'\b(tidak\s+sedang\s+menerima\s+beasiswa|tidak\s+menerima\s+beasiswa|bebas\s+beasiswa)\b', 'SK-TB'),
    (r'\b(pindah\s+studi|pindah\s+kuliah|pindah\s+kampus)\b', 'SK-PS'),
    (r'\b(keterangan\s+lulus|skl)\b', 'SK-LL'),
    (r'\b(tugas\s+lapangan)\b', 'SI-TL'),
    (r'\b(ppl|plp|pkl|kerja\s+praktek|kerja\s+praktik|pps)\b', 'SI-PKL'),
    (r'\b(magang|internship)\b', 'SI-MAG'),
    (r'\b(penelitian\s+mata\s+kuliah)\b', 'SI-PMK'),
    (r'\b(studi\s+pendahuluan|observasi|survei|survey)\b', 'SI-SP'),
    (r'\b(penelitian\s+tugas\s+akhir|riset\s+tugas\s+akhir|penelitian\s+skripsi|riset\s+skripsi)\b', 'SI-PTA'),
    (r'\b(rekomendasi\s+penelitian)\b', 'SR-PNL'),
    (r'\b(rekomendasi\s+beasiswa|beasiswa)\b', 'SR-BEA'),
    (r'\b(izin\s+sakit|ijin\s+sakit|tidak\s+masuk\s+kuliah|sakit)\b', 'CUSTOM-SAKIT'),
]
def detect_intent_dynamically(user_message: str) -> Optional[str]:
    if not user_message:
        return None
    ensure_campus_surat_types()
    message_lower = user_message.lower().strip()
    surat_types = list(SuratType.objects.all())
    available_kodes = {s.kode_surat for s in surat_types}
    for surat in surat_types:
        if re.search(r'\b' + re.escape(surat.kode_surat.lower()) + r'\b', message_lower):
            return surat.kode_surat
    for pattern, kode in EXPLICIT_PHRASE_MAPPINGS:
        if re.search(pattern, message_lower) and kode in available_kodes:
            return kode
    user_tokens = set(re.findall(r'\b\w+\b', message_lower))
    best_surat = None
    best_score = 0
    for surat in surat_types:
        if surat.kode_surat.startswith("CUSTOM"):
            continue
        nama_tokens = [
            tk for tk in re.findall(r'\w+', surat.nama_surat.lower())
            if tk not in STOP_WORDS and len(tk) > 2
        ]
        score = sum(3 for tk in nama_tokens if tk in user_tokens)
        if score > best_score:
            best_score = score
            best_surat = surat.kode_surat
    if best_score >= 3 and best_surat:
        return best_surat
    question_words = {"apa", "aja", "saja", "daftar", "list", "tersedia", "jenis", "macam"}
    if user_tokens.intersection(question_words):
        return None
    if "surat" in user_tokens and len(user_tokens) >= 3 and "CUSTOM-UMUM" in available_kodes:
        return "CUSTOM-UMUM"
    return None
