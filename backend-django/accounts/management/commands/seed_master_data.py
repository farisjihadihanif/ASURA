import random
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.campus_master import (
    ANGKATAN_LIST, CORE_COURSES, FACULTIES, FARIS_NIM, JOEL_NIP, LECTURERS_PER_PRODI,
    SHARED_COURSES, academic_year_and_semester, build_nim, lecturer_nip, person_name,
    TITLES, DEGREES,
)
from accounts.models import (
    Course, Department, Faculty, Lecturer, Student, StudentCourse, User,
)


def _upsert_user(nip: str, nama: str, role: str) -> User:
    """Buat user bila belum ada; bila sudah ada (data lama) pertahankan id/password, hanya samakan nama & peran."""
    user = User.objects.filter(nip_nim=nip).first()
    if user is None:
        return User.objects.create(id=f"U-{nip}", nip_nim=nip, nama=nama, role=role, password=_unclaimed_password())
    user.nama = nama
    user.role = role
    user.save(update_fields=["nama", "role"])
    return user


def _unclaimed_password() -> str:
    """Password tidak dapat dipakai login sampai pemilik NIM/NIP mendaftar (klaim akun)."""
    return make_password(None)


class Command(BaseCommand):
    help = (
        "Mengisi master data kampus dummy (3 fakultas, 24 prodi, mata kuliah semester 1-8, dosen, "
        "dekan/kaprodi, mahasiswa). Akun belum aktif sampai pemiliknya mendaftar memakai NIM/NIP."
    )

    def add_arguments(self, parser):
        parser.add_argument("--skip-if-seeded", action="store_true", help="Lewati bila master data sudah terisi (cepat, untuk run-local).")
        parser.add_argument("--wipe", action="store_true", help="Hapus user/fakultas/prodi/matkul lama sebelum seed.")

    def handle(self, *args, **opts):
        if opts.get("skip_if_seeded") and Department.objects.filter(id="FT-TIF").exists() and Student.objects.filter(nim=FARIS_NIM).exists() and Student.objects.count() >= 500:
            self.stdout.write("Master data sudah terisi, dilewati.")
            return
        self._seed(opts)

    @transaction.atomic
    def _seed(self, opts):
        if opts["wipe"]:
            StudentCourse.objects.all().delete()
            Student.objects.all().delete()
            Faculty.objects.update(dekan=None, wadek_1=None, wadek_3=None)
            Department.objects.update(kaprodi=None)
            Lecturer.objects.all().delete()
            User.objects.all().delete()
            Course.objects.all().delete()
            Department.objects.all().delete()
            Faculty.objects.all().delete()
            self.stdout.write("Data lama dihapus.")

        rnd = random.Random(2026)
        counter = 0
        stu_counter = 0
        keep_nims = set()
        prodi_rank = 0
        n_lec = n_stu = n_course = 0

        for kode_fak, fak_id, fak_nama, prodis in FACULTIES:
            faculty, _ = Faculty.objects.update_or_create(id=fak_id, defaults={"nama_fakultas": f"Fakultas {fak_nama}"})
            first_prodi_lecturers = []

            for p_idx, (kode_prodi, prodi_id, prodi_nama, abbr) in enumerate(prodis):
                dept, _ = Department.objects.update_or_create(
                    id=prodi_id, defaults={"fakultas": faculty, "nama_prodi": prodi_nama}
                )

                # --- Mata kuliah semester 1-8 ---
                courses_by_sem = {}
                core = CORE_COURSES[prodi_id]
                for sem in range(1, 9):
                    specs = [
                        (f"{abbr}{sem}01", core[(sem - 1) * 2], 3),
                        (f"{abbr}{sem}02", core[(sem - 1) * 2 + 1], 3),
                        (f"{abbr}{sem}03", SHARED_COURSES[sem - 1], 6 if sem == 8 else 2),
                    ]
                    rows = []
                    for kode, nama, sks in specs:
                        course, _ = Course.objects.update_or_create(
                            kode_matkul=kode, defaults={"nama_matkul": nama, "sks": sks, "prodi": dept}
                        )
                        rows.append(course)
                        n_course += 1
                    courses_by_sem[sem] = rows

                # --- Dosen prodi ---
                lecturers = []
                for i in range(LECTURERS_PER_PRODI):
                    counter += 1
                    nip = JOEL_NIP if (fak_id == "FT" and p_idx == 0 and i == 1) else lecturer_nip(counter)
                    if fak_id == "FT" and p_idx == 0 and i == 1:
                        nama = "Dr. Joel Evans, M.T."
                    else:
                        title = TITLES[counter % len(TITLES)]
                        nama = f"{title} {person_name(counter, 1)}, {DEGREES[counter % len(DEGREES)]}".strip()
                    user = _upsert_user(nip, nama, "LECTURER")
                    lec = Lecturer.objects.filter(user=user).first()
                    if lec is None:
                        lec = Lecturer.objects.create(
                            id=f"L-{nip}", user=user, fakultas=faculty, prodi=dept, jabatan_struktural=[]
                        )
                    else:
                        lec.fakultas, lec.prodi = faculty, dept
                        lec.save(update_fields=["fakultas", "prodi"])
                    lecturers.append(lec)
                    n_lec += 1

                kaprodi = lecturers[0]
                kaprodi.jabatan_struktural = [f"Ketua Program Studi {prodi_nama}"]
                kaprodi.save(update_fields=["jabatan_struktural"])
                dept.kaprodi = kaprodi
                dept.save(update_fields=["kaprodi"])
                first_prodi_lecturers.append(lecturers) if p_idx == 0 else None

                # --- Mahasiswa per angkatan + KRS: total 135 mahasiswa per angkatan (24 prodi: 15 prodi x 6 + 9 prodi x 5) ---
                n_per_prodi = 6 if prodi_rank < 15 else 5
                prodi_rank += 1
                for a_idx, angkatan in enumerate(ANGKATAN_LIST):
                    urutan = list(range(1, n_per_prodi + 1))  # 01, 02, ... mudah diingat
                    if fak_id == "FT" and p_idx == 0 and angkatan == 23:
                        urutan.append(31)  # NIM Faris
                    tahun_akademik, tahun_masuk, semester = academic_year_and_semester(angkatan)
                    semester = min(semester, 8)
                    for urut in urutan:
                        nim = build_nim(angkatan, "GANJIL", kode_fak, kode_prodi, urut)
                        keep_nims.add(nim)
                        is_faris = nim == FARIS_NIM
                        stu_counter += 1
                        nama = "Faris Jihadi Hanif Lubis" if is_faris else person_name(stu_counter, 2)
                        user = _upsert_user(nim, nama, "STUDENT")
                        student, _ = Student.objects.update_or_create(
                            nim=nim,
                            defaults={
                                "user": user, "fakultas": faculty, "prodi": dept,
                                "semester_aktif": semester, "tahun_akademik": tahun_akademik,
                                "tahun_masuk": tahun_masuk, "status_akademik": "AKTIF",
                                "status_pembayaran_ukt": "LUNAS", "dosen_pembimbing_akademik": lecturers[2],
                                "nama_ortu": f"Bapak {person_name(stu_counter, 5).split()[0]}",
                                "pekerjaan_ortu": "Wiraswasta",
                            },
                        )
                        have = set(StudentCourse.objects.filter(student=student).values_list("course_id", flat=True))
                        ips, total_sks, new_rows = [], 0, []
                        for sem in range(1, semester + 1):
                            done = sem < semester
                            for c_i, course in enumerate(courses_by_sem[sem]):
                                ip = Decimal(str(round(rnd.uniform(2.8, 4.0), 2))) if done else None
                                if course.kode_matkul not in have:
                                    new_rows.append(StudentCourse(
                                        student=student, course=course,
                                        lecturer=lecturers[(sem + c_i) % len(lecturers)],
                                        semester_taken=sem, tahun_akademik=tahun_akademik,
                                        status_krs="LULUS" if done else "AMBIL", ip=ip,
                                    ))
                                if done:
                                    ips.append(float(ip))
                                    total_sks += course.sks
                        if new_rows:
                            StudentCourse.objects.bulk_create(new_rows, batch_size=200)
                        total_sks = 20 * (semester - 1)  # rata-rata beban studi 20 SKS per semester
                        student.total_sks = total_sks
                        student.total_sks_lulus = total_sks
                        student.ipk_kumulatif = Decimal(str(round(sum(ips) / len(ips), 2))) if ips else Decimal("0.00")
                        student.save(update_fields=["total_sks", "total_sks_lulus", "ipk_kumulatif"])
                        n_stu += 1

            # --- Dekan: dosen ke-2 prodi pertama fakultas ---
            dekan = first_prodi_lecturers[0][1]
            dekan.jabatan_struktural = [f"Dekan Fakultas {fak_nama}"]
            dekan.save(update_fields=["jabatan_struktural"])
            faculty.dekan = dekan
            faculty.wadek_1 = first_prodi_lecturers[0][3]
            faculty.wadek_3 = first_prodi_lecturers[0][4]
            faculty.save(update_fields=["dekan", "wadek_1", "wadek_3"])

        # Bersihkan mahasiswa hasil seed versi lama yang belum diaktivasi dan tidak ada di master sekarang.
        stale = User.objects.filter(role="STUDENT", password__startswith="!").exclude(nip_nim__in=keep_nims)
        stale = [u for u in stale if len(u.nip_nim) == 11 and u.nip_nim.isdigit()]
        for u in stale:
            u.delete()
        if stale:
            self.stdout.write(f"{len(stale)} mahasiswa seed lama (belum aktif) dibersihkan.")

        self.stdout.write(self.style.SUCCESS(
            f"Master data selesai: {n_lec} dosen, {n_stu} mahasiswa, {n_course} mata kuliah."
        ))
