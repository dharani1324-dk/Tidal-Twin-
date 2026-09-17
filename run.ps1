# TidalTwin - local development launcher (Windows PowerShell)
# ===========================================================
# Starts the backend API and the frontend dev server together.
# For the containerised, one-command deployment use:
#     docker compose up --build
#
# Usage:
#     .\run.ps1
#
# Prerequisites: Python 3.12+, Node 20+, a reachable PostgreSQL+PostGIS,
# and a configured backend\.env (see backend\.env.example).

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Test-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

if (-not (Test-Cmd node)) { throw 'Node.js is required (https://nodejs.org).' }
if (-not (Test-Cmd npm))  { throw 'npm is required (ships with Node.js).' }

$venvPython = Join-Path $backend '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    $python = $venvPython
} elseif (Test-Cmd python) {
    $python = 'python'
} elseif (Test-Cmd py) {
    $python = 'py'
} else {
    throw 'Python 3.12+ is required (https://python.org).'
}

Write-Host '[tidaltwin] Starting backend on http://127.0.0.1:8000 ...' -ForegroundColor Cyan
$backendProc = Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $backend -PassThru

if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Write-Host '[tidaltwin] Installing frontend dependencies (first run) ...' -ForegroundColor Yellow
    Push-Location $frontend; npm install; Pop-Location
}

Write-Host '[tidaltwin] Starting frontend on http://127.0.0.1:5173 ...' -ForegroundColor Cyan
Write-Host '[tidaltwin] Press Ctrl+C to stop the frontend; the backend will be stopped too.' -ForegroundColor DarkGray

try {
    Push-Location $frontend
    npm run dev
} finally {
    Pop-Location
    if ($backendProc -and -not $backendProc.HasExited) {
        Write-Host '[tidaltwin] Stopping backend ...' -ForegroundColor DarkGray
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
}
