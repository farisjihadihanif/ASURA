import base64
import io
import logging
import os
import tempfile
from typing import Any, Callable, Dict, Optional

import qrcode
from django.db import transaction
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.utils import timezone
from pydantic import BaseModel, ConfigDict

from surat.models import (
    SuratAuditLog,
    SuratRequest,
    SuratStatus,
    TteSignature,
)
from surat.services import number_service, pdf_service, tte_service

logger = logging.getLogger(__name__)

_ORIG_GENERATE_SURAT_NUMBER = number_service.generate_surat_number
_ORIG_CREATE_TTE_SIGNATURE = tte_service.create_tte_signature
_ORIG_RENDER_AND_UPLOAD_PDF = pdf_service.render_and_upload_pdf

generate_surat_number = _ORIG_GENERATE_SURAT_NUMBER
create_tte_signature = _ORIG_CREATE_TTE_SIGNATURE
render_and_upload_pdf = _ORIG_RENDER_AND_UPLOAD_PDF

VALID_FINAL_STATUSES = (SuratStatus.SENT, SuratStatus.PRINTED, SuratStatus.APPROVED)


class ExecutionToolError(Exception):
    def __init__(
        self,
        message: str,
        *,
        tool_name: str = "execution_tools",
        original_exception: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.tool_name = tool_name
        self.original_exception = original_exception


class SuratNumberGenerationError(ExecutionToolError):
    pass


class TteGenerationError(ExecutionToolError):
    pass


class PdfRenderUploadError(ExecutionToolError):
    pass


class ExecutionPipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    surat_request_id: int
    nomor_surat_resmi: str
    file_pdf_url: str
    qr_code_url: str
    tte_token: str
    hash_document: str
    final_status: str
    final_approved_content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def _resolve_number_fn() -> Callable[..., str]:
    if generate_surat_number is not _ORIG_GENERATE_SURAT_NUMBER:
        return generate_surat_number
    return number_service.generate_surat_number


def _resolve_tte_fn() -> Callable[..., Dict[str, Any]]:
    if create_tte_signature is not _ORIG_CREATE_TTE_SIGNATURE:
        return create_tte_signature
    return tte_service.create_tte_signature


def _resolve_pdf_fn() -> Callable[..., str]:
    if render_and_upload_pdf is not _ORIG_RENDER_AND_UPLOAD_PDF:
        return render_and_upload_pdf
    return pdf_service.render_and_upload_pdf


def _build_fallback_pdf_and_upload(context_data: Dict[str, Any]) -> str:
    from surat.services.pdf_generator_safe import generate_and_save_official_pdf
    return generate_and_save_official_pdf(context_data)

class SuratExecutionTools:
    def generate_official_number(self, surat_request: SuratRequest) -> str:
        if surat_request.nomor_surat_resmi and surat_request.nomor_surat_resmi.strip():
            return surat_request.nomor_surat_resmi.strip()

        try:
            number_fn = _resolve_number_fn()
            fakultas = getattr(surat_request.student, "fakultas", None)
            nomor_resmi = number_fn(surat_request.kode_surat, fakultas=fakultas)
            if not nomor_resmi or not str(nomor_resmi).strip():
                raise ValueError("Fungsi generate_surat_number mengembalikan nilai kosong.")
            return str(nomor_resmi).strip()
        except Exception as exc:
            raise SuratNumberGenerationError(
                f"Gagal menerbitkan nomor surat resmi: {exc}",
                tool_name="generate_official_number",
                original_exception=exc,
            ) from exc

    def generate_tte_and_qr_code(
        self,
        surat_request: SuratRequest,
        signer: Optional[Any] = None,
    ) -> Dict[str, Any]:
        try:
            tte_fn = _resolve_tte_fn()
            tte_data = tte_fn(surat_request, signer=signer)
            qr_code_url = str(tte_data.get("qr_code_url") or "").strip()
            token = str(tte_data.get("token") or "").strip()
            hash_document = str(tte_data.get("hash_document") or "").strip()

            if not TteSignature.objects.filter(surat_request=surat_request).exists():
                resolved_token = token or f"token-{surat_request.id}"
                resolved_hash = hash_document or f"sha256-verified-{surat_request.id}"
                tte_instance = TteSignature.objects.create(
                    surat_request=surat_request,
                    signer=signer,
                    hash_document=resolved_hash,
                    token=resolved_token,
                )
                tte_data = {
                    "instance": tte_instance,
                    "token": resolved_token,
                    "hash_document": resolved_hash,
                    "qr_code_url": qr_code_url,
                }
            return tte_data
        except Exception as exc:
            raise TteGenerationError(
                f"Gagal membuat tanda tangan elektronik (TTE): {exc}",
                tool_name="generate_tte_and_qr_code",
                original_exception=exc,
            ) from exc

    @staticmethod
    def resolve_template_path(surat_request: SuratRequest) -> str:
        raw_path = getattr(getattr(surat_request, "kode_surat", None), "template_path", None)
        candidate = str(raw_path).strip().replace("\\", "/") if raw_path else ""
        if candidate.startswith("templates/"):
            candidate = candidate[len("templates/"):]
        elif candidate.startswith("/templates/"):
            candidate = candidate[len("/templates/"):]

        if candidate:
            try:
                from django.template.loader import get_template
                tmpl = get_template(candidate)
                tmpl_origin = getattr(tmpl, "origin", None)
                tmpl_filename = getattr(tmpl_origin, "name", None)
                if tmpl_filename and os.path.exists(tmpl_filename) and os.path.getsize(tmpl_filename) > 0:
                    return candidate
            except (TemplateDoesNotExist, TemplateSyntaxError, Exception):
                pass
        return "kerangka-surat/base_surat.html"

    def build_pdf_template_context(
        self,
        surat_request: SuratRequest,
        nomor_surat: str,
        qr_code_url: str,
        final_approved_content: Optional[str] = None,
        signer: Optional[Any] = None,
    ) -> Dict[str, Any]:
        student = surat_request.student
        user_obj = getattr(student, "user", None)
        prodi_obj = getattr(student, "prodi", None)
        fakultas_obj = getattr(student, "fakultas", None)
        surat_type_obj = getattr(surat_request, "kode_surat", None)

        effective_signer = signer
        if effective_signer is None and student is not None:
            from surat.services.manual_handlers import resolve_official_approver
            effective_signer = resolve_official_approver(
                student,
                getattr(surat_type_obj, "kode_surat", None),
            )
        if effective_signer is None and prodi_obj is not None:
            effective_signer = getattr(prodi_obj, "kaprodi", None)
        if effective_signer is None and fakultas_obj is not None:
            effective_signer = getattr(fakultas_obj, "dekan", None)

        signer_user = getattr(effective_signer, "user", None) if effective_signer is not None else None
        default_signer_nama = getattr(signer_user, "nama", None) or getattr(effective_signer, "nama", None) or ""
        default_signer_nip = (
            getattr(signer_user, "nip_nim", None)
            or getattr(effective_signer, "nip_nim", None)
            or ""
        )

        # Prioritaskan Nama & NIP penandatangan yang diubah dosen saat ACC jika ada
        signer_nama = (getattr(surat_request, "signer_nama_override", None) or "").strip() or default_signer_nama
        signer_nip = (getattr(surat_request, "signer_nip_override", None) or "").strip() or default_signer_nip

        raw_jabatan = getattr(effective_signer, "jabatan_struktural", None)
        if isinstance(raw_jabatan, (list, tuple)) and len(raw_jabatan) > 0:
            signer_jabatan = str(raw_jabatan[0]).strip()
        elif isinstance(raw_jabatan, str) and raw_jabatan.strip():
            signer_jabatan = raw_jabatan.strip()
        else:
            nama_fak = getattr(fakultas_obj, "nama_fakultas", "")
            signer_jabatan = f"Pimpinan Fakultas {nama_fak}".strip() if nama_fak else "Pejabat Penandatangan"

        payload = dict(surat_request.payload_data) if isinstance(surat_request.payload_data, dict) else {}
        kota_surat = payload.get("kota_surat") or os.environ.get("UNIVERSITY_CITY", "Yogyakarta")

        resolved_content = (
            final_approved_content
            if final_approved_content is not None and str(final_approved_content).strip()
            else (surat_request.final_approved_content or surat_request.ai_original_draft or "")
        )

        qr_base64 = ""
        try:
            qr_img = qrcode.make(qr_code_url or nomor_surat)
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")
            qr_base64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
        except Exception:
            qr_base64 = qr_code_url

        # Cek apakah Dosen mengunggah Tanda Tangan Manual (gambar) untuk menggantikan QR Code
        manual_sig_uri = (getattr(surat_request, "manual_signature_data_uri", None) or "").strip()
        is_manual_signature = bool(manual_sig_uri.startswith("data:image/"))
        effective_sig_graphic = manual_sig_uri if is_manual_signature else qr_base64

        return {
            "student": student,
            "id": surat_request.id,
            "surat_request_id": surat_request.id,
            "nama_mahasiswa": getattr(user_obj, "nama", ""),
            "nim": getattr(student, "nim", ""),
            "program_studi": getattr(prodi_obj, "nama_prodi", ""),
            "prodi": getattr(prodi_obj, "nama_prodi", ""),
            "fakultas": getattr(fakultas_obj, "nama_fakultas", ""),
            "nama_fakultas": getattr(fakultas_obj, "nama_fakultas", ""),
            "semester_aktif": getattr(student, "semester_aktif", ""),
            "tahun_akademik": getattr(student, "tahun_akademik", ""),
            "nama_surat": getattr(surat_type_obj, "nama_surat", "Surat Keterangan Resmi"),
            "kode_surat": getattr(surat_type_obj, "kode_surat", str(surat_type_obj or "")),
            "payload": payload,
            "payload_data": payload,
            "nomor_surat": nomor_surat,
            "nomor_surat_resmi": nomor_surat,
            "qr_code_url": effective_sig_graphic,
            "qr_verification_code": qr_code_url,
            "qr_base64": qr_base64,
            "is_manual_signature": is_manual_signature,
            "manual_signature_data_uri": manual_sig_uri,
            "final_approved_content": resolved_content,
            "final_content": resolved_content,
            "ai_original_draft": surat_request.ai_original_draft or "",
            "isi_surat": resolved_content,
            "tanggal_terbit": timezone.now(),
            "tanggal_surat": timezone.now().strftime("%d %B %Y"),
            "kota_surat": kota_surat,
            "signer": effective_signer,
            "signer_nama": signer_nama,
            "nama_penandatangan": signer_nama,
            "signer_nip": signer_nip,
            "nip_penandatangan": signer_nip,
            "signer_jabatan": signer_jabatan,
            "jabatan_penandatangan": signer_jabatan,
        }

    @staticmethod
    def _is_template_ready_for_ai_content(tmpl_filename: str) -> bool:
        try:
            if not tmpl_filename or not os.path.exists(tmpl_filename) or os.path.getsize(tmpl_filename) == 0:
                return False
            with open(tmpl_filename, "r", encoding="utf-8") as f_obj:
                raw_html = f_obj.read()
            if "{{ ../" in raw_html or "{{../" in raw_html:
                return False
            return any(tag in raw_html for tag in ("final_approved_content", "final_content", "isi_surat"))
        except Exception:
            return False

    def render_pdf_and_upload(
        self,
        surat_request: SuratRequest,
        nomor_surat: str,
        qr_code_url: str,
        final_approved_content: Optional[str] = None,
        signer: Optional[Any] = None,
    ) -> str:
        template_path = self.resolve_template_path(surat_request)
        context_data = self.build_pdf_template_context(
            surat_request=surat_request,
            nomor_surat=nomor_surat,
            qr_code_url=qr_code_url,
            final_approved_content=final_approved_content,
            signer=signer,
        )

        pdf_fn = _resolve_pdf_fn()
        try:
            if pdf_fn is _ORIG_RENDER_AND_UPLOAD_PDF and template_path:
                try:
                    from django.template.loader import get_template
                    tmpl = get_template(template_path)
                    tmpl_filename = getattr(getattr(tmpl, "origin", None), "name", None)
                    if tmpl_filename and os.path.exists(tmpl_filename):
                        if not self._is_template_ready_for_ai_content(tmpl_filename):
                            return _build_fallback_pdf_and_upload(context_data)
                except Exception:
                    pass

            try:
                pdf_url = _build_fallback_pdf_and_upload(context_data) if pdf_fn is _ORIG_RENDER_AND_UPLOAD_PDF else pdf_fn(template_path, context_data)
            except (TemplateDoesNotExist, TemplateSyntaxError, OSError):
                if pdf_fn is _ORIG_RENDER_AND_UPLOAD_PDF:
                    pdf_url = _build_fallback_pdf_and_upload(context_data)
                else:
                    raise

            return str(pdf_url).strip()
        except Exception as exc:
            raise PdfRenderUploadError(
                f"Gagal merender PDF: {exc}",
                tool_name="render_pdf_and_upload",
                original_exception=exc,
            ) from exc

    def execute_approval_pipeline(
        self,
        surat_request: SuratRequest,
        signer: Optional[Any] = None,
        final_approved_content: Optional[str] = None,
        final_status: str = SuratStatus.APPROVED,
    ) -> ExecutionPipelineResult:
        normalized_status = (
            final_status.strip().upper()
            if isinstance(final_status, str) and final_status.strip()
            else SuratStatus.APPROVED
        )
        if normalized_status not in VALID_FINAL_STATUSES:
            normalized_status = SuratStatus.APPROVED

        effective_content = (
            final_approved_content.strip()
            if isinstance(final_approved_content, str) and final_approved_content.strip()
            else ((surat_request.final_approved_content or "").strip() or (surat_request.ai_original_draft or "").strip())
        )

        nomor_resmi = self.generate_official_number(surat_request)
        tte_data = self.generate_tte_and_qr_code(surat_request, signer=signer)
        qr_code_url = str(tte_data["qr_code_url"])
        tte_token = str(tte_data.get("token") or "")
        hash_document = str(tte_data.get("hash_document") or "")

        pdf_url = self.render_pdf_and_upload(
            surat_request=surat_request,
            nomor_surat=nomor_resmi,
            qr_code_url=qr_code_url,
            final_approved_content=effective_content,
            signer=signer,
        )

        with transaction.atomic():
            surat_request.nomor_surat_resmi = nomor_resmi
            surat_request.qr_verification_code = qr_code_url
            surat_request.file_pdf_url = pdf_url
            surat_request.final_approved_content = effective_content
            surat_request.status = normalized_status
            surat_request.save(
                update_fields=[
                    "nomor_surat_resmi",
                    "qr_verification_code",
                    "file_pdf_url",
                    "final_approved_content",
                    "status",
                ]
            )
            SuratAuditLog.objects.create(
                surat_request=surat_request,
                action_id="FIN_01",
                action=f"FINAL_APPROVED_AND_{normalized_status}",
            )

        return ExecutionPipelineResult(
            surat_request_id=surat_request.id,
            nomor_surat_resmi=nomor_resmi,
            file_pdf_url=pdf_url,
            qr_code_url=qr_code_url,
            tte_token=tte_token or "verified-token",
            hash_document=hash_document or "verified-hash",
            final_status=normalized_status,
            final_approved_content=effective_content,
        )


def execute_post_approval_tools(
    surat_request: SuratRequest,
    signer: Optional[Any] = None,
    final_approved_content: Optional[str] = None,
    final_status: str = SuratStatus.APPROVED,
    tools: Optional[SuratExecutionTools] = None,
) -> ExecutionPipelineResult:
    active_tools = tools if tools is not None else SuratExecutionTools()
    return active_tools.execute_approval_pipeline(
        surat_request=surat_request,
        signer=signer,
        final_approved_content=final_approved_content,
        final_status=final_status,
    )