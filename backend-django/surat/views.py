from .services.conversational_ai import upgrade_static_assistant_reply
import base64
import logging
import os
import threading
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import close_old_connections
from rest_framework import permissions, status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import CustomJWTAuthentication
from accounts.models import Lecturer, Student

from .agents.backend_bridge import persist_attachments_for_request
from .agents.letter_agent import (
    SuratAgentError,
    SuratAgentRateLimitError,
    SuratAgentTimeoutError,
    SuratDraftingAgent,
)
from .models import (
    ApprovalStatus,
    SuratApproval,
    SuratAuditLog,
    SuratRequest,
    SuratStatus,
    SuratType,
    TteSignature,
    ChatThread,
    ChatMessage,
    Notification,
)
from .serializers import (
    SuratApprovalActionSerializer,
    SuratRequestCreateSerializer,
    SuratRequestDetailSerializer,
    SuratRequestListSerializer,
    SuratTypeSerializer,
    ReDraftSuratRequestSerializer,
)
from .services.workflow_service import process_approval_action
from .services.manual_handlers import create_approval_workflow_for_request
from .services.session_manager import AutoSuratSessionManager
from .services.notifications import notify_user
from .services.eligibility import check_eligibility

logger = logging.getLogger(__name__)


def _mark_surat_request_failed(surat_request_id: int, error_code: str, error_reason: str) -> None:
    try:
        surat_req = SuratRequest.objects.filter(pk=surat_request_id).first()
        if surat_req is not None:
            existing_notes = list(surat_req.revision_notes) if isinstance(surat_req.revision_notes, list) else []
            existing_notes.append(error_reason)
            surat_req.status = SuratStatus.FAILED
            surat_req.revision_notes = existing_notes
            surat_req.save(update_fields=["status", "revision_notes"])
            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id=error_code[:100],
                action=f"AI_DRAFT_FAILED: {error_reason}"[:255],
            )
    except Exception as db_exc:
        logger.error("Gagal memperbarui status FAILED untuk SuratRequest id=%s: %s", surat_request_id, db_exc)


def _execute_drafting_agent_worker(
    surat_request_id: int,
    user_prompt_context: str,
    kode_surat: str,
    student_metadata: Optional[Dict[str, Any]] = None,
    agent: Optional[SuratDraftingAgent] = None,
    dynamic_fields_dict: Optional[Dict[str, Any]] = None,
) -> None:
    close_old_connections()
    try:
        surat_req_init = SuratRequest.objects.filter(pk=surat_request_id).first()
        initial_payload = (
            dict(surat_req_init.payload_data)
            if surat_req_init is not None and isinstance(surat_req_init.payload_data, dict) and surat_req_init.payload_data
            else None
        )

        active_agent = agent if agent is not None else SuratDraftingAgent()
        draft_output = active_agent.draft_letter(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            student_metadata=student_metadata,
            previous_payload=initial_payload,
            dynamic_fields_dict=dynamic_fields_dict,
        )

        if hasattr(draft_output, "to_payload_dict") and callable(draft_output.to_payload_dict):
            structured_payload: Dict[str, Any] = draft_output.to_payload_dict()
        elif hasattr(draft_output, "extracted_payload"):
            payload_obj = draft_output.extracted_payload
            structured_payload = (
                payload_obj.model_dump(mode="json")
                if hasattr(payload_obj, "model_dump")
                else dict(payload_obj)
            )
        else:
            structured_payload = dict(initial_payload or {})

        surat_req = SuratRequest.objects.select_related(
            "student", "student__user", "student__prodi", "student__fakultas", "kode_surat"
        ).get(pk=surat_request_id)
        surat_req.payload_data = structured_payload
        surat_req.ai_original_draft = draft_output.ai_original_draft
        surat_req.self_critique_score = draft_output.evaluation.self_critique_score
        surat_req.revision_notes = list(draft_output.evaluation.revision_notes)

        critique_score = draft_output.evaluation.self_critique_score
        has_missing_info = getattr(draft_output.evaluation, "has_missing_info", False)

        if critique_score < 7 or has_missing_info:
            surat_req.status = SuratStatus.REVISION_REQUIRED
            surat_req.save(
                update_fields=[
                    "payload_data",
                    "ai_original_draft",
                    "self_critique_score",
                    "revision_notes",
                    "status",
                ]
            )
            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id="AI_REV_REQ",
                action="AI_DRAFTING_LOW_QUALITY_SCORE",
            )
            return

        surat_req.status = SuratStatus.PENDING_APPROVAL
        surat_req.save(
            update_fields=[
                "payload_data",
                "ai_original_draft",
                "self_critique_score",
                "revision_notes",
                "status",
            ]
        )

        if str(surat_req.kode_surat.kode_surat or "").upper().startswith("CUSTOM"):
            # Surat custom bersifat pribadi: tidak masuk antrean dosen dan tidak ada notifikasi ke dosen.
            SuratApproval.objects.filter(surat_request=surat_req).delete()
            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id="AI_02",
                action="CUSTOM_LETTER_READY_NO_APPROVAL",
            )
            return

        create_approval_workflow_for_request(surat_req, surat_req.student)

        for app_step in SuratApproval.objects.filter(
            surat_request=surat_req, status=ApprovalStatus.PENDING
        ).select_related("approver__user"):
            notify_user(
                app_step.approver.user,
                "APPROVAL_REQUIRED",
                f"Permohonan Baru: {surat_req.kode_surat.nama_surat}",
                f"Mahasiswa {surat_req.student.user.nama} ({surat_req.student.nim}) mengajukan {surat_req.kode_surat.nama_surat}.",
                surat_req,
            )

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="AI_02",
            action="AI_DRAFT_COMPLETED_PENDING_APPROVAL",
        )
    except (SuratAgentTimeoutError, SuratAgentRateLimitError) as exc:
        _mark_surat_request_failed(surat_request_id, "AI_ERR_LIMIT", f"{type(exc).__name__}: {exc}")
    except SuratAgentError as exc:
        _mark_surat_request_failed(surat_request_id, "AI_ERR_AGENT", f"{type(exc).__name__}: {exc}")
    except Exception as exc:
        logger.exception("Kesalahan tak terduga saat menyusun draf surat id=%s: %s", surat_request_id, exc)
        _mark_surat_request_failed(surat_request_id, "AI_ERR_UNEXPECTED", f"{type(exc).__name__}: {exc}")
    finally:
        close_old_connections()


