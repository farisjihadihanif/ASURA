"""Asisten revisi: membantu mahasiswa melengkapi atau memperbaiki data draf surat lalu menerbitkan ulang."""
import json
import os
import re
import threading
from logging import getLogger
from typing import Dict, List, Optional

from django.conf import settings

from .conversational_ai import strip_emojis

logger = getLogger(__name__)

RESUBMIT_PATTERN = re.compile(
    r"\b(ajukan|ajuin|kirim|submit|proses|buat|terbitkan)\s*(ulang|lagi|kembali)\b"
    r"|\b(ulang(i)?|revisi)\s+(sekarang|aja|saja)\b"
    r"|^\s*(ya|iya|oke|ok|siap|lanjut(kan)?|setuju|betul|benar|kirim|gas)\b[\s.!]*$",
    re.IGNORECASE,
)
QUESTION_PATTERN = re.compile(
    r"\?|\b(apa|apakah|bagaimana|gimana|kenapa|mengapa|maksud(nya)?|berarti|harus|perlu)\b",
    re.IGNORECASE,
)


def _api_key() -> str:
    return (
        getattr(settings, "GEMINI_API_KEY", None)
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip()


def _gemini_json(system_instruction: str, prompt: str) -> Optional[dict]:
    key = _api_key()
    if not key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        models = [getattr(settings, "GEMINI_MODEL_NAME", None), "gemini-2.5-flash", "gemini-2.0-flash"]
        seen = set()
        for name in [m for m in models if m and not (m in seen or seen.add(m))]:
            try:
                resp = client.models.generate_content(
                    model=name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3,
                        response_mime_type="application/json",
                    ),
                )
                raw = (getattr(resp, "text", "") or "").strip()
                raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
    except Exception:
        logger.exception("Gemini revisi gagal")
    return None


def latest_revision_note(surat_req) -> str:
    notes = [n for n in (surat_req.revision_notes or []) if isinstance(n, str) and n.strip()]
    approval = surat_req.approvals.exclude(catatan__isnull=True).exclude(catatan="").order_by("-id").first()
    if approval and approval.catatan:
        return approval.catatan.strip()
    return notes[-1].strip() if notes else "Mohon perbaiki detail permohonan surat Anda."


def _context(surat_req) -> str:
    payload = surat_req.payload_data or {}
    try:
        payload_txt = json.dumps(payload, ensure_ascii=False)[:1500]
    except Exception:
        payload_txt = str(payload)[:1500]
    return (
        f"Jenis surat: {surat_req.kode_surat.nama_surat}\n"
        f"Data permohonan saat ini: {payload_txt}\n"
        f"Draf saat ini (ringkas): {(surat_req.ai_original_draft or '')[:1200]}\n"
        f"Catatan perbaikan: {latest_revision_note(surat_req)}"
    )


_SYSTEM = (
    "Kamu adalah ASURA, asisten persuratan kampus. Draf surat mahasiswa masih memerlukan perbaikan atau kelengkapan data. "
    "Tugasmu: (1) jelaskan secara konkret apa yang perlu diubah berdasarkan catatan perbaikan dan data permohonan, "
    "beri contoh nilai perbaikan yang masuk akal (mis. durasi lebih singkat atau detail instansi), dan tanyakan nilai yang diinginkan mahasiswa bila perlu; "
    "(2) bila mahasiswa sudah menyebut perbaikan konkret atau meminta terbitkan ulang, tandai ready_to_resubmit=true "
    "dan rangkum instruksi perbaikan di correction_summary (gabungkan catatan perbaikan dan permintaan mahasiswa). "
    "Gaya bahasa: Indonesia, ringkas, tanpa emoji, tanpa pembuka klise. "
    'Balas HANYA JSON: {"reply": str, "ready_to_resubmit": bool, "correction_summary": str}'
)


def generate_guidance(surat_req) -> str:
    """Panduan proaktif setelah draf membutuhkan revisi kelengkapan."""
    data = _gemini_json(
        _SYSTEM,
        f"{_context(surat_req)}\n\nPesan mahasiswa: (belum ada) Berikan panduan awal apa saja yang harus dilengkapi/direvisi "
        "dan beri tahu cara memproses ulang (balas dengan perbaikan, lalu ketik 'terbitkan ulang').",
    )
    if data and data.get("reply"):
        return strip_emojis(str(data["reply"]))
    return strip_emojis(
        f"Yang perlu kamu perbaiki: {latest_revision_note(surat_req)}\n\n"
        "Balas di sini dengan perbaikan yang kamu inginkan (misalnya data yang diubah), "
        "lalu ketik \"terbitkan ulang\" supaya surat disusun ulang dan langsung diterbitkan otomatis."
    )


def post_guidance_async(surat_request_id: int) -> None:
    def _run():
        from django.db import close_old_connections
        from ..models import ChatMessage, SuratRequest

        close_old_connections()
        try:
            req = SuratRequest.objects.select_related("kode_surat", "chat_thread").get(pk=surat_request_id)
            if not req.chat_thread or req.status != "REVISION_REQUIRED":
                return
            ChatMessage.objects.create(
                thread=req.chat_thread,
                sender="assistant",
                message=generate_guidance(req),
                slots_snapshot={"event": "REVISION_GUIDANCE", "surat_request_id": req.id},
            )
            req.chat_thread.save(update_fields=["updated_at"])
        except Exception:
            logger.exception("Gagal mengirim panduan revisi")
        finally:
            close_old_connections()

    threading.Thread(target=_run, daemon=True).start()


