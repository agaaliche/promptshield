<# 
  dev.ps1 — Start both backend and frontend for development.
  Usage:  .\dev.ps1            (starts both)
          .\dev.ps1 -Backend   (backend only)
          .\dev.ps1 -Frontend  (frontend only)
#>
param(
    [switch]$Backend,
    [switch]$Frontend
)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$pythonVenv = Join-Path $root "src-python\.venv\Scripts\python.exe"
$frontendDir = Join-Path $root "frontend"
$backendDir = Join-Path $root "src-python"

# If neither flag is set, start both
if (-not $Backend -and -not $Frontend) {
    $Backend = $true
    $Frontend = $true
}

# --- Backend ---
if ($Backend) {
    if (-not (Test-Path $pythonVenv)) {
        Write-Host "[!] Python venv not found at $pythonVenv" -ForegroundColor Red
        Write-Host "    Run setup first:  cd src-python && python -m venv .venv && .\.venv\Scripts\pip install -e .[dev]"
        exit 1
    }

    Write-Host "[*] Starting Python backend on port 8910..." -ForegroundColor Cyan
    $backendJob = Start-Process -NoNewWindow -PassThru -FilePath $pythonVenv `
        -ArgumentList "-u", "main.py" `
        -WorkingDirectory $backendDir
    Write-Host "    Backend PID: $($backendJob.Id)"
}

# --- Frontend ---
if ($Frontend) {
    Write-Host "[*] Starting Vite dev server..." -ForegroundColor Cyan
    $frontendJob = Start-Process -NoNewWindow -PassThru -FilePath "npx" `
        -ArgumentList "vite", "--host" `
        -WorkingDirectory $frontendDir
    Write-Host "    Frontend PID: $($frontendJob.Id)"
}

Write-Host ""
Write-Host "=== Development servers running ===" -ForegroundColor Green
if ($Backend)  { Write-Host "  Backend  → http://127.0.0.1:8910" }
if ($Frontend) { Write-Host "  Frontend → http://localhost:5173" }
Write-Host ""
Write-Host "Press Ctrl+C to stop all." -ForegroundColor Yellow

# Wait for Ctrl+C, then clean up
try {
    while ($true) { Start-Sleep -Seconds 1 }
}
finally {
    Write-Host "`n[*] Shutting down..." -ForegroundColor Yellow
    if ($backendJob  -and -not $backendJob.HasExited)  { Stop-Process -Id $backendJob.Id  -Force -ErrorAction SilentlyContinue }
    if ($frontendJob -and -not $frontendJob.HasExited) { Stop-Process -Id $frontendJob.Id -Force -ErrorAction SilentlyContinue }
    Write-Host "[*] Done." -ForegroundColor Green
}
