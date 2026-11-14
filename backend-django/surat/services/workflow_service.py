import threading
from logging import getLogger
from django.conf import settings
from django.db import close_old_connections
from .auto_handlers import handle_auto_approval_surat
from .manual_handlers import handle_manual_approval_surat
from ..models import SuratApproval, SuratAuditLog, SuratRequest, ChatMessage
from .email_service import send_surat_via_gmail_admin
from .telegram_service import send_surat_via_telegram
from .notifications import notify_user

logger = getLogger(__name__)
_last_issuance_worker_thread = None


def process_surat_request(student, surat_type, payload_data, attachments_files=None):
    if surat_type.is_auto_approval:
        return handle_auto_approval_surat(student, surat_type, payload_data, attachments_files)
    return handle_manual_approval_surat(student, surat_type, payload_data, attachments_files)


def _close_sibling_approvals(approval_step):
    """Jika beberapa dosen (pejabat + dosen pengampu) menerima antrean yang sama,
    keputusan pertama berlaku; antrean paralel lain di langkah yang sama dihapus."""
    try:
        SuratApproval.objects.filter(
            surat_request=approval_step.surat_request,
            step_order=approval_step.step_order,
            status='PENDING',
        ).exclude(pk=approval_step.pk).delete()
    except Exception as exc:
        logger.warning("[SIBLING_APPROVAL] %s", exc)