def find_pending_revision(thread_id) -> Optional[object]:
    from ..models import SuratRequest

    latest = (
        SuratRequest.objects.filter(chat_thread_id=thread_id)
        .select_related("kode_surat", "student", "student__user", "student__prodi", "student__fakultas")
        .order_by("-id")
        .first()
    )
    if latest and latest.status == "REVISION_REQUIRED":
        return latest
    return None


def _student_messages_since_revision(surat_req, thread) -> List[str]:
    msgs = list(thread.messages.order_by("created_at").values("sender", "message", "slots_snapshot"))
    start = 0
    for i, m in enumerate(msgs):
        snap = m.get("slots_snapshot") or {}
        if isinstance(snap, dict) and snap.get("event") == "REVISION_REQUIRED" and snap.get("surat_request_id") == surat_req.id:
            start = i + 1
    return [m["message"] for m in msgs[start:] if m["sender"] == "user" and m.get("message")]


def _start_redraft(surat_req, instruction: str) -> None:
    from ..models import SuratStatus
    from ..views import _execute_redraft_agent_worker

    student = surat_req.student
    previous_payload = dict(surat_req.payload_data or {})
    meta = {
        "nim": student.nim,
        "nama": getattr(student.user, "nama", ""),
        "prodi": getattr(student.prodi, "nama_prodi", ""),
        "fakultas": getattr(student.fakultas, "nama_fakultas", ""),
        "semester_aktif": student.semester_aktif,
        "tahun_akademik": student.tahun_akademik,
    }
    surat_req.user_prompt_context = f"{surat_req.user_prompt_context or ''}\n\n[Revisi]: {instruction}".strip()
    surat_req.status = SuratStatus.SUBMITTED
    surat_req.save(update_fields=["user_prompt_context", "status"])
    threading.Thread(
        target=_execute_redraft_agent_worker,
        kwargs={
            "surat_request_id": surat_req.id,
            "user_prompt_context": instruction,
            "kode_surat": surat_req.kode_surat.kode_surat,
            "previous_draft": surat_req.ai_original_draft or "",
            "previous_payload": previous_payload,
            "previous_score": int(surat_req.self_critique_score or 0),
            "revision_notes": list(surat_req.revision_notes or []),
            "student_metadata": meta,
            "agent": None,
        },
        daemon=True,
    ).start()


def handle_revision_message(surat_req, thread, user_message: str) -> str:
    """Balasan untuk chat mahasiswa ketika surat terakhirnya berstatus REVISION_REQUIRED."""
    msg = (user_message or "").strip()
    note = latest_revision_note(surat_req)
    prior = _student_messages_since_revision(surat_req, thread)
    # pesan saat ini mungkin sudah tersimpan sebagai pesan terakhir; hindari duplikasi
    if prior and prior[-1].strip() == msg:
        prior = prior[:-1]
    wants_resubmit = bool(RESUBMIT_PATTERN.search(msg))

    history = "\n".join(f"Mahasiswa: {p}" for p in prior[-6:])
    data = _gemini_json(
        _SYSTEM,
        f"{_context(surat_req)}\n\nPerbaikan yang sudah disebut mahasiswa sebelumnya:\n{history or '-'}\n\n"
        f"Pesan mahasiswa sekarang: {msg}",
    )

    ready = wants_resubmit
    summary = ""
    reply = ""
    if data:
        reply = strip_emojis(str(data.get("reply") or ""))
        summary = str(data.get("correction_summary") or "").strip()
        ready = bool(data.get("ready_to_resubmit")) or wants_resubmit
        if QUESTION_PATTERN.search(msg) and not wants_resubmit:
            ready = False

    if not ready:
        if reply:
            return reply
        if QUESTION_PATTERN.search(msg):
            return strip_emojis(
                f"Catatan perbaikan: {note}\n\nArtinya data permohonanmu perlu disesuaikan dengan catatan itu. "
                "Tulis perbaikan yang kamu mau (misalnya nilai/tanggal/detail baru), lalu ketik \"terbitkan ulang\"."
            )
        return strip_emojis(
            f"Oke, perbaikan kamu saya catat: \"{msg}\".\n"
            "Kalau sudah cukup, ketik \"terbitkan ulang\" supaya surat disusun ulang dan langsung diterbitkan otomatis."
        )

    corrections = [p for p in prior if not RESUBMIT_PATTERN.search(p)]
    if not wants_resubmit:
        corrections.append(msg)
    instruction = summary or "; ".join(corrections) or f"Perbaiki sesuai catatan: {note}"
    if note and note not in instruction:
        instruction = f"{instruction}. Catatan perbaikan yang harus dipenuhi: {note}"
    _start_redraft(surat_req, instruction)
    return strip_emojis(
        "Baik, revisi kamu sudah saya terapkan. Surat sedang disusun ulang untuk segera diterbitkan otomatis. "
        "Pantau statusnya di kartu surat atau lewat notifikasi."
    )
