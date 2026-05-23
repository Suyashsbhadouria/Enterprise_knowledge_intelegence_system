import pytest

from ekcip_connectors.runtime.github import GitHubConnector


def test_item_document_issue():
    connector = GitHubConnector("ghp_test")
    doc = connector.item_document(
        "acme/app",
        {
            "number": 42,
            "title": "Fix login",
            "state": "open",
            "body": "OAuth regression",
            "user": {"login": "alex"},
            "labels": [{"name": "bug"}],
            "html_url": "https://github.com/acme/app/issues/42",
            "updated_at": "2025-05-01T00:00:00Z",
        },
    )
    assert doc["source"] == "github"
    assert doc["source_id"] == "acme/app#42"
    assert "OAuth regression" in doc["content"]
    assert doc["metadata"]["kind"] == "issue"


def test_item_document_pull_request():
    connector = GitHubConnector("ghp_test")
    doc = connector.item_document(
        "acme/app",
        {
            "number": 7,
            "title": "Add metrics",
            "state": "closed",
            "body": "Dashboard widgets",
            "user": {"login": "sam"},
            "labels": [],
            "html_url": "https://github.com/acme/app/pull/7",
            "pull_request": {"url": "https://api.github.com/repos/acme/app/pulls/7"},
            "updated_at": "2025-05-02T00:00:00Z",
        },
    )
    assert doc["source_id"] == "acme/app!7"
    assert doc["metadata"]["kind"] == "pull_request"


@pytest.mark.asyncio
async def test_knowledge_status_includes_github(client):
    response = await client.get("/v1/knowledge/status")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "github_chunks" in body["data"]
    assert "github_configured" in body["data"]
