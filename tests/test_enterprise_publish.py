import pytest

from ekcip_connectors.fixtures.enterprise_publish import (
    apply_issue_key_map,
    index_existing_nexus_issues,
    parse_csv_map,
)
from ekcip_knowledge.embeddings import EmbeddingRouter


def test_parse_csv_map():
    assert parse_csv_map("CORE:SCRUM, ACME:PROJ") == {"CORE": "SCRUM", "ACME": "PROJ"}


def test_apply_issue_key_map():
    text = "Blocked on CORE-101; see ACME-205"
    mapped = apply_issue_key_map(text, {"CORE-101": "SCRUM-10", "ACME-205": "SCRUM-11"})
    assert "SCRUM-10" in mapped
    assert "SCRUM-11" in mapped


def test_index_existing_nexus_issues():
    issues = [
        {
            "key": "SCRUM-99",
            "fields": {"summary": "[Nexus CORE-101] OIDC SSO"},
        }
    ]
    assert index_existing_nexus_issues(issues) == {"CORE-101": "SCRUM-99"}


@pytest.mark.asyncio
async def test_publish_enterprise_dry_run(client, monkeypatch):
    monkeypatch.setenv(
        "ENTERPRISE_PUBLISH_JIRA_PROJECT_MAP",
        "CORE:SCRUM,ACME:SCRUM,MERID:SCRUM,OPS:SCRUM",
    )
    monkeypatch.setenv("SLACK_CHANNEL_IDS", "C111,C222,C333,C444")
    from ekcip_shared.config import get_settings

    get_settings.cache_clear()

    async def mock_publish(**kwargs):
        return {
            "dry_run": kwargs.get("dry_run"),
            "issue_key_map": {"CORE-101": "DRY-CORE-101"},
            "confluence_page_map": {"10001": "DRY-10001"},
            "slack_channel_map": {},
            "jira": {"created": [], "skipped_existing": [], "errors": []},
            "confluence": {"created": [], "skipped_existing": [], "errors": []},
            "slack": {"posted": [], "errors": []},
        }

    monkeypatch.setattr(
        "ekcip_api.services.enterprise_publish.publish_nexus_to_live",
        mock_publish,
    )

    response = await client.post(
        "/v1/admin/publish-enterprise",
        json={"dry_run": True},
    )
    assert response.status_code == 200
    assert response.json()["data"]["dry_run"] is True
