$ErrorActionPreference = 'Stop'
$backend = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $backend
# Isi master data kampus (aman dijalankan berulang; data lama tidak dihapus).
& ".\.venv\Scripts\python.exe" manage.py migrate
& ".\.venv\Scripts\python.exe" manage.py seed_master_data
