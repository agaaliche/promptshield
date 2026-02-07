<#
.SYNOPSIS
    Kill processes on ports 8910 (backend) and 5173 (frontend), then restart both servers.
.DESCRIPTION
    1. Frees ports 8910 and 5173 by terminating any owning processes.
    2. Starts the FastAPI backend (uvicorn) on port 8910.
    3. Starts the Vite dev server on port 5173.
    4. Waits for both to become healthy before handing control back.
#>

param(
    [switch]$Back,
    [switch]$Front
)

$ErrorActionPreference = 'SilentlyContinue'
$ProjectRoot  = $PSScriptRoot
$BackendDir   = Join-Path $ProjectRoot 'src-python'
$FrontendDir  = Join-Path $ProjectRoot 'frontend'
$PythonExe    = Join-Path $BackendDir '.venv\Scripts\python.exe'
$BackendPort  = 8910
$FrontendPort = 5173

function Free-Port([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $pid = $c.OwningProcess
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "  Killing PID $pid ($($proc.ProcessName)) on port $Port" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force
        }
    }
    # Brief wait so the OS releases the port
    Start-Sleep -Milliseconds 500
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($still) {
        Write-Host "  WARNING: port $Port still in use after kill attempt" -ForegroundColor Red
    } else {
        Write-Host "  Port $Port is free" -ForegroundColor Green
    }
}

function Wait-ForUrl([string]$Url, [int]$TimeoutSec = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-RestMethod -Uri $Url -Method GET -TimeoutSec 2
            return $true
        } catch {}
        Start-Sleep -Seconds 1
    }
    return $false
}

# ── Free ports ──────────────────────────────────────────────────────────────
Write-Host "`n=== Freeing ports ===" -ForegroundColor Cyan

if (-not $Front) {
    Write-Host "Backend  (port $BackendPort):"
    Free-Port $BackendPort
}
if (-not $Back) {
    Write-Host "Frontend (port $FrontendPort):"
    Free-Port $FrontendPort
}

# ── Start backend ──────────────────────────────────────────────────────────
if (-not $Front) {
    Write-Host "`n=== Starting backend (uvicorn :$BackendPort) ===" -ForegroundColor Cyan
    $backendArgs = "-m uvicorn api.server:app --host 127.0.0.1 --port $BackendPort"
    Start-Process -FilePath $PythonExe `
        -ArgumentList $backendArgs `
        -WorkingDirectory $BackendDir `
        -WindowStyle Normal

    Write-Host "Waiting for backend health check..." -NoNewline
    if (Wait-ForUrl "http://127.0.0.1:$BackendPort/health" 30) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " TIMEOUT -- backend may not have started" -ForegroundColor Red
    }
}

# ── Start frontend ─────────────────────────────────────────────────────────
if (-not $Back) {
    Write-Host "`n=== Starting frontend (vite :$FrontendPort) ===" -ForegroundColor Cyan
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c npx vite --port $FrontendPort" `
        -WorkingDirectory $FrontendDir `
        -WindowStyle Normal

    Write-Host "Waiting for frontend..." -NoNewline
    if (Wait-ForUrl "http://localhost:$FrontendPort" 20) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " TIMEOUT -- frontend may not have started" -ForegroundColor Red
    }
}

# ── Summary ────────────────────────────────────────────────────────────────
Write-Host "`n=== Ready ===" -ForegroundColor Cyan
if (-not $Front) {
    Write-Host "  Backend:  http://127.0.0.1:$BackendPort/health"
}
if (-not $Back) {
    Write-Host "  Frontend: http://localhost:$FrontendPort"
}
Write-Host ""
