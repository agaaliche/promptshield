<#
.SYNOPSIS
    First-time setup for the Document Anonymizer project on a new dev machine.
.DESCRIPTION
    Checks and installs all required prerequisites, creates virtual environments,
    downloads dependencies (npm, pip, spaCy models), and validates the setup.

    Run from the project root:
        .\setup.ps1

    Flags:
        -SkipOptional    Skip optional dependencies (Tesseract, Rust/Tauri)
        -SpacyModel lg   Use en_core_web_lg instead of default en_core_web_sm
        -Force           Recreate venv / node_modules even if they exist
#>

param(
    [switch]$SkipOptional,
    [switch]$Force,
    [ValidateSet("sm", "lg")]
    [string]$SpacyModel = "sm"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
function Write-Step  { param([string]$msg) Write-Host "`n━━━ $msg ━━━" -ForegroundColor Cyan }
function Write-Ok    { param([string]$msg) Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn  { param([string]$msg) Write-Host "  ⚠ $msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$msg) Write-Host "  ✗ $msg" -ForegroundColor Red }
function Write-Info  { param([string]$msg) Write-Host "  → $msg" -ForegroundColor Gray }

function Test-Command { param([string]$cmd) return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

$failed = @()

# ─────────────────────────────────────────────
#  1. Check prerequisites
# ─────────────────────────────────────────────
Write-Step "Checking prerequisites"

# Node.js
if (Test-Command "node") {
    $nodeVer = (node --version) -replace '^v', ''
    $nodeMajor = [int]($nodeVer -split '\.')[0]
    if ($nodeMajor -ge 18) {
        Write-Ok "Node.js $nodeVer"
    } else {
        Write-Err "Node.js $nodeVer found but ≥18 required"
        $failed += "Node.js"
    }
} else {
    Write-Err "Node.js not found — install from https://nodejs.org (≥18)"
    $failed += "Node.js"
}

# npm
if (Test-Command "npm") {
    Write-Ok "npm $(npm --version)"
} else {
    Write-Err "npm not found (comes with Node.js)"
    $failed += "npm"
}

# Python
$pythonCmd = $null
foreach ($cmd in @("python", "python3")) {
    if (Test-Command $cmd) {
        $pyVer = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($pyVer) {
            $pyMajor, $pyMinor = $pyVer -split '\.'
            if ([int]$pyMajor -ge 3 -and [int]$pyMinor -ge 11) {
                $pythonCmd = $cmd
                Write-Ok "Python $pyVer ($cmd)"
                break
            }
        }
    }
}
if (-not $pythonCmd) {
    Write-Err "Python ≥3.11 not found — install from https://www.python.org/downloads/"
    $failed += "Python"
}

# Git
if (Test-Command "git") {
    Write-Ok "Git $(git --version | Select-String -Pattern '\d+\.\d+\.\d+' | ForEach-Object { $_.Matches.Value })"
} else {
    Write-Warn "Git not found — recommended for version control"
}

# Rust (optional)
if (-not $SkipOptional) {
    if (Test-Command "rustc") {
        Write-Ok "Rust $(rustc --version | Select-String -Pattern '\d+\.\d+\.\d+' | ForEach-Object { $_.Matches.Value })"
    } else {
        Write-Warn "Rust not found — needed only for Tauri desktop builds"
        Write-Info "Install from https://rustup.rs"
    }
}

# Tesseract (optional)
if (-not $SkipOptional) {
    if (Test-Command "tesseract") {
        Write-Ok "Tesseract OCR $(tesseract --version 2>&1 | Select-Object -First 1)"
    } else {
        Write-Warn "Tesseract OCR not found — needed only for scanned/image PDFs"
        Write-Info "Install from https://github.com/UB-Mannheim/tesseract/wiki"
    }
}

# MSVC Build Tools check (Windows)
if (-not $SkipOptional) {
    $vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vsWhere) {
        $vsInstall = & $vsWhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
        if ($vsInstall) {
            Write-Ok "MSVC Build Tools found"
        } else {
            Write-Warn "MSVC Build Tools not found — needed for llama-cpp-python and Tauri builds"
            Write-Info "Install: https://visualstudio.microsoft.com/visual-cpp-build-tools/"
        }
    } else {
        Write-Warn "Cannot check MSVC Build Tools (vswhere not found)"
        Write-Info "Install: https://visualstudio.microsoft.com/visual-cpp-build-tools/"
    }
}

if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Err "Required tools missing: $($failed -join ', ')"
    Write-Host "  Install the above and re-run this script." -ForegroundColor Yellow
    exit 1
}

# ─────────────────────────────────────────────
#  2. Python backend setup
# ─────────────────────────────────────────────
Write-Step "Setting up Python backend"

$backendDir = Join-Path $root "src-python"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"

# Create venv
if ($Force -or -not (Test-Path $venvPython)) {
    if ($Force -and (Test-Path $venvDir)) {
        Write-Info "Removing existing venv..."
        Remove-Item $venvDir -Recurse -Force
    }
    Write-Info "Creating Python virtual environment..."
    & $pythonCmd -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to create venv"; exit 1 }
    Write-Ok "Virtual environment created at src-python/.venv"
} else {
    Write-Ok "Virtual environment already exists"
}

# Upgrade pip
Write-Info "Upgrading pip..."
& $venvPython -m pip install --upgrade pip --quiet
Write-Ok "pip upgraded"

# Install Python dependencies
Write-Info "Installing Python dependencies (this may take several minutes)..."
& $venvPip install -e "$backendDir[dev,office]" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to install Python dependencies"
    Write-Info "If llama-cpp-python fails, ensure MSVC Build Tools are installed"
    Write-Info "Or install without LLM support: pip install -e .[dev,office] --no-deps llama-cpp-python"
    exit 1
}
Write-Ok "Python dependencies installed"

# Download spaCy model
$spacyModelName = "en_core_web_$SpacyModel"
Write-Info "Downloading spaCy model: $spacyModelName..."
& $venvPython -m spacy download $spacyModelName --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m spacy download $spacyModelName
}
Write-Ok "spaCy model $spacyModelName installed"

