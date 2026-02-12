<#
.SYNOPSIS
    Build the doc-anonymizer standalone executable (test builds).
.DESCRIPTION
    1. Builds the React frontend into frontend/dist
    2. Runs PyInstaller to bundle Python backend + frontend into a single .exe
    Output: src-python/dist/doc-anonymizer.exe
#>

param(
    [switch]$SkipFrontend,  # Skip frontend build if already done
    [switch]$Clean           # Clean previous build artifacts first
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $root) { $root = $PSScriptRoot }
# If the script is at the root, use current dir
if (-not (Test-Path "$root\frontend")) { $root = Get-Location }

Write-Host "`n=== Doc-Anonymizer Standalone Build ===" -ForegroundColor Cyan
Write-Host "Root: $root"

# ── Step 1: Build frontend ──
if (-not $SkipFrontend) {
    Write-Host "`n[1/3] Building frontend..." -ForegroundColor Yellow
    Push-Location "$root\frontend"
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
        Write-Host "Frontend built successfully" -ForegroundColor Green
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`n[1/3] Skipping frontend build" -ForegroundColor DarkGray
}

# Verify frontend dist exists
$frontendDist = Join-Path $root "frontend\dist\index.html"
if (-not (Test-Path $frontendDist)) {
    throw "Frontend dist not found at $frontendDist - run without -SkipFrontend"
}

# ── Step 2: Ensure PyInstaller is installed ──
Write-Host "`n[2/3] Checking PyInstaller..." -ForegroundColor Yellow
$pythonExe = Join-Path $root "src-python\.venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python venv not found at $pythonExe"
}

& $pythonExe -m pip install pyinstaller --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    & $pythonExe -m pip install pyinstaller
}

# ── Step 3: Run PyInstaller ──
Write-Host "`n[3/3] Building standalone executable..." -ForegroundColor Yellow
Push-Location "$root\src-python"
try {
    $specFile = "doc-anonymizer-standalone.spec"
    if (-not (Test-Path $specFile)) {
        throw "Spec file not found: $specFile"
    }

    $args = @("--clean", $specFile)
    if ($Clean) {
        # Remove previous build artifacts
        if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
        if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    }

    & $pythonExe -m PyInstaller @args
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    $exePath = Join-Path (Get-Location) "dist\prompt-shield.exe"
    if (Test-Path $exePath) {
        # Copy to bin/ at project root
        $binDir = Join-Path $root "bin"
        if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Path $binDir -Force | Out-Null }
        Copy-Item $exePath (Join-Path $binDir "prompt-shield.exe") -Force

        $size = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
        Write-Host "`n=== Build complete ===" -ForegroundColor Green
        Write-Host "Executable: $binDir\prompt-shield.exe" -ForegroundColor Green
        Write-Host "Size: ${size} MB" -ForegroundColor Green
        Write-Host "`nRun it with:"
        Write-Host "  .\bin\prompt-shield.exe" -ForegroundColor White
        Write-Host "`nOn first run, spaCy/BERT models will download automatically."
    } else {
        throw "Expected output not found at $exePath"
    }
} finally {
    Pop-Location
}
