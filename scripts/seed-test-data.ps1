$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"

Write-Host "Seeding enterprise data from live Jira + Confluence (no demo issues)..."
$body = @{ max_results = 50 } | ConvertTo-Json
$response = Invoke-RestMethod -Method Post -Uri "$base/v1/admin/seed" -ContentType "application/json" -Body $body
$response | ConvertTo-Json -Depth 10

if ($response.data.sample_queries) {
    Write-Host "`nSuggested test queries:"
    $response.data.sample_queries | ForEach-Object { Write-Host "  - $_" }
}

Write-Host "`nKnowledge status:"
Invoke-RestMethod "$base/v1/knowledge/status" | ConvertTo-Json -Depth 5