def _execute_redraft_agent_worker(
    surat_request_id: int,
    user_prompt_context: str,
    kode_surat: str,
    previous_draft: str,
    previous_payload: dict,
    previous_score: int,
    revision_notes: list,
    student_metadata: dict,
    agent: Optional[SuratDraftingAgent] = None,
) -> None:
    close_old_connections()
    try:
        surat_req = SuratRequest.objects.get(pk=surat_request_id)
        active_agent = agent if agent is not None else SuratDraftingAgent()
        draft_output = active_agent.draft_letter_with_reflection(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            previous_draft=previous_draft,
            previous_payload=previous_payload,
            previous_score=previous_score,
            revision_notes=revision_notes,
            student_metadata=student_metadata,
        )

        from .agents import evaluate_draft_readiness, ensure_approval_queue_for_request

        readiness = evaluate_draft_readiness(
            draft_output=draft_output,
            kode_surat=kode_surat,
            agent=active_agent,
        )

        surat_req.payload_data = readiness["structured_payload"]
        surat_req.ai_original_draft = getattr(draft_output, "ai_original_draft", "")
        surat_req.self_critique_score = readiness["critique_score"]
        surat_req.revision_notes = readiness["revision_notes"]

        if readiness["is_ready_for_approval"]:
            surat_req.status = SuratStatus.PENDING_APPROVAL
            action_code = "AI_REDRAFT_SUCCESS_PENDING_APPROVAL"
        else:
            surat_req.status = SuratStatus.REVISION_REQUIRED
            action_code = "AI_REDRAFT_STILL_INCOMPLETE"

        surat_req.save(
            update_fields=[
                "payload_data",
                "ai_original_draft",
                "self_critique_score",
                "revision_notes",
                "status",
            ]
        )

        if surat_req.status == SuratStatus.PENDING_APPROVAL and not str(surat_req.kode_surat.kode_surat or "").upper().startswith("CUSTOM"):
            # Hapus antrean lama agar pengajuan ulang tidak menggandakan approval.
            SuratApproval.objects.filter(surat_request=surat_req).delete()
            create_approval_workflow_for_request(surat_req, surat_req.student)
            ensure_approval_queue_for_request(surat_req)
            for app_step in SuratApproval.objects.filter(
                surat_request=surat_req, status=ApprovalStatus.PENDING
            ).select_related("approver__user"):
                notify_user(
                    app_step.approver.user,
                    "APPROVAL_REQUIRED",
                    f"Revisi Diajukan Ulang: {surat_req.kode_surat.nama_surat}",
                    f"Mahasiswa {surat_req.student.user.nama} ({surat_req.student.nim}) mengajukan ulang surat setelah revisi.",
                    surat_req,
                )

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="AI_02",
            action=action_code,
        )
    except Exception as exc:
        _mark_surat_request_failed(surat_request_id, "AI_REDRAFT_ERR", f"{type(exc).__name__}: {exc}")
    finally:
        close_old_connections()


class ChatThreadCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def post(self, request):
        title = request.data.get("title", "Permohonan Surat Baru")
        document_type = request.data.get("document_type", None)

        thread = ChatThread.objects.create(
            user=request.user,
            title=title,
            document_type=document_type,
            status=ChatThread.ThreadStatus.ACTIVE,
        )

        AutoSuratSessionManager.save_session(
            thread_id=str(thread.id),
            state="COLLECTING_SLOTS",
            intent=document_type,
            slots={},
            missing_slots=[],
        )

        return Response(
            {
                "status": "success",
                "message": "Sesi chat (thread) berhasil diinisialisasi.",
                "initial_message": "Halo, saya adalah ASURA. Silakan deskripsikan jenis surat yang ingin Anda buat beserta detail keperluannya.",
                "thread_id": str(thread.id),
                "title": thread.title,
                "document_type": thread.document_type,
                "created_at": thread.created_at,
            },
            status=status.HTTP_201_CREATED,
        )


class ChatThreadListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def get(self, request):
        threads = ChatThread.objects.filter(user=request.user).order_by("-updated_at")[:50]
        return Response(
            [
                {
                    "thread_id": str(thread.id),
                    "title": thread.title,
                    "document_type": thread.document_type,
                    "status": thread.status,
                    "updated_at": thread.updated_at,
                    "created_at": thread.created_at,
                }
                for thread in threads
            ],
            status=status.HTTP_200_OK,
        )


class NotificationListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def get(self, request):
        queryset = Notification.objects.filter(user=request.user)
        if hasattr(request.user, 'lecturer_profile'):
            queryset = queryset.exclude(surat_request__kode_surat__kode_surat__startswith='CUSTOM')
        if request.query_params.get('unread') == '1':
            queryset = queryset.filter(is_read=False)
        return Response(
            [
                {
                    'id': item.id,
                    'type': item.type,
                    'title': item.title,
                    'body': item.body,
                    'surat_request_id': item.surat_request_id,
                    'is_read': item.is_read,
                    'created_at': item.created_at,
                }
                for item in queryset[:50]
            ]
        )


class NotificationUnreadCountAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def get(self, request):
        qs = Notification.objects.filter(user=request.user, is_read=False)
        if hasattr(request.user, 'lecturer_profile'):
            qs = qs.exclude(surat_request__kode_surat__kode_surat__startswith='CUSTOM')
        return Response({'count': qs.count()})


class NotificationReadAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def post(self, request, notification_id):
        updated = Notification.objects.filter(id=notification_id, user=request.user).update(is_read=True)
        if not updated:
            return Response({'message': 'Notifikasi tidak ditemukan.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'success'})


class NotificationReadAllAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'success'})


class ChatSessionMessageAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, thread_id):
        user_msg = request.data.get("message", "").strip()
        attachment_files = request.FILES.getlist('attachments')

        if not user_msg and not attachment_files:
            # === ASURA_CONVERSATIONAL_UPGRADE ===
            try:
                _last_ai = thread.messages.filter(sender='assistant').order_by('-created_at').first()
                _stu_obj = getattr(request.user, 'student_profile', None) or getattr(thread, 'student', None)
                _raw_msg = str(request.data.get('message') or request.data.get('text') or '')
                if _last_ai:
                    _upgraded = upgrade_static_assistant_reply(_last_ai.message, _raw_msg, thread=thread, student=_stu_obj)
                    if _upgraded and _upgraded != _last_ai.message:
                        _last_ai.message = _upgraded
                        _last_ai.save(update_fields=['message'])
            except Exception:
                pass
            return Response(
                {"status": "error", "message": "Pesan atau berkas lampiran tidak boleh kosong."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        thread = ChatThread.objects.filter(id=thread_id, user=request.user).first()
        if not thread:
            return Response(
                {"status": "error", "message": "Sesi chat atau thread tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND,
            )

        multimodal_parts = []
        if attachment_files:
            try:
                multimodal_parts = persist_attachments_for_request(None, attachment_files)
            except Exception as exc:
                logger.warning("Gagal mengekstrak berkas lampiran multimodal: %s", exc)

        if not user_msg and attachment_files:
            file_names = ", ".join(getattr(f, "name", "berkas") for f in attachment_files)
            user_msg = f"Berikut dokumen lampiran pendukung yang saya unggah: {file_names}"

        reply_message = AutoSuratSessionManager.handle_incoming_message(
            thread_id=str(thread.id),
            user_message=user_msg,
            user_obj=request.user,
            attachments=multimodal_parts or attachment_files,
        )

        session_data = AutoSuratSessionManager.get_session(str(thread.id))
        if session_data.get("state") in ["CANCELLED", "EXPIRED"]:
            return Response(
                {
                    "status": "success",
                    "state": session_data["state"],
                    "reply": reply_message,
                },
                status=status.HTTP_200_OK,
            )

        intent = session_data.get("intent")
        slots = session_data.get("slots", {})
        waiting_confirmation = session_data.get("is_waiting_for_switch_confirmation", False)

        from .services.chat_workflow import get_effective_required_fields

        required_fields = []
        if intent:
            try:
                surat_type_obj = SuratType.objects.get(kode_surat=intent)
                required_fields = get_effective_required_fields(surat_type_obj)
            except SuratType.DoesNotExist:
                pass

        main_slots_complete = bool(intent and required_fields) and all(
            item.get("field") in slots and bool(slots[item.get("field")])
            for item in required_fields
        )
        surat_is_complete = not waiting_confirmation and main_slots_complete

        waiting_clarification = session_data.get("is_waiting_for_intent_clarification", False)
        candidate_intents = session_data.get("candidate_intents", [])

        action_required = None
        action_options = []
        if waiting_confirmation:
            action_required = "switch_confirmation"
            action_options = [
                {"label": "Ya, Beralih Surat", "value": "Ya"},
                {"label": "Tidak, Lanjutkan Sebelumnya", "value": "Tidak"},
            ]
        elif waiting_clarification and candidate_intents:
            action_required = "intent_clarification"
            for c in candidate_intents:
                try:
                    surat_type_obj = SuratType.objects.get(kode_surat=c)
                    lbl = f"{surat_type_obj.nama_surat} ({c})"
                except Exception:
                    lbl = c
                action_options.append({"label": lbl, "value": c})

        missing_fields = (
            [
                item.get("field")
                for item in required_fields
                if not (item.get("field") in slots and bool(slots[item.get("field")]))
            ]
            if required_fields
            else []
        )

        if surat_is_complete:
            return Response(
                {
                    "status": "ready_to_draft",
                    "state": "READY_TO_DRAFT",
                    "is_ready_to_draft": True,
                    "action_required": None,
                    "action_options": [],
                    "intent": intent,
                    "detected_intent": intent,
                    "kode_surat": intent,
                    "is_waiting_for_switch_confirmation": False,
                    "collected_slots": slots,
                    "missing_fields": [],
                    "required_fields": required_fields,
                    "reply": reply_message,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": "success",
                "state": "COLLECTING_SLOTS",
                "is_ready_to_draft": False,
                "action_required": action_required,
                "action_options": action_options,
                "intent": intent,
                "detected_intent": intent,
                "kode_surat": intent,
                "is_waiting_for_switch_confirmation": waiting_confirmation,
                "is_waiting_for_intent_clarification": waiting_clarification,
                "reply": reply_message,
                "collected_slots": slots,
                "missing_fields": missing_fields,
                "required_fields": required_fields,
            },
            status=status.HTTP_200_OK,
        )

    def get(self, request, thread_id):
        thread = ChatThread.objects.filter(id=thread_id, user=request.user).first()
        if not thread:
            return Response(
                {"status": "error", "message": "Sesi chat atau thread tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND,
            )

        session_data = AutoSuratSessionManager.get_session(str(thread.id))
        intent = session_data.get("intent") or thread.document_type
        slots = session_data.get("slots", {})
        waiting_confirmation = session_data.get("is_waiting_for_switch_confirmation", False)

        from .services.chat_workflow import get_effective_required_fields

        required_fields = []
        if intent:
            try:
                surat_type_obj = SuratType.objects.get(kode_surat=intent)
                required_fields = get_effective_required_fields(surat_type_obj)
            except SuratType.DoesNotExist:
                pass

        main_slots_complete = bool(intent and required_fields) and all(
            item.get("field") in slots and bool(slots[item.get("field")])
            for item in required_fields
        )
        surat_is_complete = not waiting_confirmation and main_slots_complete

        waiting_clarification = session_data.get("is_waiting_for_intent_clarification", False)
        candidate_intents = session_data.get("candidate_intents", [])

        action_required = None
        action_options = []
        if waiting_confirmation:
            action_required = "switch_confirmation"
            action_options = [
                {"label": "Ya, Beralih Surat", "value": "Ya"},
                {"label": "Tidak, Lanjutkan Sebelumnya", "value": "Tidak"},
            ]
        elif waiting_clarification and candidate_intents:
            action_required = "intent_clarification"
            for c in candidate_intents:
                try:
                    surat_type_obj = SuratType.objects.get(kode_surat=c)
                    lbl = f"{surat_type_obj.nama_surat} ({c})"
                except Exception:
                    lbl = c
                action_options.append({"label": lbl, "value": c})

        missing_fields = (
            [
                item.get("field")
                for item in required_fields
                if not (item.get("field") in slots and bool(slots[item.get("field")]))
            ]
            if required_fields
            else []
        )

        messages = ChatMessage.objects.filter(thread=thread).order_by('created_at')
        formatted_messages = [
            {
                "id": str(msg.id),
                "sender": msg.sender,
                "text": msg.message,
                "timestamp": msg.created_at.strftime("%H:%M") if msg.created_at else "",
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "slots_snapshot": msg.slots_snapshot,
            }
            for msg in messages
        ]

        latest_req = thread.surat_requests.order_by("-created_at").first()
        state = "READY_TO_DRAFT" if surat_is_complete else session_data.get("state", "COLLECTING_SLOTS")
        status_str = "ready_to_draft" if surat_is_complete else "success"

        return Response(
            {
                "status": status_str,
                "state": state,
                "is_ready_to_draft": surat_is_complete,
                "action_required": action_required,
                "action_options": action_options,
                "is_waiting_for_switch_confirmation": waiting_confirmation,
                "is_waiting_for_intent_clarification": waiting_clarification,
                "thread_id": str(thread.id),
                "title": thread.title,
                "intent": intent,
                "detected_intent": intent,
                "kode_surat": intent,
                "collected_slots": slots,
                "missing_fields": missing_fields,
                "required_fields": required_fields,
                "messages": formatted_messages,
                "latest_surat_request": SuratRequestDetailSerializer(latest_req).data if latest_req else None,
            },
            status=status.HTTP_200_OK,
        )


    def delete(self, request, thread_id):
        thread = ChatThread.objects.filter(id=thread_id, user=request.user).first()
        if not thread:
            return Response(
                {"status": "error", "message": "Riwayat chat tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND,
            )
        thread.delete()
        return Response({"status": "success", "message": "Riwayat chat berhasil dihapus."}, status=status.HTTP_200_OK)
class SuratRequestRedraftAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    agent_instance: Optional[SuratDraftingAgent] = None

    def get_drafting_agent(self) -> Optional[SuratDraftingAgent]:
        return self.agent_instance

    def post(self, request, pk=None):
        try:
            student_obj = request.user.student_profile
        except (Student.DoesNotExist, AttributeError):
            return Response({"status": "error", "errors": "Bukan akun mahasiswa."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            surat_req = SuratRequest.objects.select_related("kode_surat", "student").get(pk=pk)
        except SuratRequest.DoesNotExist:
            return Response({"status": "error", "errors": "Permohonan surat tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)

        if surat_req.student != student_obj:
            return Response({"status": "error", "errors": "Akses ditolak."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReDraftSuratRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        additional_context = serializer.validated_data["additional_prompt_context"]
        combined_prompt = f"{surat_req.user_prompt_context or ''}\n\n[Tambahan Informasi Revisi]: {additional_context}".strip()

        previous_draft = surat_req.ai_original_draft or ""
        previous_payload = dict(surat_req.payload_data or {})
        raw_new_payload = serializer.validated_data.get("payload_data")
        if isinstance(raw_new_payload, dict) and raw_new_payload:
            previous_payload.update(raw_new_payload)

        student_metadata = {
            "nim": student_obj.nim,
            "nama": getattr(student_obj.user, "nama", ""),
            "prodi": getattr(student_obj.prodi, "nama_prodi", ""),
            "fakultas": getattr(student_obj.fakultas, "nama_fakultas", ""),
            "semester_aktif": student_obj.semester_aktif,
            "tahun_akademik": student_obj.tahun_akademik,
        }

        surat_req.user_prompt_context = combined_prompt
        surat_req.payload_data = previous_payload
        surat_req.status = SuratStatus.SUBMITTED
        surat_req.save(update_fields=["user_prompt_context", "payload_data", "status"])

        worker_thread = threading.Thread(
            target=_execute_redraft_agent_worker,
            kwargs={
                "surat_request_id": surat_req.id,
                "user_prompt_context": additional_context,
                "kode_surat": surat_req.kode_surat.kode_surat,
                "previous_draft": previous_draft,
                "previous_payload": previous_payload,
                "previous_score": int(surat_req.self_critique_score or 0),
                "revision_notes": list(surat_req.revision_notes or []),
                "student_metadata": student_metadata,
                "agent": self.get_drafting_agent(),
            },
            daemon=True,
        )
        worker_thread.start()

        return Response(
            {
                "status": "success",
                "message": "Revisi permohonan surat berhasil diterima dan diproses ulang oleh ASURA.",
                "request_id": surat_req.id,
                "surat_status": surat_req.status,
                "data": {"request_id": surat_req.id, "status": surat_req.status},
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def patch(self, request, pk=None):
        return self.post(request, pk=pk)


class SuratTypeListAPIView(ListAPIView):
    serializer_class = SuratTypeSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    def get_queryset(self):
        from .services.campus_catalog import ensure_campus_surat_types
        ensure_campus_surat_types()
        from django.db.models import Q
        from .services.campus_catalog import CATALOG_CODES
        # Hanya katalog kampus + surat custom; seed lama (mis. SK-KUL) tidak ditampilkan.
        return SuratType.objects.filter(
            Q(kode_surat__in=CATALOG_CODES) | Q(kode_surat__startswith='CUSTOM')
        ).order_by('kategori', 'nama_surat')


class SuratRequestCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    agent_instance: Optional[SuratDraftingAgent] = None

    def get_drafting_agent(self) -> Optional[SuratDraftingAgent]:
        return self.agent_instance

    def post(self, request):
        try:
            student_obj = request.user.student_profile
        except (Student.DoesNotExist, AttributeError):
            return Response(
                {"status": "error", "message": "Validasi gagal", "errors": "Hanya mahasiswa yang dapat mengajukan surat."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SuratRequestCreateSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            def _flatten_errors(err):
                if isinstance(err, dict):
                    return " ".join(_flatten_errors(x) for x in err.values())
                if isinstance(err, (list, tuple)):
                    return " ".join(_flatten_errors(x) for x in err)
                return str(err)

            reason = _flatten_errors(serializer.errors).strip() or "Validasi gagal"
            return Response(
                {"status": "error", "message": reason, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        kode_surat_str = serializer.validated_data["kode_surat"]
        try:
            surat_type = SuratType.objects.get(kode_surat=kode_surat_str)
        except SuratType.DoesNotExist:
            return Response({"status": "error", "errors": "Jenis surat tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)

        not_eligible = check_eligibility(student_obj, surat_type.kode_surat)
        if not_eligible:
            return Response(
                {"status": "error", "message": not_eligible, "errors": not_eligible},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_prompt_context = serializer.validated_data.get("user_prompt_context", "")
        initial_payload = serializer.validated_data.get("payload_data") or {}
        chosen_destination = serializer.validated_data.get("chosen_destination") or request.data.get("chosen_destination")
        target_destination_address = serializer.validated_data.get("target_destination_address") or request.data.get("target_destination_address")

        raw_thread_id = request.data.get("thread_id")
        linked_thread = ChatThread.objects.filter(id=raw_thread_id, user=request.user).first() if raw_thread_id else None

        student_metadata = {
            "nim": student_obj.nim,
            "nama": getattr(student_obj.user, "nama", ""),
            "prodi": getattr(student_obj.prodi, "nama_prodi", ""),
            "fakultas": getattr(student_obj.fakultas, "nama_fakultas", ""),
            "semester_aktif": student_obj.semester_aktif,
            "tahun_akademik": student_obj.tahun_akademik,
        }

        surat_req = SuratRequest.objects.create(
            student=student_obj,
            kode_surat=surat_type,
            status=SuratStatus.SUBMITTED,
            payload_data=initial_payload,
            user_prompt_context=user_prompt_context,
            chosen_destination=chosen_destination,
            target_destination_address=target_destination_address,
            chat_thread=linked_thread,
        )

        if linked_thread:
            ChatMessage.objects.create(
                thread=linked_thread,
                sender="assistant",
                message=(
                    f"📨 Permohonan **{surat_type.nama_surat}** telah diterima. "
                    + (
                        "ASURA sedang menyusun suratmu. Surat ini bersifat pribadi, tidak dikirim ke dosen dan tidak perlu persetujuan."
                        if str(surat_type.kode_surat or "").upper().startswith("CUSTOM")
                        else "ASURA sedang menyusun draf resmi dan meneruskannya ke dosen untuk di-ACC."
                    )
                ),
                slots_snapshot={"event": "SURAT_SUBMITTED", "surat_request_id": surat_req.id},
            )
            linked_thread.save(update_fields=["updated_at"])

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="AI_01",
            action="SURAT_SUBMITTED_FOR_AI_DRAFTING",
        )

        worker_thread = threading.Thread(
            target=_execute_drafting_agent_worker,
            kwargs={
                "surat_request_id": surat_req.id,
                "user_prompt_context": user_prompt_context,
                "kode_surat": surat_type.kode_surat,
                "student_metadata": student_metadata,
                "agent": self.get_drafting_agent(),
            },
            daemon=True,
        )
        worker_thread.start()

        return Response(
            {
                "status": "success",
                "message": (
                    f"Permohonan surat {surat_type.nama_surat} berhasil diterima. Surat pribadi ini tidak perlu persetujuan dosen."
                    if str(surat_type.kode_surat or "").upper().startswith("CUSTOM")
                    else f"Permohonan surat {surat_type.nama_surat} berhasil diterima dan diteruskan ke dosen."
                ),
                "request_id": surat_req.id,
                "surat_status": surat_req.status,
                "data": {"request_id": surat_req.id, "kode_surat": surat_type.kode_surat, "status": surat_req.status},
            },
            status=status.HTTP_202_ACCEPTED,
        )


class SuratRequestListAPIView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    serializer_class = SuratRequestListSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'student_profile'):
            return SuratRequest.objects.filter(student=user.student_profile).order_by('-created_at')
        if hasattr(user, 'lecturer_profile'):
            lecturer = user.lecturer_profile
            demo_enabled = getattr(settings, 'DEMO_ONE_STEP_APPROVAL', True)
            demo_approver_nip = getattr(settings, 'DEMO_APPROVER_NIP', '198001012005011001')
            is_demo_lecturer = getattr(user, 'nip_nim', None) == demo_approver_nip
            # Dosen hanya mengurus surat kampus. Surat custom (pribadi) tidak pernah tampil di dashboard dosen.
            non_custom = SuratRequest.objects.exclude(kode_surat__kode_surat__startswith='CUSTOM')
            if demo_enabled and is_demo_lecturer:
                return non_custom.order_by('-created_at').distinct()
            return non_custom.filter(approvals__approver=lecturer).order_by('-created_at').distinct()
        return SuratRequest.objects.all().order_by('-created_at')


class SuratRequestDetailAPIView(RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    serializer_class = SuratRequestDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'student_profile'):
            return SuratRequest.objects.filter(student=user.student_profile)
        return SuratRequest.objects.exclude(kode_surat__kode_surat__startswith='CUSTOM')


class LecturerApprovalActionAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, approval_id):
        action = request.data.get("action")
        if action not in ["APPROVE", "REJECT", "REVISION_REQUIRED"]:
            return Response(
                {"error": "Aksi harus bernilai 'APPROVE', 'REVISION_REQUIRED', atau 'REJECT'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            lecturer_obj = request.user.lecturer_profile
        except (Lecturer.DoesNotExist, AttributeError):
            return Response(
                {"error": "Anda tidak memiliki hak akses sebagai dosen pemberi persetujuan."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            approval_step = SuratApproval.objects.select_related('approver', 'surat_request').get(id=approval_id)
        except SuratApproval.DoesNotExist:
            return Response({"error": "Antrean approval tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)

        catatan = ""
        final_approved_content = None
        final_status = "APPROVED"

        if action == "APPROVE":
            serializer = SuratApprovalActionSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            catatan = serializer.validated_data.get("catatan") or ""
            final_approved_content = serializer.validated_data.get("final_approved_content")

            surat_req = approval_step.surat_request
            custom_nama = str(request.data.get("signer_nama") or "").strip()
            custom_nip = str(request.data.get("signer_nip") or "").strip()
            save_to_profile = str(request.data.get("save_to_profile") or "").lower() in ("true", "1", "yes")
            signature_mode = str(request.data.get("signature_mode") or "qr").strip().lower()
            sig_file = request.FILES.get("signature_image")

            update_fields = []
            if custom_nama:
                surat_req.signer_nama_override = custom_nama
                update_fields.append("signer_nama_override")
            if custom_nip:
                surat_req.signer_nip_override = custom_nip
                update_fields.append("signer_nip_override")

            if save_to_profile:
                user_updates = []
                if custom_nama and custom_nama != request.user.nama:
                    request.user.nama = custom_nama
                    user_updates.append("nama")
                if custom_nip and custom_nip != request.user.nip_nim:
                    from accounts.models import User as AccountUser
                    if not AccountUser.objects.filter(nip_nim=custom_nip).exclude(pk=request.user.pk).exists():
                        request.user.nip_nim = custom_nip
                        user_updates.append("nip_nim")
                if user_updates:
                    request.user.save(update_fields=user_updates)

            if signature_mode == "manual_image" and sig_file is not None:
                raw_bytes = sig_file.read()
                mime_type = getattr(sig_file, "content_type", None) or "image/png"
                if not mime_type.startswith("image/"):
                    return Response(
                        {"error": "File tanda tangan harus berupa gambar (PNG, JPG, atau WEBP)."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                sig_dir = os.path.join(settings.BASE_DIR, "media", "signatures")
                os.makedirs(sig_dir, exist_ok=True)
                with open(os.path.join(sig_dir, f"sig_{surat_req.id}.png"), "wb") as f_sig:
                    f_sig.write(raw_bytes)

                b64_sig = base64.b64encode(raw_bytes).decode("utf-8")
                surat_req.manual_signature_data_uri = f"data:{mime_type};base64,{b64_sig}"
                update_fields.append("manual_signature_data_uri")
            elif signature_mode == "qr":
                surat_req.manual_signature_data_uri = None
                update_fields.append("manual_signature_data_uri")

            if update_fields:
                surat_req.save(update_fields=update_fields)

        elif action in ["REJECT", "REVISION_REQUIRED"]:
            catatan = str(request.data.get("alasan_penolakan") or request.data.get("catatan") or "").strip()
            if not catatan:
                return Response(
                    {"error": "Catatan alasan penolakan atau revisi wajib diisi."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        result_data, http_code = process_approval_action(
            approval_id=approval_id,
            lecturer=lecturer_obj,
            action=action,
            catatan=catatan,
            final_approved_content=final_approved_content,
            final_status=final_status,
        )
        return Response(result_data, status=http_code)


class SuratVerifyAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        try:
            tte_sig = TteSignature.objects.select_related(
                'surat_request',
                'surat_request__student',
                'surat_request__student__user',
                'surat_request__student__prodi',
                'surat_request__student__fakultas',
                'surat_request__kode_surat',
                'signer__user',
            ).get(token=token)
        except TteSignature.DoesNotExist:
            return Response(
                {
                    "status": "INVALID",
                    "message": "Dokumen Surat TIDAK VALID atau palsu. Token verifikasi tidak ditemukan di sistem.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        surat_req = tte_sig.surat_request
        student = surat_req.student
        signer_display = (
            (surat_req.signer_nama_override or "").strip()
            or (tte_sig.signer.user.nama if tte_sig.signer else "Sistem Otomatis Kampus")
        )

        return Response(
            {
                "status": "VALID",
                "message": "Dokumen Surat ASLI dan terdaftar secara resmi di sistem ASURA.",
                "detail_surat": {
                    "nomor_surat_resmi": surat_req.nomor_surat_resmi,
                    "jenis_surat": surat_req.kode_surat.nama_surat,
                    "kategori": surat_req.kode_surat.kategori,
                    "tanggal_terbit": surat_req.created_at,
                },
                "mahasiswa": {
                    "nim": student.nim,
                    "nama": student.user.nama,
                    "prodi": student.prodi.nama_prodi,
                    "fakultas": student.fakultas.nama_fakultas,
                },
                "tte_info": {
                    "hash_sha256": tte_sig.hash_document,
                    "penandatangan": signer_display,
                    "tanggal_ttd": tte_sig.created_at,
                },
            },
            status=status.HTTP_200_OK,
        )

