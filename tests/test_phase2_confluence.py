import pytest

from ekcip_connectors.runtime.confluence import (
    ConfluenceConnector,
    html_to_text,
    normalize_confluence_base_url,
)


def test_normalize_confluence_base_url_appends_wiki():
    assert (
        normalize_confluence_base_url("https://example.atlassian.net")
        == "https://example.atlassian.net/wiki"
    )


def test_html_to_text_strips_tags():
    html = "<p>Feature <strong>Y</strong> spec</p>"
    assert "Feature Y spec" in html_to_text(html)


def test_page_document_shapes_index_payload():
    connector = ConfluenceConnector(
        "https://example.atlassian.net/wiki",
        "user@example.com",
        "token",
    )
    page = {
        "id": "12345",
        "title": "Architecture RFC",
        "space": {"key": "ENG", "name": "Engineering"},
        "history": {
            "lastUpdated": {
                "when": "2025-05-01T10:00:00.000Z",
                "by": {"displayName": "Alex"},
            }
        },
        "body": {"view": {"value": "<p>OAuth design details.</p>"}},
        "_links": {"webui": "/spaces/ENG/pages/12345/Architecture+RFC"},
    }
    doc = connector.page_document(page)
    assert doc["source"] == "confluence"
    assert doc["source_id"] == "12345"
    assert "OAuth design" in doc["content"]
    assert "ENG" in doc["content"]
    assert "12345" in doc["url"]


@pytest.mark.asyncio
async def test_search_pages_uses_content_search(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    captured_params: list[dict] = []

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "id": "99",
                "title": "Runbook",
                "space": {"key": "OPS", "name": "Ops"},
                "body": {"view": {"value": "<p>Restart steps</p>"}},
                "_links": {"webui": "/spaces/OPS/pages/99/Runbook"},
            }
        ],
        "size": 1,
    }

    async def mock_get(url: str, **kwargs: object) -> MagicMock:
        captured_params.append(kwargs.get("params", {}))
        return mock_response

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    monkeypatch.setattr(
        "ekcip_connectors.runtime.confluence.httpx.AsyncClient",
        lambda **kwargs: mock_client,
    )

    connector = ConfluenceConnector(
        "https://example.atlassian.net/wiki",
        "user@example.com",
        "token",
    )
    pages = await connector.search_pages(
        'type=page AND lastModified >= now("-90d") order by lastModified desc',
        max_results=10,
    )

    assert len(pages) == 1
    assert pages[0]["id"] == "99"
    assert captured_params[0]["cql"].startswith("type=page")


@pytest.mark.asyncio
async def test_knowledge_status_includes_confluence(client):
    response = await client.get("/v1/knowledge/status")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "confluence_entities" in body["data"]
    assert "confluence_configured" in body["data"]
