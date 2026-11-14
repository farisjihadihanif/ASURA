import os
import re
from typing import Dict, Any, List
from django.conf import settings
_TITLE_SMALL_WORDS = {"dan", "ke", "di", "untuk", "dengan", "yang", "dari", "pada", "atau", "serta"}
_GENERIC_TITLE_RE = re.compile(r"(keterangan\s+lainnya|custom|surat\s+umum|^surat\s*$)", re.IGNORECASE)


def normalize_letter_title(text: Any) -> str:
    """Ubah ungkapan bebas (mis. 'buatkan surat permohonan kunjungan industri ke google')
    menjadi judul surat singkat ('Surat Permohonan Kunjungan Industri'). Kosong jika terlalu generik."""
    s = str(text or "").strip()
    if not s:
        return ""
    s = re.sub(r"\(?\bCUSTOM[-_ ]?[A-Z]*\b\)?", "", s, flags=re.IGNORECASE)
    if _GENERIC_TITLE_RE.search(s):
        return ""
    s = re.sub(
        r"^(tolong\s+|mohon\s+)?(buatkan|buat|bikinkan|bikin|susunkan|saya\s+(ingin|mau|butuh|perlu)(\s+membuat)?|aku\s+(ingin|mau|butuh)(\s+membuat)?)\s+(sebuah\s+)?",
        "",
        s.strip(),
        flags=re.IGNORECASE,
    )
    s = re.split(r"\s+(?:ke|kepada|untuk|di|pada|yang|dengan|dari|tanggal|guna|agar|supaya)\s+|[,.;\n]", s, maxsplit=1)[0].strip()
    s = re.sub(r"\s+", " ", s).strip(" -:()")
    if len(s) < 3:
        return ""
    if not re.match(r"(?i)^surat\b", s):
        s = f"Surat {s}"
    words = s.split(" ")
    titled = [
        w.lower() if (i > 0 and w.lower() in _TITLE_SMALL_WORDS) else (w if w.isupper() and len(w) > 1 else w[:1].upper() + w[1:].lower())
        for i, w in enumerate(words)
    ]
    return " ".join(titled)[:80]


def derive_custom_title(payload: Dict[str, Any], fallback_text: Any = "", default: str = "Surat Pribadi") -> str:
    """Judul surat custom mengikuti keperluan: judul_surat -> keperluan_surat -> permintaan awal."""
    payload = payload or {}
    for candidate in (payload.get("judul_surat"), payload.get("keperluan_surat"), fallback_text):
        t = normalize_letter_title(candidate)
        if t:
            return t
    return default


def _strip_redundant_header_footer(text: str) -> str:
    lines = []
    for raw in str(text or "").splitlines():
        s = raw.strip()
        if not s:
            lines.append("")
            continue
        # Buang baris kop/nomor/tanggal/blok TTD ganda yang sudah dirender template PDF
        if re.match(r"^(Nomor\s*:|Perihal\s*:|Yogyakarta,\s*\d+|Hormat\s+(saya|kami)\s*,?|Pemohon\s*,?|NIM\.?\s*[:.]?\s*[A-Z0-9]+)", s, flags=re.IGNORECASE):
            continue
        lines.append(raw.rstrip())
    cleaned = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", cleaned)
