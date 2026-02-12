# dev-licensing.ps1 — Start the licensing server for local development
# Usage: .\dev-licensing.ps1

$ErrorActionPreference = "Stop"

Write-Host "Starting PromptShield Licensing Server..." -ForegroundColor Cyan

$licensingDir = Join-Path $PSScriptRoot "src-licensing"
$venvPython = Join-Path $licensingDir ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating licensing server venv..." -ForegroundColor Yellow
    Push-Location $licensingDir
    python -m venv .venv
    & $venvPython -m pip install --upgrade pip
    & .\.venv\Scripts\pip.exe install -e ".[dev]"
    Pop-Location
}

Push-Location $licensingDir
Write-Host "Licensing server running on http://localhost:8443" -ForegroundColor Green
Write-Host "API docs: http://localhost:8443/docs" -ForegroundColor DarkGray
& $venvPython main.py
Pop-Location
