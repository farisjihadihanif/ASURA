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
    for st in SuratType.objects.all().order_by("kategori", "nama_surat"):
        if st.kode_surat == "CUSTOM-UMUM":
            continue
        desc = (getattr(st, "deskripsi", "") or getattr(st, "keterangan", "") or "").strip()
        if desc:
            lines.append(f"- {st.nama_surat} ({st.kode_surat}): {desc}")
        else:
            lines.append(f"- {st.nama_surat} ({st.kode_surat})")
    return lines
def generate_conversational_reply(
    user_message: str,
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
            f"{'Mahasiswa' if m.get('sender') == 'user' else 'ASURA'}: {m.get('text', '')}"
            for m in recent
            if m.get("text")
        )
    mhs_ctx = ""
    if student_info:
        mhs_ctx = (
            f"Data mahasiswa yang sedang login: Nama={student_info.get('nama', '-')}, "
            f"NIM={student_info.get('nim', '-')}, Prodi={student_info.get('prodi', '-')}, "
            f"Semester={student_info.get('semester', '-')}."
        )
    system_instruction = (
        "Kamu adalah ASURA, asisten persuratan akademik kampus yang cerdas, ringkas, dan membantu.\n"
        f"{mhs_ctx}\n\n"
        "Daftar jenis surat resmi kampus yang tersedia di sistem saat ini:\n"
        f"{catalog_text}\n\n"
        "Kemampuan tambahan penting:\n"
        "- Selain daftar surat standar di atas, kamu JUGA BISA membuatkan SURAT CUSTOM (surat bebas sesuai kebutuhan mahasiswa, misalnya surat izin kegiatan, surat pernyataan, surat pengantar khusus, surat dispensasi, atau surat permohonan lainnya).\n"
        "- Alur kerja: kumpulkan detail keperluan surat dari mahasiswa -> susun draf -> kirim ke dosen untuk ACC -> setelah ACC bisa dikirim ke email atau dicetak ke printer.\n\n"
        "ATURAN GAYA BAHASA (WAJIB DIPATUHI):\n"
        "1. Jawab langsung ke inti pertanyaan mahasiswa secara natural seperti staf akademik yang ramah dan sigap.\n"
        "2. DILARANG KERAS menggunakan emoji atau emotikon apa pun.\n"
        "3. DILARANG memakai kalimat pembuka template AI seperti 'Halo, saya adalah Asisten AI...', 'Tentu! Dengan senang hati...', atau 'Berikut adalah informasi yang Anda minta'.\n"
        "4. Jika mahasiswa menanyakan jenis surat apa saja yang bisa dibuat, tampilkan daftar surat di atas secara rapi dan tegaskan bahwa kamu juga bisa membuatkan Surat Custom sesuai kebutuhan mereka."
    )
    prompt = (
        f"Riwayat percakapan sebelumnya:\n{history_text}\n\n"
        f"Pesan terbaru mahasiswa: {user_message}\n\n"
        "Berikan jawaban yang relevan, spesifik, dan langsung membantu:"
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
    daftar_ringkas = "\n".join(line.split(":")[0] for line in catalog_lines)
    return strip_emojis(
        "Saya bisa membantu membuatkan berbagai surat resmi kampus berikut:\n\n"
        f"{daftar_ringkas}\n\n"
        "Selain jenis surat di atas, saya juga bisa membuatkan **Surat Custom** sesuai kebutuhan spesifik kamu "
        "(seperti surat izin kegiatan, surat pernyataan, dispensasi, atau surat pengantar khusus).\n\n"
        "Sebutkan saja jenis surat dan keperluannya, nanti langsung saya siapkan drafnya."
    )