def process_approval_action(
    approval_id,
    lecturer,
    action,
    catatan="",
    final_approved_content=None,
    final_status="APPROVED",
):
    try:
        approval_step = SuratApproval.objects.select_related(
            'surat_request',
            'surat_request__kode_surat',
            'surat_request__student',
            'surat_request__student__user',
            'surat_request__student__fakultas',
            'surat_request__student__prodi',
            'surat_request__chat_thread',
        ).get(id=approval_id)
    except SuratApproval.DoesNotExist:
        return {"error": "Antrean approval tidak ditemukan."}, 404

    surat_req = approval_step.surat_request

    demo_enabled = getattr(settings, 'DEMO_ONE_STEP_APPROVAL', False)
    demo_target_surat = getattr(settings, 'DEMO_TARGET_SURAT', ['SR-MAG', 'SR-BEA', 'SP-MAG', 'SI-MAG', 'SK-KUL'])
    demo_approver_nip = getattr(settings, 'DEMO_APPROVER_NIP', '198001012005011001')
    lecturer_nip = getattr(getattr(lecturer, 'user', None), 'nip_nim', None)
    lecturer_nama = getattr(getattr(lecturer, 'user', None), 'nama', '')
    # Hanya akun pejabat resmi (NIP demo) yang boleh melewati pengecekan antrean.
    # Dosen lain hanya bisa memproses antrean yang memang ditugaskan kepadanya.
    is_demo_bypass = bool(demo_enabled and lecturer_nip == demo_approver_nip)

    if not is_demo_bypass and approval_step.approver != lecturer:
        return {"error": "Anda tidak memiliki hak akses untuk menyetujui antrean ini."}, 403

    if not is_demo_bypass and approval_step.status != 'PENDING':
        return {"error": "Langkah persetujuan ini belum aktif atau sudah diproses sebelumnya."}, 400

    if action == 'REVISION_REQUIRED':
        approval_step.status = 'PENDING'
        approval_step.catatan = catatan
        approval_step.save(update_fields=['status', 'catatan'])
        surat_req.status = 'REVISION_REQUIRED'
        surat_req.revision_notes = list(surat_req.revision_notes or []) + [catatan]
        surat_req.save(update_fields=['status', 'revision_notes'])
        notify_user(
            surat_req.student.user,
            'REVISION_REQUIRED',
            f'Revisi Diperlukan: {surat_req.kode_surat.nama_surat}',
            catatan or 'Dosen meminta revisi pada draf surat Anda.',
            surat_req,
        )
        if surat_req.chat_thread:
            ChatMessage.objects.create(
                thread=surat_req.chat_thread,
                sender="assistant",
                message=f"📝 **Dosen Meminta Revisi:** {catatan or 'Mohon perbaiki detail permohonan surat Anda.'}",
                slots_snapshot={"event": "REVISION_REQUIRED", "surat_request_id": surat_req.id},
            )
            surat_req.chat_thread.save(update_fields=["updated_at"])
            try:
                from .revision_assistant import post_guidance_async
                post_guidance_async(surat_req.id)
            except Exception as guide_exc:
                logger.warning("[REVISION_GUIDANCE] %s", guide_exc)
        return {"message": "Permintaan revisi telah dikirim kepada mahasiswa."}, 200

    if action == 'REJECT':
        approval_step.status = 'REJECTED'
        approval_step.catatan = catatan
        approval_step.save(update_fields=['status', 'catatan'])
        _close_sibling_approvals(approval_step)

        surat_req.status = 'REJECTED'
        surat_req.save(update_fields=['status'])
        notify_user(
            surat_req.student.user,
            'REJECTED',
            f'Surat Ditolak: {surat_req.kode_surat.nama_surat}',
            catatan or 'Dosen menolak pengajuan surat.',
            surat_req,
        )
        if surat_req.chat_thread:
            ChatMessage.objects.create(
                thread=surat_req.chat_thread,
                sender="assistant",
                message=f"❌ **Permohonan Surat Ditolak:** {catatan or 'Tidak memenuhi persyaratan.'}",
                slots_snapshot={"event": "SURAT_REJECTED", "surat_request_id": surat_req.id},
            )
            surat_req.chat_thread.save(update_fields=["updated_at"])

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="REJ_01",
            action=f"REJECTED_BY_{lecturer.id}",
        )
        return {"message": "Pengajuan surat telah ditolak."}, 200

    if action == 'APPROVE':
        approval_step.status = 'APPROVED'
        approval_step.catatan = catatan
        approval_step.save(update_fields=['status', 'catatan'])
        _close_sibling_approvals(approval_step)

        if isinstance(final_approved_content, str) and final_approved_content.strip():
            surat_req.final_approved_content = final_approved_content.strip()

        next_step = None
        if not is_demo_bypass:
            next_step = SuratApproval.objects.filter(
                surat_request=surat_req,
                step_order=approval_step.step_order + 1,
            ).first()

        if next_step:
            next_step.status = 'PENDING'
            next_step.save(update_fields=['status'])
            notify_user(
                next_step.approver.user,
                'APPROVAL_REQUIRED',
                'Persetujuan surat diperlukan',
                'Surat telah diteruskan ke tahap persetujuan berikutnya.',
                surat_req,
            )
            surat_req.status = 'IN_REVIEW'
            update_cols = ['status']
            if isinstance(final_approved_content, str) and final_approved_content.strip():
                update_cols.append('final_approved_content')
            surat_req.save(update_fields=update_cols)
            return {"message": "Persetujuan tahap ini berhasil. Surat diteruskan ke pejabat selanjutnya."}, 200

        resolved_content = surat_req.final_approved_content or surat_req.ai_original_draft or ""
        if not surat_req.final_approved_content and resolved_content:
            surat_req.final_approved_content = resolved_content

        surat_req.status = 'APPROVED'
        update_req_fields = ['status']
        if isinstance(final_approved_content, str) and final_approved_content.strip():
            update_req_fields.append('final_approved_content')
        surat_req.save(update_fields=update_req_fields)

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id=f"APP_0{approval_step.step_order}",
            action=f"FINAL_APPROVAL_CONFIRMED_BY_{lecturer.id}",
        )

        _execute_final_issuance_worker(
            surat_request_id=surat_req.id,
            signer_lecturer_id=lecturer.id,
            final_status="APPROVED",
        )
        surat_req.refresh_from_db()
        if surat_req.status == "FAILED":
            return {"error": "Gagal menerbitkan dokumen PDF resmi surat."}, 500
        return {
            "message": f"Surat berhasil di-ACC (No. {surat_req.nomor_surat_resmi})! Notifikasi telah dikirim ke mahasiswa.",
            "status": surat_req.status,
            "nomor_surat_resmi": surat_req.nomor_surat_resmi,
            "file_pdf_url": surat_req.file_pdf_url,
        }, 200

    return {"error": "Aksi tidak valid."}, 400


