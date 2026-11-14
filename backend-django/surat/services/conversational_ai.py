import os
import re
from typing import List, Dict, Any
from django.conf import settings
def strip_emojis(text: str) -> str:
    if not text:
        return ""
    emoji_pattern = re.compile(
        "["
        "\U0001F1E0-\U0001F1FF"
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\u2600-\u26FF"
        "\u2700-\u27BF"
        "\ufe0f"
        "]+",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", str(text))
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()
def get_catalog_summary_lines() -> List[str]:
    from surat.models import SuratType
    try:
        from surat.services.campus_catalog import ensure_campus_surat_types
        ensure_campus_surat_types()
    except Exception:
        pass
    lines = []
    from surat.services.campus_catalog import CATALOG_CODES

    for st in SuratType.objects.filter(kode_surat__in=CATALOG_CODES).order_by("kategori", "nama_surat"):
        if str(st.kode_surat or "").upper().startswith("CUSTOM"):
            continue
        lines.append(f"- {st.nama_surat} ({st.kode_surat})")
    lines.append("- Custom (Surat pribadi/mandiri sesuai kebutuhan, seperti surat izin sakit, izin kegiatan, surat pernyataan, dll.)")
    return lines
def generate_conversational_reply(
    user_message: str = "",
    history_messages: List[Dict[str, str]] = None,
    student_info: Dict[str, Any] = None,
) -> str:
    catalog_lines = get_catalog_summary_lines()
    catalog_text = "\n".join(catalog_lines) if catalog_lines else "- Surat Keterangan Masih Kuliah (SK-MK)"
    api_key = (
        getattr(settings, "GEMINI_API_KEY", None)
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip()
    history_text = ""
    if history_messages:
        recent = history_messages[-8:]
        history_text = "\n".join(
            f"{'Mahasiswa' if m.get('sender') == 'user' else 'ASURA'}: {m.get('message') or m.get('text') or ''}"
            for m in recent
            if m.get("message") or m.get("text")
        )
    mhs_ctx = ""
    if student_info:
        mhs_ctx = (
            f"Data mahasiswa: Nama={student_info.get('nama', '-')}, "
            f"NIM={student_info.get('nim', '-')}, Prodi={student_info.get('prodi', '-')}, "
            f"Semester={student_info.get('semester', '-')}."
        )
    system_instruction = (
        "Kamu adalah ASURA, asisten persuratan akademik kampus yang sigap, jelas, dan membantu.\n"
        f"{mhs_ctx}\n\n"
        "Daftar jenis surat resmi kampus yang tersedia di sistem:\n"
        f"{catalog_text}\n\n"
        "Kemampuan tambahan penting:\n"
        "- Selain daftar surat standar di atas, kamu JUGA BISA membuatkan SURAT CUSTOM (bebas sesuai kebutuhan mahasiswa, misalnya surat izin kegiatan, surat pernyataan, surat pengantar khusus, dispensasi, atau surat permohonan lainnya).\n"
        "- Alur surat kampus resmi: kumpulkan detail -> susun draf -> diteruskan ke pejabat kampus (kaprodi/dekan) untuk ACC -> kirim email atau cetak.\n"
        "- Alur Surat Custom (pribadi, mis. surat sakit, surat cinta): langsung jadi tanpa persetujuan siapa pun dan TIDAK dikirim ke dosen. Jangan pernah bilang surat custom diteruskan ke dosen.\n\n"
        "ATURAN GAYA BAHASA:\n"
        "1. Jawab langsung ke inti pertanyaan mahasiswa secara natural, tanpa kalimat pembuka klise AI.\n"
        "2. DILARANG menggunakan emoji atau emotikon.\n"
        "3. Jika mahasiswa bertanya bisa bikin surat apa saja, tampilkan daftar surat di atas dan jelaskan bahwa kamu juga melayani pembuatan Surat Custom sesuai kebutuhan."
    )
    msg_clean = (user_message or "").strip() or "Halo"
    prompt = (
        f"Riwayat chat:\n{history_text}\n\n"
        f"Pesan mahasiswa: {msg_clean}\n\n"
        "Jawab langsung dan membantu:"
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
                            temperature=0.4,
                        ),
                    )
                    out_text = strip_emojis(getattr(resp, "text", "") or "")
                    if out_text:
                        return out_text
                except Exception:
                    continue
        except Exception:
            pass
    return strip_emojis(
        "Saya bisa membantu membuatkan surat resmi kampus berikut:\n\n"
        f"{catalog_text}\n\n"
        "Selain daftar di atas, saya juga bisa membuatkan **Surat Custom** sesuai kebutuhan spesifik kamu "
        "(seperti surat izin kegiatan, surat pernyataan, dispensasi, atau surat pengantar khusus).\n\n"
        "Sebutkan jenis surat dan keperluannya, nanti langsung saya buatkan drafnya."
    )

def upgrade_static_assistant_reply(
    reply_text: str,
    user_message: str,
    thread=None,
    student=None,
) -> str:
    txt = str(reply_text or "").strip()
    if not txt:
        return txt
    is_generic_stub = (
        "Halo, saya adalah Asisten AI" in txt
        or "Silakan deskripsikan jenis surat yang ingin Anda buat" in txt
    )
    if not is_generic_stub:
        return strip_emojis(txt)
    hist = []
    if thread is not None:
        try:
            hist = list(
                thread.messages.order_by("created_at").values("sender", "message")
            )
        except Exception:
            hist = []
    stu_info = {}
    if student is not None:
        stu_info = {
            "nama": getattr(getattr(student, "user", None), "nama", "-"),
            "nim": getattr(student, "nim", "-"),
            "prodi": getattr(getattr(student, "prodi", None), "nama_prodi", "-"),
            "semester": getattr(student, "semester_aktif", "-"),
        }
    smart = generate_conversational_reply(
        user_message=user_message,
        history_messages=hist,
        student_info=stu_info,
    )
    return strip_emojis(smart or txt)
