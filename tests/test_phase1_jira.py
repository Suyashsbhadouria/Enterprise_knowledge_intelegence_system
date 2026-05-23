import pytest

from ekcip_connectors.runtime.jira import JiraConnector, _adf_to_text


def test_adf_to_text_extracts_plain_text():
    adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Feature Y is blocked."}],
            }
        ],
    }
    assert "Feature Y is blocked" in _adf_to_text(adf)


@pytest.mark.asyncio
async def test_search_issues_uses_search_jql_endpoint(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    captured: list[str] = []

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "issues": [{"key": "PROJ-1", "fields": {"summary": "Test"}}],
        "nextPageToken": None,
    }

    async def mock_post(url: str, **kwargs: object) -> MagicMock:
        captured.append(url)
        return mock_response

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    monkeypatch.setattr(
        "ekcip_connectors.runtime.jira.httpx.AsyncClient",
        lambda **kwargs: mock_client,
    )

    connector = JiraConnector("https://example.atlassian.net", "user@example.com", "token")
    issues = await connector.search_issues("ORDER BY updated DESC", max_results=5)

    assert len(issues) == 1
    assert issues[0]["key"] == "PROJ-1"
    assert captured[0].endswith("/rest/api/3/search/jql")


def test_issue_document_shapes_index_payload():
    connector = JiraConnector("https://example.atlassian.net", "user@example.com", "token")
    issue = {
        "key": "PROJ-42",
        "fields": {
            "summary": "Implement auth",
            "description": "Add OAuth flow",
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "Alex"},
            "project": {"key": "PROJ"},
            "comment": {
                "comments": [
                    {"author": {"displayName": "Sam"}, "body": "Need review"},
                ]
            },
        },
    }
    doc = connector.issue_document(issue)
    assert doc["source_id"] == "PROJ-42"
    assert "Implement auth" in doc["content"]
    assert "Alex" in doc["content"]
    assert doc["url"].endswith("/browse/PROJ-42")


@pytest.mark.asyncio
async def test_knowledge_status_endpoint(client):
    response = await client.get("/v1/knowledge/status")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "jira_chunks" in body["data"]
    assert "confluence_chunks" in body["data"]
