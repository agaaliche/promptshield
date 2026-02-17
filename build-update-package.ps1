<#
.SYNOPSIS
    Create update packages for online and offline distribution.

.DESCRIPTION
    After running `cd frontend; npm run tauri build`, this script:

    1. Locates the NSIS installer produced by Tauri in the bundle output.
    2. Computes the SHA-256 hash for integrity verification.
    3. Generates a server-side `manifest.json` for the online update API.
    4. Packages an offline `.promptshield-update` file (a zip containing
       the manifest + installer) that users can sideload.

    The outputs go into `dist/updates/`:
      - promptShield_<version>_x64-setup.nsis.exe    (the installer, for CDN upload)
      - manifest.json                                 (for the update API to serve)
      - promptShield_<version>_x64.promptshield-update  (offline package)

.PARAMETER Version
    Override the version string. By default reads from tauri.conf.json.

.PARAMETER InstallerPath
    Path to the NSIS installer. By default searches the Tauri bundle output.

.PARAMETER DownloadBaseUrl
    Base URL where the installer will be hosted for online downloads.
    Default: https://updates.promptshield.com/releases

.PARAMETER Notes
    Release notes / changelog text (Markdown). Can be a string or a path
    to a .md file. Default: empty string.

.PARAMETER Mandatory
    Mark this update as mandatory (users cannot skip).

.EXAMPLE
    # Basic usage after `npm run tauri build`:
    .\build-update-package.ps1

.EXAMPLE
    # With release notes from a file:
    .\build-update-package.ps1 -Notes .\CHANGELOG.md

.EXAMPLE
    # Explicit version and custom download URL:
    .\build-update-package.ps1 -Version "0.3.0" -DownloadBaseUrl "https://cdn.example.com/releases"
#>

param(
    [string]$Version,
    [string]$InstallerPath,
    [string]$DownloadBaseUrl = "https://updates.promptshield.com/releases",
    [string]$Notes = "",
    [switch]$Mandatory
)

$ErrorActionPreference = "Stop"

# ── Resolve version from tauri.conf.json ────────────────────────

$tauriConf = Join-Path $PSScriptRoot "frontend\src-tauri\tauri.conf.json"
if (-not $Version) {
    if (Test-Path $tauriConf) {
        $conf = Get-Content $tauriConf -Raw | ConvertFrom-Json
        $Version = $conf.version
        Write-Host "[*] Version from tauri.conf.json: $Version" -ForegroundColor Cyan
    } else {
        throw "Cannot determine version. Provide -Version or ensure tauri.conf.json exists."
    }
}

# ── Locate installer ───────────────────────────────────────────

if (-not $InstallerPath) {
    # Tauri v2 bundle output paths
    $bundleDir = Join-Path $PSScriptRoot "frontend\src-tauri\target\release\bundle"
    $nsisDir   = Join-Path $bundleDir "nsis"

    # Look for NSIS installer first (preferred), then MSI
    $candidates = @()
    if (Test-Path $nsisDir) {
        $candidates += Get-ChildItem $nsisDir -Filter "*.exe" | Sort-Object LastWriteTime -Descending
    }
    $msiDir = Join-Path $bundleDir "msi"
    if (Test-Path $msiDir) {
        $candidates += Get-ChildItem $msiDir -Filter "*.msi" | Sort-Object LastWriteTime -Descending
    }

    if ($candidates.Count -eq 0) {
        throw @"
No installer found in $bundleDir.
Run 'cd frontend; npm run tauri build' first.
"@
    }

    $InstallerPath = $candidates[0].FullName
    Write-Host "[*] Found installer: $InstallerPath" -ForegroundColor Cyan
}

if (-not (Test-Path $InstallerPath)) {
    throw "Installer not found at: $InstallerPath"
}

$installerItem = Get-Item $InstallerPath
$installerName = $installerItem.Name
$installerSize = $installerItem.Length

# ── Read release notes ──────────────────────────────────────────

if ($Notes -and (Test-Path $Notes)) {
    $Notes = Get-Content $Notes -Raw -Encoding utf8
    Write-Host "[*] Loaded release notes from file ($($Notes.Length) chars)" -ForegroundColor Cyan
}

# ── Compute SHA-256 ─────────────────────────────────────────────

Write-Host "[*] Computing SHA-256..." -ForegroundColor Cyan
$sha256 = (Get-FileHash -Path $InstallerPath -Algorithm SHA256).Hash.ToLower()
Write-Host "    Hash: $sha256" -ForegroundColor DarkGray

# ── Create output directory ─────────────────────────────────────

