# Menjalankan Backend ASURA

## Persiapan Windows

```powershell
cd "auto-surat-backend\backend-django"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Isi minimal `.env` sebelum memakai AI dan pengiriman email:

- `DJANGO_SECRET_KEY`
- `GEMINI_API_KEY`
- `DATABASE_URL` (atau gunakan SQLite untuk development jika konfigurasi project mengizinkannya)
- kredensial SMTP/email
- kredensial Cloudinary bila PDF akan disimpan ke Cloudinary

Lanjutkan:

```powershell
python manage.py migrate
python manage.py seed_data
python manage.py runserver 8000
```

Backend tersedia di `http://localhost:8000`. Endpoint chat yang dipakai web dan Windows:

- `POST /surat/chat/init/`
- `GET /surat/chat/`
- `GET /surat/chat/<thread_id>/`
- `POST /surat/chat/<thread_id>/`

Prefix `/api/` juga tersedia untuk web dan desktop baru, misalnya
`POST /api/surat/chat/init/`. Route tanpa `/api/` dipertahankan untuk kompatibilitas.

Reset database lokal tanpa menghapus `db.sqlite3`:

```powershell
.\reset-dev.ps1
```

## Catatan PDF di Windows

WeasyPrint membutuhkan library GTK/Pango native. `manage.py check` tidak memerlukan
library tersebut karena import PDF dibuat lazy, tetapi penerbitan PDF tetap memerlukan
instalasi runtime WeasyPrint/GTK atau deployment backend menggunakan Linux container.
