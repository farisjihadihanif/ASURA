param(
    [switch]$Web
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend-django"
$FrontendDir = Join-Path $Root "frontend"
$DesktopDir = Join-Path $Root "desktop-app"
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
Push-Location $BackendDir
& $VenvPython manage.py migrate --noinput
& $VenvPython manage.py seed_master_data --skip-if-seeded
Pop-Location
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$BackendDir'; `$env:DEBUG='True'; Remove-Item Env:DATABASE_URL,Env:REDIS_URL -ErrorAction SilentlyContinue; & '$VenvPython' manage.py runserver 127.0.0.1:8000"
# Tunggu backend siap agar frontend/desktop tidak kena ECONNREFUSED saat startup
Write-Host "[ASURA] Menunggu backend siap di 127.0.0.1:8000 ..." -ForegroundColor Yellow
for ($i = 0; $i -lt 60; $i++) {
    if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -WarningAction SilentlyContinue -InformationLevel Quiet)) { break }
    Start-Sleep -Seconds 1
}
if ($Web) {
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Push-Location $FrontendDir
        npm install
        Pop-Location
    }
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$FrontendDir'; npm run dev -- --host 127.0.0.1 --port 5173"
}
if (-not (Test-Path (Join-Path $DesktopDir "node_modules"))) {
    Push-Location $DesktopDir
    npm install
    Pop-Location
}
Push-Location $DesktopDir
$env:ASURA_API_BASE_URL = "http://127.0.0.1:8000"
npm start
Pop-Location
