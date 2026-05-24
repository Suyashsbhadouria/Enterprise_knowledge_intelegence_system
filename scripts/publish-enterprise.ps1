$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"

Write-Host "Publishing Nexus Dynamics to LIVE Jira, Confluence, Slack (then re-index Neo4j + Postgres)..."
Write-Host "Ensure .env has ENTERPRISE_PUBLISH_JIRA_PROJECT_MAP and SLACK_CHANNEL_IDS set."
Write-Host ""

$dryRun = $args -contains "-DryRun"
$body = @{
    dry_run = [bool]$dryRun
    clear_knowledge_before_reindex = $true
} | ConvertTo-Json

$response = Invoke-RestMethod -Method Post -Uri "$base/v1/admin/publish-enterprise" -ContentType "application/json" -Body $body
$response | ConvertTo-Json -Depth 12

if ($response.data.publish.issue_key_map) {
    Write-Host "`n=== Fixture -> Live Jira keys (sample) ===" -ForegroundColor Cyan
    $response.data.publish.issue_key_map.PSObject.Properties | Select-Object -First 8 | ForEach-Object {
        Write-Host "  $($_.Name) -> $($_.Value)"
    }
}
