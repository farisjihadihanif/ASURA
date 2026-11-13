import base64
import os
from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import SuratRequest
from .services.pdf_generator_safe import generate_and_save_official_pdf
@method_decorator(xframe_options_exempt, name="dispatch")
class SuratPreviewPdfAPIView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    def get(self, request, pk: int):
        surat_req = (
            SuratRequest.objects.select_related(
                "student",
                "student__user",
                "student__prodi",
                "student__fakultas",
                "kode_surat",
            )
            .filter(pk=pk)
            .first()
        )
        if not surat_req:
            return Response(
                {"error": f"Surat dengan ID {pk} tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND,
            )
        pdf_dir = os.path.join(settings.BASE_DIR, "media", "generated_pdf")
        os.makedirs(pdf_dir, exist_ok=True)
        nomor_clean = str(surat_req.nomor_surat_resmi or f"req_{pk}").replace("/", "_")
        target_pdf = os.path.join(pdf_dir, f"surat_{pk}.pdf")
        if not (os.path.exists(target_pdf) and os.path.getsize(target_pdf) > 0):
            student = surat_req.student
            prodi_nama = getattr(getattr(student, "prodi", None), "nama_prodi", None) or "Teknik Informatika"
            fakultas_nama = getattr(getattr(student, "fakultas", None), "nama_fakultas", None) or "Sains dan Teknologi"
            nomor_resmi = surat_req.nomor_surat_resmi or f"{pk:03d}/{surat_req.kode_surat.kode_surat}/FT/2026"
            effective_content = (
                (surat_req.final_approved_content or "").strip()
                or (surat_req.ai_original_draft or "").strip()
                or f"Dengan ini menerangkan bahwa {student.user.nama} (NIM {student.nim}) mengajukan {surat_req.kode_surat.nama_surat}."
            )
            generate_and_save_official_pdf(
                {
                    "id": surat_req.id,
                    "surat_request_id": surat_req.id,
                    "nomor_surat": nomor_resmi,
                    "nama_surat": surat_req.kode_surat.nama_surat,
                    "nama_mahasiswa": student.user.nama,
                    "nim": student.nim,
                    "program_studi": prodi_nama,
                    "fakultas": fakultas_nama,
                    "semester_aktif": getattr(student, "semester_aktif", "-"),
                    "tahun_akademik": getattr(student, "tahun_akademik", "-"),
                    "final_approved_content": effective_content,
                    "isi_surat": effective_content,
                    "payload": surat_req.payload_data or {},
                    "qr_verification_code": surat_req.qr_verification_code or nomor_resmi,
                }
            )
        with open(target_pdf, "rb") as f_pdf:
            pdf_bytes = f_pdf.read()
        if request.query_params.get("format") == "base64":
            return Response(
                {
                    "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                    "filename": f"surat_{nomor_clean}.pdf",
                },
                status=status.HTTP_200_OK,
            )
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="surat_{nomor_clean}.pdf"'
        resp["Content-Security-Policy"] = "frame-ancestors 'self' http://localhost:* http://127.0.0.1:*"
        return resp
class SuratDownloadPdfAPIView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    def get(self, request, pk: int):
        resp = SuratPreviewPdfAPIView().get(request, pk)
        if hasattr(resp, "headers") and "Content-Disposition" in resp:
            resp["Content-Disposition"] = resp["Content-Disposition"].replace("inline;", "attachment;")
        return resp
