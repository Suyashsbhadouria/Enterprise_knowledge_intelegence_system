$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"

Write-Host "Seeding Nexus Dynamics enterprise fixture (Jira, Confluence, Slack, meetings — no GitHub)..."
$body = @{ clear_existing = $true } | ConvertTo-Json
$response = Invoke-RestMethod -Method Post -Uri "$base/v1/admin/seed-enterprise" -ContentType "application/json" -Body $body
$response | ConvertTo-Json -Depth 12

if ($response.data.test_queries) {
    Write-Host "`n=== Knowledge Q&A ===" -ForegroundColor Cyan
    $response.data.test_queries.knowledge_qa | ForEach-Object { Write-Host "  - $_" }
    Write-Host "`n=== Graph RAG ===" -ForegroundColor Cyan
    $response.data.test_queries.graph_rag | ForEach-Object { Write-Host "  - $_" }
    Write-Host "`n=== Action proposals (set SLACK_CHANNEL_IDS from action_channel_ids) ===" -ForegroundColor Cyan
    $response.data.test_queries.action_proposals | ForEach-Object { Write-Host "  - $_" }
    Write-Host "`nFixture Slack channel IDs:" -ForegroundColor Yellow
    $response.data.action_channel_ids | ForEach-Object { Write-Host "  $_" }
}

Write-Host "`nKnowledge status:"
Invoke-RestMethod "$base/v1/knowledge/status" | ConvertTo-Json -Depth 5
