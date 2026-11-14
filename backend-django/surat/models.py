import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import User, Faculty, Department, Lecturer, Student, Course, StudentCourse


class SuratStatus(models.TextChoices):
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval (Menunggu Tinjauan Draf AI)"
    SUBMITTED = "SUBMITTED", "Submitted (Diajukan)"
    IN_REVIEW = "IN_REVIEW", "In Review (Dalam Proses Persetujuan Berjenjang)"
    APPROVED = "APPROVED", "Approved (Disetujui)"
    REJECTED = "REJECTED", "Rejected (Ditolak)"
    SENT = "SENT", "Sent (Terkirim via Email)"
    PRINTED = "PRINTED", "Printed (Dicetak)"
    FAILED = "FAILED", "Failed (Gagal Eksekusi Pipeline)"
    REVISION_REQUIRED = "REVISION_REQUIRED", "Revision Required (Revisi Draf AI Diminta)"


class ApprovalStatus(models.TextChoices):
    WAITING = "WAITING", "Waiting (Menunggu Giliran)"
    PENDING = "PENDING", "Pending (Aktif Menunggu Keputusan)"
    APPROVED = "APPROVED", "Approved (Disetujui)"
    REJECTED = "REJECTED", "Rejected (Ditolak)"


class SuratType(models.Model):
    kode_surat = models.CharField(max_length=50, primary_key=True)
    nama_surat = models.CharField(max_length=255)
    kategori = models.CharField(max_length=100)
    is_auto_approval = models.BooleanField(default=False)
    template_path = models.CharField(max_length=500, null=True, blank=True)
    required_payload_fields = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'surat_types'


class ApprovalRule(models.Model):
    kode_surat = models.ForeignKey(SuratType, on_delete=models.CASCADE)
    step_order = models.IntegerField()
    approval_role = models.CharField(max_length=100)

    class Meta:
        db_table = 'approval_rules'


class SuratNumberCounter(models.Model):
    kode_surat = models.ForeignKey(SuratType, on_delete=models.CASCADE)
    fakultas = models.ForeignKey(Faculty, on_delete=models.CASCADE, null=True, blank=True)
    prodi = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True)
    tahun = models.IntegerField()
    bulan = models.IntegerField()
    last_number = models.IntegerField(default=0)

    class Meta:
        db_table = 'surat_number_counter'


class ChatThread(models.Model):
    class ThreadStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chat_threads'
    )
    title = models.CharField(max_length=255, default="Permohonan Surat Baru")
    document_type = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ThreadStatus.choices,
        default=ThreadStatus.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
        ]


