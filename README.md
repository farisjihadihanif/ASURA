# ASURA — Auto Surat Reasoning Agent

Asisten AI untuk pengajuan surat administrasi kampus. Mahasiswa cukup **mengobrol**; ASURA mengumpulkan data, menyusun draf surat, mengirimkannya ke pejabat yang berwenang (Kaprodi/Dekan) untuk disetujui, lalu menerbitkan PDF bertanda tangan elektronik berkode QR.

Dokumentasi lengkap (latar belakang, definisi, teknologi, struktur, alur): [`docs/DOKUMENTASI.md`](docs/DOKUMENTASI.md)

## Komponen

| Folder | Isi |
|---|---|
| `backend-django/` | REST API Django + DRF, agen AI (Gemini), PDF, approval, notifikasi |
| `frontend/` | Web React + Vite + Tailwind (mahasiswa & dosen) |
| `desktop-app/` | Aplikasi desktop Windows (Electron) berupa maskot/widget chat |

## Menjalankan secara lokal (Windows, PowerShell)

Prasyarat: Python 3.11+, Node.js 20+.

```powershell
cd backend-django
copy .env.example .env      # isi GEMINI_API_KEY (opsional untuk uji tanpa AI)
.\run-local.ps1             # venv, migrate, seed_surat, seed_master_data, jalankan server :8000
```

Web:
```powershell
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Desktop:
```powershell
cd desktop-app
npm install
npm start                   # build portable: npm run dist  -> ASURA-Portable.exe
```

Hanya mengisi ulang data master: `backend-django\seed-master.ps1`
(`python manage.py seed_master_data` ; `--wipe` hanya untuk DB lokal, **jangan** pada database bersama/produksi).

## Akun & NIM

Tidak ada akun demo. Semua akun hasil seed berstatus **belum diaktivasi**. Buka halaman **Daftar/Aktivasi**, masukkan NIM atau NIP, data otomatis muncul, lalu isi email dan kata sandi.

Format NIM (11 digit): `AA SS FF PPP UU` = angkatan, semester masuk (10 ganjil / 20 genap), fakultas (Teknik 60, Sains dan Teknologi 70, Kedokteran 80), prodi (500–507), nomor urut.
Contoh: **23106050031** (Teknik Informatika angkatan 23). Satu angkatan berisi 135 mahasiswa, urut dimulai 01. Daftar lengkap ada di `data-master-kampus.xlsx`.

## Jenis surat & penyetuju

Katalog surat dikelola di `surat/services/campus_catalog.py`. **Dekan** hanya menyetujui `SK-MK` (aktif kuliah) dan `SK-UKT` (pembayaran UKT); **semua surat lain** disetujui **Kaprodi**. Surat kustom (`CUSTOM-UMUM`, `CUSTOM-SAKIT`) bersifat pribadi: tanpa kop, tanpa approval.

## Variabel lingkungan (`backend-django/.env`)

`DJANGO_SECRET_KEY`, `DEBUG`, `DATABASE_URL` (Postgres/Supabase; kosong = SQLite), `REDIS_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL_NAME`, `AGENT_TIMEOUT_SECONDS`, `AGENT_MAX_REVISIONS`, `AGENT_CRITIQUE_MIN_SCORE`, `CLOUDINARY_*`, `RESEND_API_KEY` / `BREVO_API_KEY`, `DEFAULT_FROM_EMAIL`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `DEMO_ONE_STEP_APPROVAL` (default `False`).
Frontend: `VITE_API_BASE_URL`. Desktop: `ASURA_API_BASE_URL`.

## Deploy ringkas

1. **Backend**: Render (Docker, `backend-django/Dockerfile`, port 8000) + Supabase Postgres. Set env di atas, lalu jalankan sekali: `python manage.py migrate && python manage.py seed_surat && python manage.py seed_master_data --skip-if-seeded`.
2. **Frontend**: build `npm run build` dengan `VITE_API_BASE_URL` menunjuk ke backend; host di Vercel/Netlify/Render Static. Tambahkan domainnya ke `CORS_ALLOWED_ORIGINS`.
3. **Desktop**: set `ASURA_API_BASE_URL` ke backend produksi lalu `npm run dist`.
4. URL verifikasi QR memakai `https://auto-surat-backend.onrender.com/surat/verify/<token>/`; sesuaikan bila domain backend berubah.
