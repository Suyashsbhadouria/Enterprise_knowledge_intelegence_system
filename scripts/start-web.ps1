$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "apps\web")

if (-not (Test-Path "node_modules")) {
    npm install
}

Write-Host "Starting EKCIP web UI at http://localhost:3000" -ForegroundColor Cyan
Write-Host "API: http://127.0.0.1:8000 (run scripts\start-api.ps1 in another terminal)" -ForegroundColor Gray

npm run dev