class SuratRequest(models.Model):
    Status = SuratStatus
    StatusChoices = SuratStatus

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='requests')
    kode_surat = models.ForeignKey(SuratType, on_delete=models.CASCADE)
    nomor_surat_resmi = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(
        max_length=50,
        choices=SuratStatus.choices,
        default=SuratStatus.PENDING_APPROVAL,
        db_index=True,
    )
    payload_data = models.JSONField(default=dict)

    user_prompt_context = models.TextField(null=True, blank=True)
    ai_original_draft = models.TextField(null=True, blank=True)
    final_approved_content = models.TextField(null=True, blank=True)
    self_critique_score = models.SmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    revision_notes = models.JSONField(default=list, blank=True)

    file_pdf_url = models.CharField(max_length=500, null=True, blank=True)
    qr_verification_code = models.CharField(max_length=255, null=True, blank=True)

    # Kustomisasi Penandatangan & Tanda Tangan Manual (Gambar pengganti QR Code)
    signer_nama_override = models.CharField(max_length=255, null=True, blank=True)
    signer_nip_override = models.CharField(max_length=50, null=True, blank=True)
    manual_signature_data_uri = models.TextField(null=True, blank=True)

    CHOICES_DESTINATION = (
        ('email', 'Email'),
        ('telegram', 'Telegram'),
    )
    chosen_destination = models.CharField(choices=CHOICES_DESTINATION, max_length=20, null=True, blank=True)
    target_destination_address = models.CharField(max_length=255, null=True, blank=True)
    chat_thread = models.ForeignKey(
        ChatThread,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='surat_requests',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'surat_request'


class SuratApproval(models.Model):
    Status = ApprovalStatus
    StatusChoices = ApprovalStatus

    surat_request = models.ForeignKey(SuratRequest, on_delete=models.CASCADE, related_name='approvals')
    step_order = models.IntegerField()
    approver = models.ForeignKey(Lecturer, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=50,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )
    catatan = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'surat_approvals'


class SuratAttachment(models.Model):
    surat_request = models.ForeignKey(SuratRequest, on_delete=models.CASCADE, related_name='attachments')
    nama_dokumen = models.CharField(max_length=255)
    file_url = models.CharField(max_length=500)
    mime_type = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'surat_attachment'


class TteSignature(models.Model):
    surat_request = models.ForeignKey(SuratRequest, on_delete=models.CASCADE, related_name='signatures')
    signer = models.ForeignKey(Lecturer, on_delete=models.CASCADE, null=True, blank=True)
    hash_document = models.CharField(max_length=255)
    token = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tte_signatures'


class SuratAuditLog(models.Model):
    surat_request = models.ForeignKey(SuratRequest, on_delete=models.CASCADE, related_name='audit_logs')
    action_id = models.CharField(max_length=100)
    action = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'surat_audit_logs'


class AgentFeedbackMemory(models.Model):
    surat_request = models.ForeignKey(
        SuratRequest,
        on_delete=models.CASCADE,
        related_name='feedback_memories',
    )
    kode_surat = models.ForeignKey(
        SuratType,
        on_delete=models.CASCADE,
        related_name='style_memories',
    )
    diff_summary = models.TextField()
    extracted_rule = models.TextField()
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'agent_feedback_memories'
        indexes = [
            models.Index(fields=['kode_surat', 'is_active']),
        ]


class ChatMessage(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=20)
    message = models.TextField()
    slots_snapshot = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        APPROVAL_REQUIRED = 'APPROVAL_REQUIRED', 'Approval required'
        REVISION_REQUIRED = 'REVISION_REQUIRED', 'Revision required'
        REJECTED = 'REJECTED', 'Rejected'
        APPROVED = 'APPROVED', 'Approved'
        SENT = 'SENT', 'Sent'
        DIRECT_DELIVERY = 'DIRECT_DELIVERY', 'Direct delivery'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=40, choices=NotificationType.choices)
    title = models.CharField(max_length=255)
    body = models.TextField()
    surat_request = models.ForeignKey(
        SuratRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications',
    )
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['user', 'is_read', '-created_at'],
                name='surat_notif_user_id_6c0a3b_idx',
            )
        ]
# === ASURA_AUTO_SMART_CHAT_SAVE ===
_orig_chat_message_save = ChatMessage.save
def _get_chat_msg_text_field():
    for f in ChatMessage._meta.fields:
        if f.name in ("content", "message", "text", "body"):
            return f.name
    return "content"
def _smart_chat_message_save(self, *args, **kwargs):
    try:
        if getattr(self, "sender", "") == "assistant":
            txt_field = _get_chat_msg_text_field()
            raw_txt = str(getattr(self, txt_field, "") or "")
            if (
                "Halo, saya adalah Asisten AI" in raw_txt
                or "Silakan deskripsikan jenis surat yang ingin Anda buat" in raw_txt
            ):
                from .services.conversational_ai import generate_conversational_reply
                thread_obj = getattr(self, "thread", None)
                hist = []
                last_user_msg = ""
                stu_obj = None
                if thread_obj is not None:
                    raw_rows = list(
                        thread_obj.messages.order_by("created_at").values("sender", txt_field)
                    )
                    hist = [
                        {"sender": r.get("sender"), "text": r.get(txt_field, "")}
                        for r in raw_rows
                    ]
                    for item in reversed(hist):
                        if item.get("sender") == "user" and item.get("text"):
                            last_user_msg = str(item["text"])
                            break
                    u_obj = getattr(thread_obj, "user", None)
                    stu_obj = getattr(thread_obj, "student", None) or getattr(u_obj, "student_profile", None)
                stu_info = {}
                if stu_obj is not None:
                    stu_info = {
                        "nama": getattr(getattr(stu_obj, "user", None), "nama", "-"),
                        "nim": getattr(stu_obj, "nim", "-"),
                        "prodi": getattr(getattr(stu_obj, "prodi", None), "nama_prodi", "-"),
                        "semester": getattr(stu_obj, "semester_aktif", "-"),
                    }
                upgraded = generate_conversational_reply(
                    user_message=last_user_msg or "Halo",
                    history_messages=hist,
                    student_info=stu_info,
                )
                if upgraded:
                    setattr(self, txt_field, upgraded)
    except Exception:
        pass
    return _orig_chat_message_save(self, *args, **kwargs)
