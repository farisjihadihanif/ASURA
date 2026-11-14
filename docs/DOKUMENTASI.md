# Dokumentasi ASURA — Auto Surat Reasoning Agent

## 1. Latar Belakang

Pengurusan surat di kampus (surat aktif kuliah, keterangan UKT, rekomendasi, izin kegiatan, dan sejenisnya) umumnya masih manual: mahasiswa harus tahu format dan syarat tiap surat, mengisi formulir, menunggu tanda tangan basah, lalu mengambil surat secara fisik. Akibatnya:

- mahasiswa sering salah format atau kurang data sehingga bolak-balik revisi;
- staf dan dosen menghabiskan waktu menyusun dan memeriksa surat yang bentuknya berulang;
- status pengajuan tidak transparan, dan keaslian surat sulit diverifikasi pihak luar.

ASURA dibuat untuk menyederhanakan alur itu: pemohon cukup berbicara dengan asisten, AI menyusun naskah resmi, pejabat hanya meninjau dan menyetujui, dan surat terbit sebagai PDF dengan tanda tangan elektronik yang bisa diverifikasi lewat QR.

## 2. Definisi dan Fungsi

**ASURA (Auto Surat Reasoning Agent)** adalah sistem layanan surat administrasi kampus berbasis percakapan dan agen AI.

Fungsi utama:
1. **Pengajuan lewat chat** — AI mengenali jenis surat, menanyakan data yang kurang (slot filling), dan memvalidasi kelayakan (mis. semester, SKS).
2. **Penyusunan draf otomatis** — agen AI (Gemini) menyusun naskah sesuai tata naskah dinas, menilai dirinya sendiri (self-critique) dan merevisi bila skor rendah.
3. **Approval berjenjang** — draf masuk antrean pejabat: Dekan untuk SK-MK dan SK-UKT, Kaprodi untuk surat lain. Pejabat dapat menyetujui, menolak, atau meminta revisi.
4. **Revisi** — catatan pejabat diterjemahkan AI menjadi panduan bagi mahasiswa; setelah mahasiswa melengkapi lewat chat, draf disusun ulang dan dikirim kembali.
5. **Pembelajaran dari suntingan dosen** — hasil suntingan dosen yang disetujui dijadikan contoh gaya (tanpa data pribadi) untuk draf berikutnya.
6. **Penerbitan** — PDF dengan nomor surat, tanda tangan elektronik, dan QR; dapat diunduh, dicetak, atau dikirim lewat email.
7. **Verifikasi keaslian** — memindai QR membuka halaman verifikasi publik.
8. **Surat kustom pribadi** — surat umum/sakit tanpa kop dan tanpa approval, tidak terlihat oleh dosen.
9. **Notifikasi** — lonceng notifikasi di web/desktop, juga email dan Telegram bila dikonfigurasi.
10. **Aktivasi akun berbasis data kampus** — pengguna mendaftar dengan NIM/NIP yang sudah ada di data master, bukan membuat identitas sendiri.

Pengguna: **Mahasiswa** (mengajukan) dan **Dosen/Pejabat** (Kaprodi, Dekan; menyetujui). Tidak ada peran admin.

## 3. Teknologi

| Lapisan | Teknologi |
|---|---|
| Backend | Python 3.11, Django 5, Django REST Framework, SimpleJWT (autentikasi kustom NIM/NIP), drf-spectacular |
| AI | Google Gemini (`google-genai`, model flash dengan fallback), skema Pydantic untuk keluaran terstruktur |
| PDF & QR | xhtml2pdf, pypdf, `qrcode` |
| Data | PostgreSQL (Supabase) produksi; SQLite untuk lokal; Redis/`django-redis` untuk state chat; Cloudinary untuk berkas |
| Notifikasi | Resend / Brevo (email), Telegram |
| Web | React 19, Vite, TypeScript, Tailwind CSS v4, axios, react-router-dom 7, lucide-react |
| Desktop | Electron 35 (widget maskot frameless, selalu di atas), electron-builder (portable `.exe`) |
| Deploy | Docker (python:3.11-slim, uvicorn ASGI), Render, Supabase |

## 4. Struktur Proyek

