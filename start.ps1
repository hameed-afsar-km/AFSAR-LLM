# AFSAR — Development Launcher
# Usage: .\start.ps1 [-BackendOnly] [-FrontendOnly] [-NoBrowser]
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$NoTauri
)

$Root    = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Venv    = Join-Path $Backend ".venv\Scripts\python.exe"

function Write-Banner {
    Write-Host ""
    Write-Host "  █████╗ ███████╗███████╗ █████╗ ██████╗ " -ForegroundColor Cyan
    Write-Host " ██╔══██╗██╔════╝██╔════╝██╔══██╗██╔══██╗" -ForegroundColor Cyan
    Write-Host " ███████║█████╗  ███████╗███████║██████╔╝" -ForegroundColor Cyan
    Write-Host " ██╔══██║██╔══╝  ╚════██║██╔══██║██╔══██╗" -ForegroundColor Cyan
    Write-Host " ██║  ██║██║     ███████║██║  ██║██║  ██║" -ForegroundColor Cyan
    Write-Host " ╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝" -ForegroundColor Cyan
    Write-Host "  Personal AI Assistant — Dev Launcher" -ForegroundColor DarkCyan
    Write-Host ""
}

Write-Banner

# --- Validate environment ---
if (-not (Test-Path $Venv)) {
    Write-Host "[ERROR] Python venv not found at: $Venv" -ForegroundColor Red
    Write-Host "        Run: cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

$jobs = @()

# --- Start Backend ---
if (-not $FrontendOnly) {
    Write-Host "[1/2] Starting FastAPI backend on http://127.0.0.1:8000 ..." -ForegroundColor Green
    $backendJob = Start-Job -ScriptBlock {
        param($venv, $backend)
        Set-Location $backend
        & $venv -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
    } -ArgumentList $Venv, $Backend
    $jobs += $backendJob
    Write-Host "      Backend PID (job): $($backendJob.Id)" -ForegroundColor DarkGray

    # Wait briefly then probe health
    Start-Sleep -Seconds 3
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
        Write-Host "      Health: $($health.status) | env: $($health.env)" -ForegroundColor DarkGreen
    } catch {
        Write-Host "      Backend not ready yet — it may still be starting." -ForegroundColor Yellow
    }
}

# --- Start Frontend ---
if (-not $BackendOnly) {
    if ($NoTauri) {
        Write-Host "[2/2] Starting Next.js dev server on http://localhost:3000 ..." -ForegroundColor Green
        $frontendJob = Start-Job -ScriptBlock {
            param($frontend)
            Set-Location $frontend
            npm run dev
        } -ArgumentList $Frontend
        $jobs += $frontendJob
        Write-Host "      Open http://localhost:3000 in your browser."
    } else {
        Write-Host "[2/2] Starting Tauri desktop app ..." -ForegroundColor Green
        $frontendJob = Start-Job -ScriptBlock {
            param($frontend)
            Set-Location $frontend
            npm run tauri dev 2>&1
        } -ArgumentList $Frontend
        $jobs += $frontendJob
    }
}

Write-Host ""
Write-Host "  All processes started. Press Ctrl+C to stop." -ForegroundColor Cyan
Write-Host "  Backend:  http://127.0.0.1:8000" -ForegroundColor DarkGray
Write-Host "  API Docs: http://127.0.0.1:8000/docs" -ForegroundColor DarkGray
if ($NoTauri -and -not $BackendOnly) {
    Write-Host "  Frontend: http://localhost:3000" -ForegroundColor DarkGray
}
Write-Host ""

try {
    while ($true) {
        foreach ($job in $jobs) {
            $output = Receive-Job -Job $job
            if ($output) { Write-Host $output }
        }
        Start-Sleep -Milliseconds 500
    }
} finally {
    Write-Host "`n[Stopping] Cleaning up processes..." -ForegroundColor Yellow
    foreach ($job in $jobs) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -ErrorAction SilentlyContinue
    }
    Write-Host "[Done]" -ForegroundColor Green
}
