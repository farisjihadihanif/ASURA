import cloudinary.uploader
from django.conf import settings
from accounts.models import Lecturer
from ..models import SuratRequest, SuratApproval, SuratAttachment, SuratAuditLog, ApprovalRule
from .notifications import notify_user

def resolve_official_approver(student, kode_surat=None):
    """Penyetuju surat kampus berdasarkan jabatan (tanpa admin):
    surat keterangan aktif kuliah dan UKT -> Dekan; semua surat lain -> Ketua Program Studi.
    Bila jabatan terkait kosong, jatuh ke jabatan lainnya."""
    from .campus_catalog import DEKAN_SURAT_CODES

    prodi = getattr(student, 'prodi', None)
    fakultas = getattr(student, 'fakultas', None)
    kaprodi = getattr(prodi, 'kaprodi', None)
    dekan = getattr(fakultas, 'dekan', None)
    primary, secondary = (dekan, kaprodi) if str(kode_surat or '').upper() in DEKAN_SURAT_CODES else (kaprodi, dekan)
    return primary or secondary or getattr(student, 'dosen_pembimbing_akademik', None)


def create_approval_workflow_for_request(surat_req, student):
    """
    Membuat antrean SuratApproval untuk sebuah SuratRequest.
    - Bila ApprovalRule untuk jenis surat diatur di database, ikuti rule berjenjang tersebut.
    - Bila tidak, satu langkah: Dekan untuk surat aktif kuliah/UKT, Ketua Program Studi untuk surat lainnya.
    """
    if surat_req.approvals.exists():
        return  # idempotent: antrean sudah dibuat (mis. oleh hook penyimpanan)
    surat_type = surat_req.kode_surat
    rules = ApprovalRule.objects.filter(kode_surat=surat_type).order_by('step_order')

    if not rules.exists():
        approver = resolve_official_approver(student, getattr(surat_type, "kode_surat", surat_type))
        if approver:
            SuratApproval.objects.create(
                surat_request=surat_req,
                step_order=1,
                approver=approver,
                status='PENDING',
            )
        return

    for rule in rules:
        approver_obj = None
        if rule.approval_role == 'DPA':
            approver_obj = student.dosen_pembimbing_akademik
        elif rule.approval_role == 'KAPRODI':
            approver_obj = student.prodi.kaprodi
        elif rule.approval_role == 'DEKAN':
            approver_obj = student.fakultas.dekan

        if approver_obj:
            SuratApproval.objects.create(
                surat_request=surat_req,
                step_order=rule.step_order,
                approver=approver_obj,
                status='PENDING' if rule.step_order == 1 else 'WAITING',
            )


def handle_manual_approval_surat(student, surat_type, payload_data, attachments_files=None):
    """
    Menangani pengajuan surat jalur Manual Approval Berjenjang.
    """
    # 1. Buat record SuratRequest dengan status SUBMITTED
    surat_req = SuratRequest.objects.create(
        student=student,
        kode_surat=surat_type,
        payload_data=payload_data,
        status='SUBMITTED'
    )

    # 2. Simpan lampiran dokumen ke Cloudinary jika ada
    if attachments_files:
        for file_obj in attachments_files:
            upload_res = cloudinary.uploader.upload(
                file_obj, 
                resource_type="auto", 
                folder="autosurat_attachments"
            )
            SuratAttachment.objects.create(
                surat_request=surat_req,
                nama_dokumen=file_obj.name,
                file_url=upload_res.get("secure_url"),
                mime_type=getattr(file_obj, 'content_type', 'application/octet-stream')
            )

    # 3. Ambil aturan approval berjenjang berdasarkan ApprovalRule
    create_approval_workflow_for_request(surat_req, student)
    first_approval = surat_req.approvals.filter(status='PENDING').select_related('approver__user').first()
    if first_approval:
        notify_user(
            first_approval.approver.user,
            'APPROVAL_REQUIRED',
            'Pengajuan surat baru',
            f'{student.user.nama} mengajukan {surat_type.nama_surat}. Silakan tinjau isi dan tujuan pengiriman.',
            surat_req,
        )
    
    # 4. Catat Audit Log
    SuratAuditLog.objects.create(
        surat_request=surat_req,
        action_id="SUB_01",
        action="SURAT_SUBMITTED_FOR_APPROVAL"
    )

    return {
        "message": f"Pengajuan surat {surat_type.nama_surat} berhasil dikirim dan masuk antrean approval.",
        "request_id": surat_req.id,
        "status": "SUBMITTED"
    }, 201