def route_and_distribute_document(surat_request):
    if not surat_request.file_pdf_url:
        raise ValueError("File PDF belum tersedia untuk didistribusikan.")

    destination_type = surat_request.chosen_destination
    target_address = surat_request.target_destination_address

    if destination_type == 'email':
        subject = f"Dokumen Resmi - {surat_request.kode_surat.nama_surat}"
        body = (
            "Dengan hormat,\n\n"
            "Berikut dilampirkan dokumen resmi yang telah diterbitkan dan disetujui oleh Fakultas.\n"
            "Terima kasih."
        )
        return send_surat_via_gmail_admin(
            recipient_email=target_address,
            subject=subject,
            body_message=body,
            pdf_path=surat_request.file_pdf_url,
        )
    elif destination_type == 'telegram':
        caption = "✅ *Surat Resmi Anda Telah Disetujui!*\nBerikut adalah dokumen PDF resmi yang diterbitkan oleh sistem kampus."
        return send_surat_via_telegram(
            chat_id=target_address,
            caption=caption,
            pdf_path=surat_request.file_pdf_url,
        )
    logger.warning(f"Destinasi pengiriman kosong untuk SuratRequest id={surat_request.id}")
    return {"status": "SKIPPED"}


def _execute_final_issuance_worker(
    surat_request_id: int,
    signer_lecturer_id: int = None,
    final_status: str = "APPROVED",
):
    close_old_connections()
    try:
        from ..models import Lecturer
        from ..agents.execution_tools import SuratExecutionTools

        surat_req = SuratRequest.objects.select_related(
            'kode_surat',
            'student',
            'student__user',
            'student__fakultas',
            'student__prodi',
            'chat_thread',
        ).get(pk=surat_request_id)

        signer = Lecturer.objects.filter(pk=signer_lecturer_id).first() if signer_lecturer_id else None
        resolved_content = surat_req.final_approved_content or surat_req.ai_original_draft or ""

        tools = SuratExecutionTools()
        pipeline_result = tools.execute_approval_pipeline(
            surat_request=surat_req,
            signer=signer,
            final_approved_content=resolved_content,
            final_status="APPROVED",
        )

        surat_req.status = "APPROVED"
        surat_req.save(update_fields=["status"])

        if surat_req.ai_original_draft and surat_req.final_approved_content:
            try:
                from ..agents.memory_agent import AgenticMemoryAgent
                mem_agent = AgenticMemoryAgent()
                mem_agent.record_feedback_memory(
                    surat_request=surat_req,
                    ai_original_draft=surat_req.ai_original_draft,
                    final_approved_content=surat_req.final_approved_content,
                    allow_heuristic_fallback=True,
                )
            except Exception as mem_exc:
                logger.warning("[ASYNC_MEMORY_WARN] id=%s: %s", surat_req.id, mem_exc)

        signer_display = (
            (surat_req.signer_nama_override or "").strip()
            or getattr(getattr(signer, 'user', None), 'nama', 'Dosen / Pejabat Berwenang')
        )
        notif_body = (
            f"{surat_req.kode_surat.nama_surat} (No. {pipeline_result.nomor_surat_resmi}) "
            f"telah di-ACC oleh {signer_display}. Buka sesi chat untuk mengirim ke Email atau mencetak ke Printer."
        )
        notify_user(
            surat_req.student.user,
            'APPROVED',
            f'Surat Di-ACC: {surat_req.kode_surat.nama_surat}',
            notif_body,
            surat_req,
        )

        if surat_req.chat_thread:
            ChatMessage.objects.create(
                thread=surat_req.chat_thread,
                sender="assistant",
                message=(
                    f"✅ **Surat Anda Telah Di-ACC oleh {signer_display}!**\n\n"
                    f"- **Jenis Surat:** {surat_req.kode_surat.nama_surat}\n"
                    f"- **Nomor Resmi:** `{pipeline_result.nomor_surat_resmi}`\n\n"
                    f"Silakan pilih tindakan selanjutnya di bawah ini: **Kirim ke Email** atau **Cetak ke Printer**."
                ),
                slots_snapshot={
                    "event": "SURAT_APPROVED",
                    "surat_request_id": surat_req.id,
                    "nomor_surat_resmi": pipeline_result.nomor_surat_resmi,
                },
            )
            surat_req.chat_thread.save(update_fields=["updated_at"])

    except Exception as exc:
        logger.exception("[ASYNC_ISSUANCE_ERROR] id=%s: %s", surat_request_id, exc)
        try:
            surat_req = SuratRequest.objects.get(pk=surat_request_id)
            surat_req.status = "FAILED"
            surat_req.save(update_fields=["status"])
            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id="FIN_ERR",
                action=f"ASYNC_ISSUANCE_FAILED: {str(exc)}"[:255],
            )
        except Exception:
            pass
    finally:
        close_old_connections()