# ASURA — Agentic AI Academic Letter System

Struktur lengkap proyek **ASURA** di folder ini:
- `backend-django/` — Backend Django 5 + DRF + Agentic AI (10 jenis surat, Zero-Hallucination Slot-Filling, TTE SHA-256, TTD Manual Gambar, Email & PDF).
- `frontend/` — Aplikasi Web (React 19 + Vite + Tailwind CSS v4) dengan tampilan Chat ala Gemini untuk Mahasiswa & Dashboard Approval Dosen.
- `desktop-app/` — Aplikasi Windows (Electron) khusus Mahasiswa berupa ikon maskot Email melayang di pojok kanan bawah (`Minta ASURA`).
- `run-web.ps1` — Menjalankan Backend Django + Web Frontend secara lokal.
- `run-local.ps1` — Menjalankan Backend Django + Web Frontend (`-Web`) + Aplikasi Windows Electron.

## Akun Demo
- **Mahasiswa:** `INF24001` / `12345678`
- **Dosen:** `198001012005011001` / `12345678`

## Cara Menjalankan
1. Pastikan seluruh isi folder `ASURA` ini sudah diekstrak ke `D:\coolyeah\ASURA`.
2. Buka PowerShell di `D:\coolyeah\ASURA`:
   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\run-web.ps1
   ```
3. Untuk menjalankan juga aplikasi Windows Desktop (`desktop-app`):
   ```powershell
   .\run-local.ps1 -Web
   ```
