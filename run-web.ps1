$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend-django"
$FrontendDir = Join-Path $Root "frontend"
$VenvDir = Join-Path $BackendDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
foreach ($var in @("DATABASE_URL", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT", "REDIS_URL")) {
    Remove-Item "Env:$var" -ErrorAction SilentlyContinue
}
$env:DEBUG = "True"
$env:DJANGO_SETTINGS_MODULE = "core.settings"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[ASURA] Membuat virtual environment mandiri di $VenvDir ..." -ForegroundColor Yellow
    python -m venv $VenvDir
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $BackendDir "requirements.txt")
}
Write-Host "[ASURA] Menjalankan migrasi database & seed data..." -ForegroundColor Cyan
Push-Location $BackendDir
& $VenvPython manage.py migrate --noinput
& $VenvPython manage.py seed_master_data --skip-if-seeded
Pop-Location
Write-Host "[ASURA] Menjalankan Backend Django di http://127.0.0.1:8000 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$BackendDir'; `$env:DEBUG='True'; Remove-Item Env:DATABASE_URL,Env:REDIS_URL -ErrorAction SilentlyContinue; & '$VenvPython' manage.py runserver 127.0.0.1:8000"
Write-Host "[ASURA] Menunggu server backend siap..." -ForegroundColor Cyan
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/schema/" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { break }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "[ASURA] Menginstal dependensi Web Frontend..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    npm install
    Pop-Location
}
Write-Host "[ASURA] Menjalankan Web Frontend di http://127.0.0.1:5173 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$FrontendDir'; npm run dev -- --host 127.0.0.1 --port 5173"
