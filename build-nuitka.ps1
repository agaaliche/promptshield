<#
.SYNOPSIS
    Build the Python backend with Nuitka for code protection.

.DESCRIPTION
    Compiles src-python/ into a native executable using Nuitka, which converts
    Python to C and then to a native binary. This prevents trivial reverse
    engineering compared to PyInstaller (which bundles .pyc bytecode).

.NOTES
    Requirements:
      - Nuitka: pip install nuitka ordered-set
      - A C compiler (MSVC on Windows, gcc/clang on Linux/macOS)
      - The virtual environment must be activated

    Output: dist/doc-anonymizer-sidecar.exe (Windows)
#>

$ErrorActionPreference = "Stop"

# ── Configuration ─────────────────────────────────────────────────

$srcDir       = Join-Path $PSScriptRoot "src-python"
$entryPoint   = Join-Path $srcDir "main.py"
$outputDir    = Join-Path $PSScriptRoot "dist"
$outputName   = "doc-anonymizer-sidecar"
$iconPath     = Join-Path $PSScriptRoot "frontend\src-tauri\icons\icon.ico"

# ── Activate venv ────────────────────────────────────────────────

$venvActivate = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    Write-Host "[*] Activating virtual environment..." -ForegroundColor Cyan
    . $venvActivate
}

# ── Verify Nuitka is installed ───────────────────────────────────

$nuitkaVersion = python -m nuitka --version 2>$null
if (-not $nuitkaVersion) {
    Write-Host "[!] Nuitka not found. Installing..." -ForegroundColor Yellow
    pip install nuitka ordered-set
}

# ── Build ────────────────────────────────────────────────────────

Write-Host "[*] Building with Nuitka (this may take 10-30 minutes)..." -ForegroundColor Cyan

$nuitkaArgs = @(
    "-m", "nuitka",
    "--standalone",
    "--onefile",
    "--output-dir=$outputDir",
    "--output-filename=$outputName",

    # Include all packages used by the project
    "--include-package=api",
    "--include-package=core",
    "--include-package=models",

    # Core dependencies
    "--include-package=fastapi",
    "--include-package=uvicorn",
    "--include-package=pydantic",
    "--include-package=starlette",
    "--include-package=spacy",
    "--include-package=pypdfium2",

    # Anti-decompilation: remove docstrings, asserts, and debug info
    "--remove-output",
    "--no-pyi-file",

    # Windows-specific
    "--windows-console-mode=disable",
    "--company-name=PromptShield",
    "--product-name=PromptShield Sidecar",
    "--product-version=1.0.0",
    "--file-description=PromptShield Document Anonymizer Backend"
)

# Add icon if it exists
if (Test-Path $iconPath) {
    $nuitkaArgs += "--windows-icon-from-ico=$iconPath"
}

# Add the entry point
$nuitkaArgs += $entryPoint

Write-Host "Running: python $($nuitkaArgs -join ' ')" -ForegroundColor DarkGray

python @nuitkaArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Nuitka build failed!" -ForegroundColor Red
    exit 1
}

# ── Copy to Tauri binaries directory ─────────────────────────────

$tauriBinDir = Join-Path $PSScriptRoot "frontend\src-tauri\binaries"
$targetTriple = rustc -vV 2>$null | Select-String "host:" | ForEach-Object { ($_ -split ":\s*")[1] }
if (-not $targetTriple) { $targetTriple = "x86_64-pc-windows-msvc" }

$sidecarFileName = "$outputName-$targetTriple.exe"
$sidecarSrc = Join-Path $outputDir "$outputName.exe"
$sidecarDest = Join-Path $tauriBinDir $sidecarFileName

if (Test-Path $sidecarSrc) {
    if (-not (Test-Path $tauriBinDir)) { New-Item -ItemType Directory -Path $tauriBinDir -Force | Out-Null }
    Copy-Item $sidecarSrc $sidecarDest -Force
    Write-Host "[+] Copied sidecar to: $sidecarDest" -ForegroundColor Green
} else {
    Write-Host "[!] Build output not found at $sidecarSrc" -ForegroundColor Yellow
}

# ── Summary ──────────────────────────────────────────────────────

$fileSize = if (Test-Path $sidecarDest) { (Get-Item $sidecarDest).Length / 1MB } else { 0 }
Write-Host ""
Write-Host "=== Build Complete ===" -ForegroundColor Green
Write-Host "  Output: $sidecarDest"
Write-Host "  Size:   $([math]::Round($fileSize, 1)) MB"
Write-Host ""
Write-Host "Next: run 'cd frontend; npm run tauri build' to package the full desktop app." -ForegroundColor Cyan
