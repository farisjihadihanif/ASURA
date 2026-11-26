import logging
import os
from enum import Enum
from typing import List, Optional, Dict, Any
from django.conf import settings
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from .campus_catalog import ensure_campus_surat_types
from .detect_intent import detect_intent_dynamically
logger = logging.getLogger(__name__)
class IntentCategoryEnum(str, Enum):
    OFFICIAL_LETTER = "OFFICIAL_LETTER"
    AMBIGUOUS = "AMBIGUOUS"
    OUT_OF_CONTEXT = "OUT_OF_CONTEXT"
    GREETING_OR_CHITCHAT = "GREETING_OR_CHITCHAT"
class ExtractedSlotItem(BaseModel):
    key: str = Field(description="Nama field parameter seperti instansi_tujuan, keperluan_surat, tanggal_mulai, tanggal_selesai, judul_surat")
    value: str = Field(description="Nilai parameter yang diekstrak dari pesan atau lampiran")
class IntentRouterOutput(BaseModel):
    category: IntentCategoryEnum
    kode_surat: Optional[str] = None
    candidate_kodes: List[str] = Field(default_factory=list)
    detected_document_summary: Optional[str] = None
    explanation_or_response: str = ""
    extracted_items: List[ExtractedSlotItem] = Field(default_factory=list)
    @property
    def extracted_parameters(self) -> Dict[str, Any]:
        return {item.key: item.value for item in self.extracted_items if item.key and item.value}
def _fallback_local_route(cleaned_msg: str) -> IntentRouterOutput:
    lower = cleaned_msg.lower()
    if any(q in lower for q in ("apa aja", "apa saja", "jenis surat", "daftar surat", "bisa buat surat apa", "surat apa")):
        from surat.models import SuratType
        daftar = "\n".join(f"- **{s.nama_surat}** (`{s.kode_surat}`)" for s in SuratType.objects.all().order_by("kategori", "nama_surat"))
        return IntentRouterOutput(
            category=IntentCategoryEnum.GREETING_OR_CHITCHAT,
            explanation_or_response=(
                "ASURA dapat membantu membuatkan berbagai surat akademik resmi maupun surat permohonan/keterangan lainnya, antara lain:\n\n"
                f"{daftar}\n\n"
                "Silakan ketik jenis surat yang ingin Anda buat (misal: *Saya ingin membuat Surat Permohonan Izin Magang*)."
            ),
        )
    if any(g in lower for g in ("halo", "hai", "selamat pagi", "selamat siang", "selamat sore", "selamat malam", "assalamualaikum")) and len(lower.split()) <= 4:
        return IntentRouterOutput(
            category=IntentCategoryEnum.GREETING_OR_CHITCHAT,
            explanation_or_response="Halo! Saya ASURA. Silakan sebutkan jenis surat yang ingin Anda buat beserta detail keperluannya.",
        )
    kode = detect_intent_dynamically(cleaned_msg) or "CUSTOM-UMUM"
    return IntentRouterOutput(
        category=IntentCategoryEnum.OFFICIAL_LETTER,
        kode_surat=kode,
        extracted_items=[ExtractedSlotItem(key="judul_surat", value=cleaned_msg[:120])],
    )
def route_intent_with_ai(user_message: str, attachments: Optional[List[Any]] = None) -> IntentRouterOutput:
    ensure_campus_surat_types()
    cleaned_msg = (user_message or "").strip()
    api_key = getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        return _fallback_local_route(cleaned_msg)
    from surat.models import SuratType
    surat_types = list(SuratType.objects.all())
    catalog_text = "\n".join(f"- {s.kode_surat}: {s.nama_surat}" for s in surat_types)
    try:
        client = genai.Client(api_key=str(api_key).strip())
        model_name = getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.5-flash")
        prompt = f"""Klasifikasikan permintaan surat mahasiswa berikut ke salah satu kode katalog yang tersedia.
Jika mahasiswa meminta jenis surat di luar daftar spesifik, gunakan kode "CUSTOM-UMUM" dan isi key "judul_surat" dengan nama surat yang diminta.
Katalog Surat:
{catalog_text}
Pesan Mahasiswa:
"{cleaned_msg}"
"""
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=IntentRouterOutput,
                temperature=0.1,
            ),
        )
        parsed = IntentRouterOutput.model_validate_json(resp.text)
        valid_kodes = {s.kode_surat for s in surat_types}
        if parsed.category == IntentCategoryEnum.OFFICIAL_LETTER:
            if not parsed.kode_surat or parsed.kode_surat not in valid_kodes:
                parsed.kode_surat = "CUSTOM-UMUM"
        return parsed
    except Exception as exc:
        logger.warning("Fallback router lokal aktif: %s", exc)
        return _fallback_local_route(cleaned_msg)