ChatMessage.save = _smart_chat_message_save

# === ASURA_CUSTOM_REQUEST_GUARD ===
_orig_surat_request_save = SuratRequest.save
def _guarded_surat_request_save(self, *args, **kwargs):
    try:
        kode = str(getattr(getattr(self, "kode_surat", None), "kode_surat", "") or "").upper()
        if kode.startswith("CUSTOM"):
            pdata = dict(getattr(self, "payload_data", None) or {})
            pdata["_is_custom_personal"] = True
            self.payload_data = pdata
            cur_body = str(getattr(self, "final_approved_content", "") or getattr(self, "ai_original_draft", "") or "").strip()
            is_slop_or_empty = (
                not cur_body
                or "fakultas teknik universitas yang bersangkutan" in cur_body.lower()
                or "tata naskah dinas resmi perguruan tinggi" in cur_body.lower()
                or "mahasiswa bersangkutan" in cur_body.lower()
                or "kelengkapan administratif" in cur_body.lower()
            )
            if is_slop_or_empty and getattr(self, "student_id", None):
                from .services.custom_letter_ai import generate_custom_letter_body
                hist = []
                if self.id:
                    th = ChatThread.objects.filter(latest_surat_request_id=self.id).first()
                    if th:
                        hist = [{"sender": r.sender, "text": r.message} for r in th.messages.order_by("created_at")]
                body_txt = generate_custom_letter_body(
                    student=self.student,
                    payload_data=pdata,
                    user_prompt_context=str(getattr(self, "user_prompt_context", "") or ""),
                    history_messages=hist,
                    kode_surat=kode,
                )
                self.ai_original_draft = body_txt
                self.final_approved_content = body_txt
            self.status = SuratStatus.APPROVED
    except Exception:
        pass
    res = _orig_surat_request_save(self, *args, **kwargs)
    try:
        kode = str(getattr(getattr(self, "kode_surat", None), "kode_surat", "") or "").upper()
        if kode.startswith("CUSTOM") and self.id:
            SuratApproval.objects.filter(surat_request_id=self.id).delete()
            from .services.pdf_generator_safe import generate_and_save_official_pdf
            st = self.student
            pdata = self.payload_data or {}
            generate_and_save_official_pdf({
                "id": self.id,
                "surat_request_id": self.id,
                "kode_surat": kode,
                "is_custom_personal": True,
                "nomor_surat": self.nomor_surat_resmi or f"CUSTOM/{self.id:03d}/2026",
                "nama_surat": pdata.get("judul_surat") or self.kode_surat.nama_surat,
                "nama_mahasiswa": st.user.nama,
                "nim": st.nim,
                "program_studi": getattr(getattr(st, "prodi", None), "nama_prodi", None) or "Informatika",
                "fakultas": getattr(getattr(st, "fakultas", None), "nama_fakultas", None) or "Teknik",
                "final_approved_content": self.final_approved_content or self.ai_original_draft or "",
                "isi_surat": self.final_approved_content or self.ai_original_draft or "",
                "payload": pdata,
            })
    except Exception:
        pass
    return res
SuratRequest.save = _guarded_surat_request_save
