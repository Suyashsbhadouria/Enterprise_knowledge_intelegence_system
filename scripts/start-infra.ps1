$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Starting Postgres and Redis (local Docker)..."
Write-Host "Neo4j: using Neo4j Aura from .env (no local container)."
docker compose up -d postgres redis

function Wait-Healthy($name, $seconds = 120) {
    $deadline = (Get-Date).AddSeconds($seconds)
    do {
        $status = docker inspect -f "{{.State.Health.Status}}" $name 2>$null
        if ($status -eq "healthy") { return $true }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    return $false
}

$pg = "enterpriseknowledgeintellligenceplatform-pranayv2-postgres-1"
$redis = "enterpriseknowledgeintellligenceplatform-pranayv2-redis-1"

if (-not (Wait-Healthy $pg 60)) { Write-Warning "Postgres not healthy yet" }
if (-not (Wait-Healthy $redis 30)) { Write-Warning "Redis not healthy yet" }

docker compose ps postgres redis
Write-Host ""
Write-Host "Configure Aura in .env (from the downloaded credentials file):"
Write-Host "  NEO4J_URI=neo4j+ssc://<instance-id>.databases.neo4j.io"
Write-Host "  NEO4J_USER=<instance-id>"
Write-Host "  NEO4J_DATABASE=<instance-id>"
Write-Host "  NEO4J_PASSWORD=<from https://console.neo4j.io>"
Write-Host "Verify: GET http://127.0.0.1:8000/v1/graph/status"
