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


def test_commit_document_includes_push_time():
    connector = GitHubConnector("ghp_test")
    doc = connector.commit_document(
        "acme/app",
        {
            "sha": "abc123def456789",
            "html_url": "https://github.com/acme/app/commit/abc123def456789",
            "author": {"login": "alex"},
            "commit": {
                "message": "Fix OAuth redirect\n\nHandle edge case for SSO.",
                "author": {
                    "name": "Alex Kim",
                    "email": "alex@example.com",
                    "date": "2025-05-01T09:00:00Z",
                },
                "committer": {
                    "name": "Alex Kim",
                    "email": "alex@example.com",
                    "date": "2025-05-01T10:30:00Z",
                },
            },
        },
    )
    assert doc["source_id"] == "acme/app@abc123d"
    assert doc["metadata"]["kind"] == "commit"
    assert "Pushed to GitHub at: 2025-05-01T10:30:00Z" in doc["content"]
    assert "Fix OAuth redirect" in doc["content"]
    assert doc["metadata"]["author"] == "alex"


@pytest.mark.asyncio
async def test_list_recent_commits_paginates(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "sha": "deadbeef" * 5,
            "html_url": "https://github.com/acme/app/commit/deadbeef",
            "author": {"login": "alex"},
            "commit": {
                "message": "Initial commit",
                "author": {"date": "2025-05-01T00:00:00Z"},
                "committer": {"date": "2025-05-01T00:00:00Z"},
            },
        }
    ]

    async def mock_get(url: str, **kwargs: object) -> MagicMock:
        return mock_response

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    monkeypatch.setattr(
        "ekcip_connectors.runtime.github.httpx.AsyncClient",
        lambda **kwargs: mock_client,
    )

    connector = GitHubConnector("ghp_test")
    commits = await connector.list_recent_commits(
        "acme/app",
        since_iso="2025-01-01T00:00:00Z",
        max_results=10,
    )
    assert len(commits) == 1
    assert commits[0]["sha"].startswith("deadbeef")


@pytest.mark.asyncio
async def test_knowledge_status_includes_github(client):
    response = await client.get("/v1/knowledge/status")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "github_entities" in body["data"]
    assert "github_configured" in body["data"]