$outputDir = Join-Path $PSScriptRoot "dist\updates"
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

# ── Copy installer to output ────────────────────────────────────

$installerDest = Join-Path $outputDir $installerName
Copy-Item $InstallerPath $installerDest -Force
Write-Host "[+] Installer copied to: $installerDest" -ForegroundColor Green

# ── Generate server manifest (for online update API) ────────────

$pubDate = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$downloadUrl = "$DownloadBaseUrl/$installerName"

$serverManifest = [ordered]@{
    version   = $Version
    notes     = $Notes
    pub_date  = $pubDate
    url       = $downloadUrl
    sha256    = $sha256
    size      = $installerSize
    mandatory = [bool]$Mandatory
}

$serverManifestJson = $serverManifest | ConvertTo-Json -Depth 10
$serverManifestPath = Join-Path $outputDir "manifest.json"
[System.IO.File]::WriteAllText($serverManifestPath, $serverManifestJson, [System.Text.Encoding]::UTF8)
Write-Host "[+] Server manifest: $serverManifestPath" -ForegroundColor Green

# ── Generate offline update package (.promptshield-update) ──────

$offlineManifest = [ordered]@{
    version  = $Version
    sha256   = $sha256
    notes    = $Notes
    pub_date = $pubDate
    platform = "windows"
}

$offlineManifestJson = $offlineManifest | ConvertTo-Json -Depth 10

$offlinePkgName = "promptShield_${Version}_x64.promptshield-update"
$offlinePkgPath = Join-Path $outputDir $offlinePkgName

# Remove old package if it exists
if (Test-Path $offlinePkgPath) {
    Remove-Item $offlinePkgPath -Force
}

# Create zip archive with manifest.json + installer
Write-Host "[*] Packaging offline update..." -ForegroundColor Cyan

# Write manifest to a temp file
$tempManifest = Join-Path $env:TEMP "promptshield-update-manifest.json"
[System.IO.File]::WriteAllText($tempManifest, $offlineManifestJson, [System.Text.Encoding]::UTF8)

# Use .NET to create the zip
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$zipStream = [System.IO.File]::Create($offlinePkgPath)
$archive   = [System.IO.Compression.ZipArchive]::new($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)

# Add manifest.json
$manifestEntry = $archive.CreateEntry("manifest.json", [System.IO.Compression.CompressionLevel]::Optimal)
$manifestStream = $manifestEntry.Open()
$manifestBytes = [System.IO.File]::ReadAllBytes($tempManifest)
$manifestStream.Write($manifestBytes, 0, $manifestBytes.Length)
$manifestStream.Close()

# Add installer
$installerEntry = $archive.CreateEntry($installerName, [System.IO.Compression.CompressionLevel]::Optimal)
$installerStream = $installerEntry.Open()
$installerBytes = [System.IO.File]::ReadAllBytes($InstallerPath)
$installerStream.Write($installerBytes, 0, $installerBytes.Length)
$installerStream.Close()

$archive.Dispose()
$zipStream.Close()

# Cleanup temp
Remove-Item $tempManifest -ErrorAction SilentlyContinue

$offlineSize = [math]::Round((Get-Item $offlinePkgPath).Length / 1MB, 1)
Write-Host "[+] Offline package: $offlinePkgPath ($offlineSize MB)" -ForegroundColor Green

# ── Summary ──────────────────────────────────────────────────────

Write-Host ""
Write-Host "=== Update Package Build Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "  Version:         $Version"
Write-Host "  SHA-256:         $sha256"
Write-Host "  Installer size:  $([math]::Round($installerSize / 1MB, 1)) MB"
Write-Host "  Mandatory:       $Mandatory"
Write-Host ""
Write-Host "  Outputs in $outputDir/:" -ForegroundColor Yellow
Write-Host "    1. $installerName          → Upload to CDN ($DownloadBaseUrl/)"
Write-Host "    2. manifest.json           → Serve from update API endpoint"
Write-Host "    3. $offlinePkgName         → Distribute for offline installs"
Write-Host ""
Write-Host "  Online deployment:" -ForegroundColor Cyan
Write-Host "    1. Upload $installerName to your CDN/storage bucket"
Write-Host "    2. Copy manifest.json content to your update server config"
Write-Host "    3. The endpoint GET /updates/check should return the manifest"
Write-Host "       when the client version is older than $Version"
Write-Host ""
Write-Host "  Offline distribution:" -ForegroundColor Cyan
Write-Host "    Share $offlinePkgName via email, USB, etc."
Write-Host "    Users load it from Settings → Updates → Offline section."
Write-Host ""
