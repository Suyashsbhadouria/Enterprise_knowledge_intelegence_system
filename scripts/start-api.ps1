$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

# .env must win over stale shell variables (e.g. NEO4J_USER=neo4j from an old session)
Get-Content ".env" -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    $eq = $line.IndexOf("=")
    if ($eq -lt 1) { return }
    $name = $line.Substring(0, $eq).Trim()
    $value = $line.Substring($eq + 1).Trim()
    if ($name) { Set-Item -Path "env:$name" -Value $value }
}

$env:PYTHONPATH = @(
    "packages/shared/src",
    "packages/connectors/src",
    "packages/llm/src",
    "packages/knowledge/src",
    "packages/orchestration/src",
    "packages/graph/src",
    "apps/api/src"
) -join ";"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\Activate.ps1"
#pip install -q -e ".[dev]"

& "$PSScriptRoot\start-infra.ps1"
alembic upgrade head
uvicorn ekcip_api.main:app --reload --host 127.0.0.1 --port 8000