```
ASURA/
├── README.md
├── docs/DOKUMENTASI.md
├── data-master-kampus.xlsx        # daftar NIM/NIP/mata kuliah hasil seed
├── backend-django/
│   ├── Dockerfile, requirements.txt, .env.example
│   ├── run-local.ps1, seed-master.ps1
│   ├── core/                      # settings, urls, asgi
│   ├── accounts/                  # User, Faculty, Department, Course, Lecturer, Student, StudentCourse
│   │   ├── campus_master.py       # aturan NIM, fakultas/prodi, nama, mata kuliah dummy
│   │   ├── register_views.py      # lookup & aktivasi akun
│   │   ├── backends.py            # login (menolak akun belum diaktivasi)
│   │   └── management/commands/seed_master_data.py
│   └── surat/
│       ├── models.py              # SuratType, SuratRequest, SuratApproval, ChatThread/Message,
│       │                          # Notification, TteSignature, AuditLog, AgentFeedbackMemory, ...
│       ├── views.py, views_extra.py, urls.py
│       ├── agents/                # letter_agent, memory_agent, prompts, schemas, slot_memory,
│       │                          # backend_bridge, execution_tools
│       └── services/              # chat_workflow, detect_intent, campus_catalog, manual_handlers,
│                                  # workflow_service, revision_assistant, custom_letter_ai,
│                                  # pdf_generator_safe, conversational_ai
├── frontend/src/                  # pages, components, hooks, services (axios)
└── desktop-app/                   # main.js (IPC/API), preload.js, renderer.js, index.html
```

Model data: `Faculty → Department → Course`; `User ↔ Student/Lecturer`; `Student ↔ Course` lewat `StudentCourse`. Pejabat ditandai lewat jabatan dosen (Ketua Program Studi / Dekan Fakultas).

## 5. Alur

### 5.1 Aktivasi akun
NIM/NIP dimasukkan → sistem mencari di data master (`GET /api/accounts/register/lookup/`) dan menampilkan nama, fakultas, prodi → pengguna mengisi email dan kata sandi (`POST /api/accounts/register/`) → akun aktif dan dapat login. Akun seed berstatus belum diaktivasi (hash kata sandi tidak valid) sampai langkah ini selesai.

### 5.2 Pengajuan surat (alur utama)
```
Mahasiswa chat
  → deteksi intent (jenis surat)
  → slot filling + validasi kelayakan
  → agen AI menyusun draf + self-critique
  → status SUBMITTED → PENDING_APPROVAL
  → approver ditentukan (Dekan: SK-MK/SK-UKT, selain itu Kaprodi; fallback antar-pejabat)
  → pejabat: Setujui / Tolak / Minta revisi
  → APPROVED → nomor surat + TTE + QR → PDF
  → SENT (email) atau PRINTED
```
Status: `SUBMITTED, PENDING_APPROVAL, APPROVED, SENT, PRINTED, REVISION_REQUIRED, REJECTED, FAILED`.

### 5.3 Revisi
Pejabat memilih "Perlu revisi" + catatan → status `REVISION_REQUIRED`, mahasiswa menerima notifikasi dan panduan AI → mahasiswa membalas di chat → draf disusun ulang, antrean lama dibersihkan, pejabat diberi tahu → kembali ke persetujuan.

### 5.4 Pembelajaran dari suntingan dosen
Saat surat disetujui dengan isi berbeda dari draf AI, versi final disanitasi dari data pribadi dan dipakai sebagai contoh gaya pada pembuatan draf surat sejenis berikutnya.

### 5.5 Verifikasi QR
Pindai QR → `GET /surat/verify/<token>/` → menampilkan keabsahan, nomor surat, penandatangan, dan tanggal.

### 5.6 Endpoint utama (`/api/surat/`)
`types/`, `request/`, `requests/`, `requests/<id>/`, `requests/<id>/preview-pdf|download-pdf|mark-printed|deliver-email|re-draft/`, `approval/<id>/action/`, `verify/<token>/`, `chat/init/`, `chat/threads/`, `chat/<thread_id>/`, `notifications/` (+ `unread-count/`, `<id>/read/`, `read-all/`). Dokumentasi interaktif tersedia lewat drf-spectacular.

## 6. Data Master (dummy)

3 fakultas (Teknik 60, Sains dan Teknologi 70, Kedokteran 80) × 8 prodi (kode 500–507) = 24 prodi; 576 mata kuliah (semester 1–8); 120 dosen (5 per prodi, termasuk Kaprodi dan Dekan); 135 mahasiswa per angkatan (23–26) ditambah akun pengembang. Detail dan daftar NIM: `data-master-kampus.xlsx`.

## 7. Batasan Saat Ini
- Kode fakultas 70/80 dan pemetaan Dekan/Kaprodi bersifat asumsi, perlu disesuaikan dengan kebijakan kampus.
- Penggunaan Gemini dibatasi kuota; saat terbatas, AI memakai fallback.
- Tanda tangan elektronik bersifat internal ASURA (bukan sertifikat TTE tersertifikasi BSrE).
