import re

from django.contrib.auth.hashers import make_password
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .campus_master import parse_nim
from .models import Lecturer, Student, User

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_claimed(user: User) -> bool:
    """Akun master data belum diklaim selama password-nya masih berupa hash 'tidak dapat dipakai' (diawali '!')."""
    return bool(user.password) and not user.password.startswith("!")


def _profile_payload(user: User) -> dict:
    if user.role == "STUDENT":
        st = Student.objects.filter(user=user).select_related("fakultas", "prodi").first()
        if not st:
            return {}
        info = parse_nim(st.nim) or {}
        return {
            "nama": user.nama,
            "role": "STUDENT",
            "nip_nim": user.nip_nim,
            "fakultas": st.fakultas.nama_fakultas,
            "prodi": st.prodi.nama_prodi,
            "angkatan": 2000 + info["angkatan"] if info else st.tahun_masuk,
            "semester_aktif": st.semester_aktif,
        }
    lec = Lecturer.objects.filter(user=user).select_related("fakultas", "prodi").first()
    if not lec:
        return {}
    return {
        "nama": user.nama,
        "role": "LECTURER",
        "nip_nim": user.nip_nim,
        "fakultas": lec.fakultas.nama_fakultas,
        "prodi": lec.prodi.nama_prodi,
        "jabatan": (lec.jabatan_struktural or [None])[0] or "Dosen",
    }


class RegisterLookupAPIView(APIView):
    """Cek NIM/NIP terhadap master data kampus; data diri terisi otomatis."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        nip_nim = str(request.query_params.get("nip_nim") or "").strip()
        if len(nip_nim) < 4:
            return Response({"status": "error", "message": "Masukkan NIM/NIP."}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(nip_nim__iexact=nip_nim).first()
        if not user:
            return Response(
                {"status": "error", "message": "NIM/NIP tidak ditemukan di data kampus."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if _is_claimed(user):
            return Response(
                {"status": "error", "message": "NIM/NIP ini sudah terdaftar. Silakan masuk."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"status": "success", "data": _profile_payload(user)})


class RegisterAPIView(APIView):
    """Aktivasi akun: pengguna hanya mengisi NIM/NIP, email, dan kata sandi. Data lain dari master kampus."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data
        nip_nim = str(data.get("nip_nim") or "").strip()
        email = str(data.get("email") or "").strip()
        password = str(data.get("password") or "")

        errors = {}
        user = User.objects.filter(nip_nim__iexact=nip_nim).first() if nip_nim else None
        if not user:
            errors["nip_nim"] = "NIM/NIP tidak ditemukan di data kampus."
        elif _is_claimed(user):
            errors["nip_nim"] = "NIM/NIP sudah terdaftar. Silakan masuk."
        if email and not EMAIL_PATTERN.match(email):
            errors["email"] = "Format email tidak valid."
        if len(password) < 8:
            errors["password"] = "Kata sandi minimal 8 karakter."
        if errors:
            return Response(
                {"status": "error", "message": "Validasi gagal", "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user.password = make_password(password)
            if email:
                user.email = email
            user.save(update_fields=["password", "email"])

        refresh = RefreshToken()
        refresh["user_id"] = user.id
        refresh["role"] = user.role
        refresh["nip_nim"] = user.nip_nim
        return Response(
            {
                "message": "Pendaftaran berhasil",
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "id": user.id,
                    "nama": user.nama,
                    "nip_nim": user.nip_nim,
                    "role": user.role,
                    "email": user.email,
                },
            },
            status=status.HTTP_201_CREATED,
        )

