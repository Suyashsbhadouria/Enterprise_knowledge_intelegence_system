import pytest

from ekcip_connectors.fixtures.enterprise_catalog import (
    build_confluence_documents,
    build_jira_documents,
    build_slack_message_batches,
    build_test_queries,
)
from ekcip_knowledge.embeddings import EmbeddingRouter


def test_enterprise_catalog_volume():
    jira = build_jira_documents()
    conf = build_confluence_documents()
    slack = build_slack_message_batches()
    assert len(jira) >= 25
    assert len(conf) >= 10
    assert len(slack) >= 30
    assert any(doc["source_id"] == "ACME-205" for doc in jira)
    assert any(doc["metadata"]["project"] == "MERID" for doc in jira)


def test_test_queries_categories():
    queries = build_test_queries()
    assert "knowledge_qa" in queries
    assert "action_proposals" in queries
    assert len(queries["knowledge_qa"]) >= 5


@pytest.mark.asyncio
async def test_seed_enterprise_fixture_endpoint(client, monkeypatch):
    async def mock_embed(self, text: str):
        return [0.1, 0.2, 0.3], "test"

    monkeypatch.setattr(EmbeddingRouter, "embed", mock_embed)

    async def mock_neo4j(*args, **kwargs):
        return {"status": "skipped", "reason": "test"}

    monkeypatch.setattr(
        "ekcip_api.services.enterprise_fixture_seed.seed_neo4j_from_enterprise_data",
        mock_neo4j,
    )

    response = await client.post("/v1/admin/seed-enterprise", json={"clear_existing": True})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "enterprise_fixture"
    assert data["total_chunks"] > 50
    assert data["github"]["status"] == "skipped"
    assert "test_queries" in data
    assert len(data["action_channel_ids"]) == 4

    status = await client.get("/v1/knowledge/status")
    counts = status.json()["data"]
    assert counts["jira_entities"] >= 25
    assert counts["slack_entities"] >= 25
    assert counts["meetings_entities"] >= 1
