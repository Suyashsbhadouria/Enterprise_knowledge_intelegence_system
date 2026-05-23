import pytest

from ekcip_connectors.runtime.slack import SlackConnector
from ekcip_connectors.slack_channels import parse_channel_ids


def test_parse_channel_ids():
    assert parse_channel_ids("C01234567, C08999999") == ["C01234567", "C08999999"]


def test_message_document_skips_empty():
    connector = SlackConnector("xoxb-test")
    assert connector.message_document("C01234567", "general", {"text": ""}) is None


def test_message_document_shapes_payload():
    connector = SlackConnector("xoxb-test")
    doc = connector.message_document(
        "C01234567",
        "general",
        {"ts": "1714500000.001234", "user": "U123", "text": "Deploy blocked on auth"},
    )
    assert doc is not None
    assert doc["source"] == "slack"
    assert doc["source_id"] == "C01234567:1714500000001234"
    assert "Deploy blocked" in doc["content"]


@pytest.mark.asyncio
async def test_knowledge_status_includes_slack(client):
    response = await client.get("/v1/knowledge/status")
    assert response.status_code == 200
    body = response.json()
    assert "slack_chunks" in body["data"]
    assert "slack_configured" in body["data"]
