$ErrorActionPreference = 'Stop'
$backend = Split-Path -Parent $MyInvocation.MyCommand.Path
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Where-Object { $_.CommandLine -like "*$backend*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Set-Location -LiteralPath $backend
& ".\.venv\Scripts\python.exe" manage.py reset_local_db
