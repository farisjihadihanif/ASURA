import json
from rest_framework import serializers
from .models import (
    SuratType,
    SuratRequest,
    SuratApproval,
    SuratAttachment,
    TteSignature,
    SuratAuditLog,
    AgentFeedbackMemory,
)
from .services.validators import run_validators


class SuratRequestCreateSerializer(serializers.Serializer):
    kode_surat = serializers.CharField(max_length=50)
    user_prompt_context = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    konteks = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    payload_data = serializers.JSONField(default=dict, required=False)
    chosen_destination = serializers.ChoiceField(choices=["email", "telegram"], required=False, allow_null=True)
    target_destination_address = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    attachments = serializers.ListField(child=serializers.FileField(), required=False, allow_empty=True)

    def validate(self, data):
        kode_surat = data.get('kode_surat')
        raw_payload = data.get('payload_data')

        prompt_candidates = [data.get('user_prompt_context'), data.get('konteks')]
        if hasattr(self, 'initial_data') and isinstance(self.initial_data, dict):
            prompt_candidates.extend([self.initial_data.get('prompt'), self.initial_data.get('context')])
            if not raw_payload and self.initial_data.get('payload_data'):
                raw_payload = self.initial_data.get('payload_data')

        if isinstance(raw_payload, str) and raw_payload.strip():
            try:
                parsed = json.loads(raw_payload.strip())
                payload = parsed if isinstance(parsed, dict) else {}
            except Exception:
                prompt_candidates.append(raw_payload.strip())
                payload = {}
        elif isinstance(raw_payload, dict):
            payload = dict(raw_payload)
        else:
            payload = {}

        resolved_prompt = next(
            (item.strip() for item in prompt_candidates if isinstance(item, str) and item.strip()),
            ""
        )
        if not resolved_prompt and payload:
            resolved_prompt = json.dumps(payload, ensure_ascii=False)
        if not resolved_prompt:
            resolved_prompt = f"Permohonan {kode_surat}"

        data['user_prompt_context'] = resolved_prompt
        data['payload_data'] = payload

        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Autentikasi diperlukan untuk mengajukan surat.")

        user = request.user
        if hasattr(user, 'student_profile'):
            student_profile = user.student_profile
            student_data = {
                "nim": student_profile.nim,
                "status_akademik": student_profile.status_akademik,
                "status_pembayaran_ukt": student_profile.status_pembayaran_ukt,
                "semester_aktif": student_profile.semester_aktif,
                "total_sks_lulus": student_profile.total_sks_lulus,
                "ipk_kumulatif": student_profile.ipk_kumulatif,
                "catatan_pelanggaran_etik": student_profile.catatan_pelanggaran_etik,
                "status_disiplin_kampus": student_profile.status_disiplin_kampus,
                "status_beasiswa_aktif": student_profile.status_beasiswa_aktif,
                "nama_beasiswa_aktif": student_profile.nama_beasiswa_aktif,
                "prodi": student_profile.prodi.nama_prodi,
                "fakultas": student_profile.fakultas.nama_fakultas,
            }
            student_courses_data = list(
                student_profile.courses_taken.values("student_id", "course_id", "semester_taken", "status_krs")
            )
            run_validators(
                kode_surat=kode_surat,
                student_data=student_data,
                payload=payload,
                student_courses_data=student_courses_data,
            )

        return data


class ReDraftSuratRequestSerializer(serializers.Serializer):
    additional_prompt_context = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    user_prompt_context = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    konteks = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    payload_data = serializers.JSONField(default=dict, required=False)

    def validate(self, data):
        candidates = [
            data.get("additional_prompt_context"),
            data.get("user_prompt_context"),
            data.get("konteks"),
        ]
        resolved = next((item.strip() for item in candidates if isinstance(item, str) and item.strip()), "")
        if not resolved:
            raise serializers.ValidationError({"additional_prompt_context": "Konteks tambahan revisi wajib diisi."})
        data["additional_prompt_context"] = resolved
        return data


class SuratApprovalActionSerializer(serializers.Serializer):
    catatan = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    final_approved_content = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    final_status = serializers.ChoiceField(choices=["APPROVED", "SENT", "PRINTED"], required=False, default="APPROVED")


class SuratTypeSerializer(serializers.ModelSerializer):
    required_payload_fields = serializers.SerializerMethodField()

    class Meta:
        model = SuratType
        fields = [
            'kode_surat',
            'nama_surat',
            'kategori',
            'is_auto_approval',
            'template_path',
            'required_payload_fields',
        ]

    def get_required_payload_fields(self, obj):
        from .services.chat_workflow import get_effective_required_fields
        return get_effective_required_fields(obj)


class SuratAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuratAttachment
        fields = ['id', 'nama_dokumen', 'file_url', 'mime_type', 'created_at']


class TteSignatureSerializer(serializers.ModelSerializer):
    signer_name = serializers.CharField(source='signer.user.nama', read_only=True, default="Sistem Otomatis")
    signer_nip = serializers.CharField(source='signer.user.nip_nim', read_only=True, default=None)

    class Meta:
        model = TteSignature
        fields = ['id', 'signer_name', 'signer_nip', 'hash_document', 'token', 'created_at']


class SuratApprovalSerializer(serializers.ModelSerializer):
    approver_name = serializers.CharField(source='approver.user.nama', read_only=True, default=None)
    approver_nip = serializers.CharField(source='approver.user.nip_nim', read_only=True, default=None)

    class Meta:
        model = SuratApproval
        fields = [
            'id',
            'step_order',
            'approver',
            'approver_name',
            'approver_nip',
            'status',
            'catatan',
            'created_at',
        ]


class SuratAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuratAuditLog
        fields = ['id', 'action_id', 'action', 'created_at']


class SuratRequestListSerializer(serializers.ModelSerializer):
    nama_surat = serializers.CharField(source='kode_surat.nama_surat', read_only=True)
    kategori = serializers.CharField(source='kode_surat.kategori', read_only=True)
    nim_mahasiswa = serializers.SerializerMethodField()
    nama_mahasiswa = serializers.SerializerMethodField()
    requester_role = serializers.SerializerMethodField()

    def get_nim_mahasiswa(self, obj):
        return obj.requester_identifier or '-'

    def get_nama_mahasiswa(self, obj):
        return getattr(obj.requester_user, 'nama', None) or '-'

    def get_requester_role(self, obj):
        return obj.requester_role

    class Meta:
        model = SuratRequest
        fields = [
            'id',
            'nim_mahasiswa',
            'nama_mahasiswa',
            'requester_role',
            'kode_surat',
            'nama_surat',
            'kategori',
            'nomor_surat_resmi',
            'status',
            'created_at',
        ]


class SuratRequestDetailSerializer(serializers.ModelSerializer):
    nama_surat = serializers.CharField(source='kode_surat.nama_surat', read_only=True)
    nama_mahasiswa = serializers.SerializerMethodField()
    nim_mahasiswa = serializers.SerializerMethodField()
    prodi_mahasiswa = serializers.SerializerMethodField()
    fakultas_mahasiswa = serializers.SerializerMethodField()
    requester_role = serializers.SerializerMethodField()

    attachments = SuratAttachmentSerializer(many=True, read_only=True)
    approvals = SuratApprovalSerializer(many=True, read_only=True)
    signatures = TteSignatureSerializer(many=True, read_only=True)
    audit_logs = SuratAuditLogSerializer(many=True, read_only=True)

    def get_nama_mahasiswa(self, obj):
        return getattr(obj.requester_user, 'nama', None) or '-'

    def get_nim_mahasiswa(self, obj):
        return obj.requester_identifier or '-'

    def get_prodi_mahasiswa(self, obj):
        return getattr(obj.requester_prodi, 'nama_prodi', None) or '-'

    def get_fakultas_mahasiswa(self, obj):
        return getattr(obj.requester_fakultas, 'nama_fakultas', None) or '-'

    def get_requester_role(self, obj):
        return obj.requester_role

    class Meta:
        model = SuratRequest
        fields = [
            'id',
            'nim_mahasiswa',
            'nama_mahasiswa',
            'requester_role',
            'prodi_mahasiswa',
            'fakultas_mahasiswa',
            'kode_surat',
            'nama_surat',
            'nomor_surat_resmi',
            'status',
            'signer_nama_override',
            'signer_nip_override',
            'chosen_destination',
            'target_destination_address',
            'payload_data',
            'user_prompt_context',
            'ai_original_draft',
            'final_approved_content',
            'self_critique_score',
            'revision_notes',
            'file_pdf_url',
            'qr_verification_code',
            'created_at',
            'attachments',
            'approvals',
            'signatures',
            'audit_logs',
        ]


class AgentFeedbackMemorySerializer(serializers.ModelSerializer):
    kode_surat = serializers.CharField(source='kode_surat_id', read_only=True)
    nama_surat = serializers.CharField(source='kode_surat.nama_surat', read_only=True)

    class Meta:
        model = AgentFeedbackMemory
        fields = [
            'id',
            'surat_request_id',
            'kode_surat',
            'nama_surat',
            'diff_summary',
            'extracted_rule',
            'reference_draft',
            'is_active',
            'created_at',
        ]