# ─────────────────────────────────────────────
#  3. Frontend setup
# ─────────────────────────────────────────────
Write-Step "Setting up frontend"

$frontendDir = Join-Path $root "frontend"
$nodeModules = Join-Path $frontendDir "node_modules"

if ($Force -and (Test-Path $nodeModules)) {
    Write-Info "Removing existing node_modules..."
    Remove-Item $nodeModules -Recurse -Force
}

Write-Info "Installing npm dependencies..."
Push-Location $frontendDir
npm install --silent 2>$null
if ($LASTEXITCODE -ne 0) { npm install }
Pop-Location

if ($LASTEXITCODE -ne 0) {
    Write-Err "npm install failed"
    exit 1
}
Write-Ok "Frontend dependencies installed"

# ─────────────────────────────────────────────
#  4. Verify installation
# ─────────────────────────────────────────────
Write-Step "Verifying installation"

# Check Python imports
$checkScript = @"
import sys
errors = []
try:
    import fastapi; print(f'  ✓ FastAPI {fastapi.__version__}')
except: errors.append('fastapi')
try:
    import uvicorn; print(f'  ✓ Uvicorn {uvicorn.__version__}')
except: errors.append('uvicorn')
try:
    import spacy; print(f'  ✓ spaCy {spacy.__version__}')
    nlp = spacy.load('en_core_web_$SpacyModel')
    print(f'  ✓ spaCy model en_core_web_$SpacyModel loaded')
except Exception as e: errors.append(f'spacy ({e})')
try:
    import torch; print(f'  ✓ PyTorch {torch.__version__}')
except: errors.append('torch')
try:
    import transformers; print(f'  ✓ Transformers {transformers.__version__}')
except: errors.append('transformers')
try:
    import gliner; print(f'  ✓ GLiNER {gliner.__version__}')
except: errors.append('gliner')
try:
    import fitz; print(f'  ✓ PyMuPDF {fitz.version[0]}')
except: errors.append('PyMuPDF')
try:
    import PIL; print(f'  ✓ Pillow {PIL.__version__}')
except: errors.append('Pillow')
try:
    import cryptography; print(f'  ✓ cryptography {cryptography.__version__}')
except: errors.append('cryptography')
try:
    from llama_cpp import Llama; print('  ✓ llama-cpp-python')
except Exception as e:
    print(f'  ⚠ llama-cpp-python not available ({e})')
    print('    (Optional — needed for LLM detection layer)')
if errors:
    print(f'\n  ✗ Failed imports: {", ".join(errors)}')
    sys.exit(1)
"@
& $venvPython -c $checkScript
if ($LASTEXITCODE -ne 0) {
    Write-Err "Some Python packages failed to import"
    exit 1
}

# Check frontend build
Write-Info "Checking frontend TypeScript..."
Push-Location $frontendDir
npx tsc --noEmit 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Ok "TypeScript compilation OK"
} else {
    Write-Warn "TypeScript has errors (non-blocking for dev)"
}
Pop-Location

# ─────────────────────────────────────────────
#  5. Summary
# ─────────────────────────────────────────────
Write-Step "Setup complete!"

Write-Host ""
Write-Host "  To start developing:" -ForegroundColor White
Write-Host "    .\dev.ps1            # Start backend + frontend" -ForegroundColor Gray
Write-Host "    .\start.ps1          # Kill existing & restart both" -ForegroundColor Gray
Write-Host ""
Write-Host "  Backend:  http://127.0.0.1:8910" -ForegroundColor Gray
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Gray
Write-Host ""
Write-Host "  Optional setup:" -ForegroundColor White
Write-Host "    • Tesseract OCR — for scanned PDFs" -ForegroundColor Gray
Write-Host "      https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor DarkGray
Write-Host "    • GGUF model — for LLM detection layer" -ForegroundColor Gray
Write-Host "      Download any GGUF model and set path in Settings" -ForegroundColor DarkGray
Write-Host "    • Rust + MSVC — for Tauri desktop builds" -ForegroundColor Gray
Write-Host "      https://rustup.rs" -ForegroundColor DarkGray
Write-Host ""