def generate_custom_letter_body(
    student,
    payload_data: Dict[str, Any] = None,
    user_prompt_context: str = "",
    history_messages: List[Dict[str, str]] = None,
    kode_surat: str = "CUSTOM-UMUM",
) -> str:
    payload = payload_data or {}
    kode = str(kode_surat or payload.get("kode_surat") or "CUSTOM-UMUM").upper()
    is_sakit = kode == "CUSTOM-SAKIT" or "sakit" in str(payload.get("judul_surat") or user_prompt_context).lower()
    nama_mhs = getattr(getattr(student, "user", None), "nama", "Mahasiswa")
    nim_mhs = getattr(student, "nim", "-")
    prodi_mhs = getattr(getattr(student, "prodi", None), "nama_prodi", "Informatika")
    judul = str(
        payload.get("judul_surat")
        or payload.get("perihal")
        or ("Surat Izin Sakit" if is_sakit else "Surat Pribadi")
    ).strip()
    tujuan = str(
        payload.get("dosen_tujuan")
        or payload.get("instansi_tujuan")
        or payload.get("nama_instansi_tujuan")
        or payload.get("penerima")
        or payload.get("tujuan")
        or ""
    ).strip()
    kegiatan = str(
        payload.get("mata_kuliah_kegiatan")
        or payload.get("mata_kuliah")
        or payload.get("kegiatan")
        or ""
    ).strip()
    tanggal_izin = str(payload.get("tanggal_izin") or payload.get("tanggal") or "hari ini").strip()
    keperluan = str(
        payload.get("keperluan_surat")
        or payload.get("alasan")
        or payload.get("keterangan")
        or payload.get("isi_surat")
        or user_prompt_context
        or ""
    ).strip()
    hist_text = ""
    if history_messages:
        hist_text = "\n".join(
            f"{m.get('sender', 'user')}: {m.get('text', '')}"
            for m in history_messages[-8:]
            if m.get("text")
        )
    api_key = (
        getattr(settings, "GEMINI_API_KEY", None)
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip()
    if is_sakit:
        system_instruction = (
            "Kamu menulis ISI BADAN SURAT IZIN SAKIT mahasiswa kepada dosen/pengampu kegiatan.\n"
            "ATURAN WAJIB:\n"
            "1. Sudut pandang ORANG PERTAMA ('Saya yang bertanda tangan di bawah ini...'), BUKAN pihak ketiga ('mahasiswa bersangkutan' atau 'kami sampaikan').\n"
            "2. Cantumkan identitas singkat pemohon: Nama, NIM, dan Program Studi.\n"
            "3. Jelaskan secara sopan bahwa pemohon memohon izin tidak dapat mengikuti perkuliahan/kegiatan yang disebutkan karena sakit.\n"
            "4. JANGAN tulis tanggal di atas, JANGAN tulis 'Kepada Yth.' (karena sudah diletakkan di kiri atas template), dan JANGAN tulis blok 'Hormat saya' / tanda tangan di bawah.\n"
            "5. Bebas emoji dan tanpa simbol markdown (** atau `)."
        )
        prompt = (
            f"Pemohon: {nama_mhs} (NIM: {nim_mhs}, Prodi: {prodi_mhs})\n"
            f"Ditujukan kepada: {tujuan or 'Bapak/Ibu Dosen Pengampu'}\n"
            f"Mata Kuliah / Kegiatan: {kegiatan or keperluan or 'Perkuliahan'}\n"
            f"Waktu Izin: {tanggal_izin}\n"
            f"Konteks chat:\n{hist_text}\n\n"
            "Tulis isi badan surat izin sakit yang rapi dan sopan:"
        )
    else:
        system_instruction = (
            "Kamu menulis ISI BADAN SURAT PRIBADI / NON-FORMAL.\n"
            "ATURAN WAJIB:\n"
            "1. INI SURAT NON-FORMAL PRIBADI: DILARANG mencantumkan NIM, Nomor Surat, Fakultas, Program Studi, atau istilah birokrasi kampus ('kelengkapan administratif', 'mahasiswa bersangkutan', 'menjadi periksa').\n"
            "2. Gunakan sudut pandang orang pertama ('Saya' / 'Aku') yang natural, hangat, dan terstruktur rapi dalam 2-3 paragraf sesuai tujuan surat.\n"
            "3. JANGAN tulis tanggal di atas, JANGAN tulis 'Yth.' di atas (sudah ada di kiri atas template), dan JANGAN tulis 'Hormat saya' / nama di bawah (sudah ada di blok TTD template).\n"
            "4. Bebas emoji dan tanpa simbol markdown (** atau `)."
        )
        prompt = (
            f"Nama Pengirim: {nama_mhs}\n"
            f"Judul / Perihal: {judul}\n"
            f"Penerima: {tujuan or '-'}\n"
            f"Maksud / Isi: {keperluan or judul}\n"
            f"Konteks chat:\n{hist_text}\n\n"
            "Tulis isi badan surat non-formal yang rapi dan menyentuh/sesuai konteks:"
        )
    if api_key:
        candidate_models = [
            getattr(settings, "GEMINI_MODEL_NAME", None),
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ]
        seen = set()
        models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=api_key)
            for model_name in models_to_try:
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.5,
                        ),
                    )
                    raw_out = (getattr(resp, "text", "") or "").strip()
                    if raw_out and "fakultas teknik" not in raw_out.lower() and "mahasiswa bersangkutan" not in raw_out.lower():
                        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", raw_out).replace("`", "")
                        return _strip_redundant_header_footer(cleaned)
                except Exception:
                    continue
        except Exception:
            pass
    # Fallback terstruktur & rapi jika API Gemini sedang sibuk
    if is_sakit:
        mk_line = f" pada mata kuliah/kegiatan {kegiatan}" if kegiatan else " pada kegiatan perkuliahan"
        return (
            f"Dengan hormat,\n\n"
            f"Saya yang bertanda tangan di bawah ini:\n"
            f"Nama : {nama_mhs}\n"
            f"NIM : {nim_mhs}\n"
            f"Program Studi : {prodi_mhs}\n\n"
            f"Dengan ini memohon izin untuk tidak dapat mengikuti perkuliahan{mk_line} pada {tanggal_izin} "
            f"dikarenakan kondisi kesehatan yang sedang kurang baik (sakit) dan memerlukan waktu istirahat untuk pemulihan.\n\n"
            f"Demikian surat izin ini saya sampaikan dengan sebenar-benarnya. Atas perhatian dan pengertian Bapak/Ibu, saya ucapkan terima kasih."
        )
    low_all = f"{judul} {keperluan}".lower()
    if "cinta" in low_all or "pacar" in low_all or "kencan" in low_all:
        target_name = tujuan or "Kamu"
        return (
            f"Halo {target_name},\n\n"
            f"Melalui surat singkat ini, saya ingin menyampaikan perasaan yang selama ini saya simpan. "
            f"{keperluan if keperluan else 'Setiap waktu dan obrolan bersamamu selalu meninggalkan kesan yang berarti bagi saya.'}\n\n"
            f"Besar harapan saya kita bisa saling mengenal lebih dekat dan melangkah bersama ke depannya."
        )
    return (
        f"Dengan hormat,\n\n"
        f"Melalui surat ini, saya ({nama_mhs}) bermaksud menyampaikan {judul.lower()}. "
        f"{keperluan if keperluan else 'Besar harapan saya maksud ini dapat diterima dengan baik.'}\n\n"
        f"Demikian surat ini saya buat. Atas perhatian dan waktunya, saya ucapkan terima kasih."
    )
