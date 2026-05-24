import pytest


@pytest.mark.asyncio
async def test_liveness(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "alive"


@pytest.mark.asyncio
async def test_mcp_connectors_registry(client):
    response = await client.get("/v1/connectors/mcp")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    connectors = body["data"]["connectors"]
    sources = {item["source"] for item in connectors}
    assert "jira" in sources
    assert "github" in sources
    assert "slack" in sources
    jira = next(c for c in connectors if c["source"] == "jira")
    assert jira["mcp_server_id"] == "plugin-atlassian-atlassian"


@pytest.mark.asyncio
async def test_llm_status(client):
    response = await client.get("/v1/llm/status")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["provider_order"] == ["groq", "nvidia", "huggingface", "gemini"]


@pytest.mark.asyncio
async def test_conversation_flow(client):
    create_resp = await client.post("/v1/conversations", json={"title": "Phase 0 test"})
    assert create_resp.status_code == 201
    create_body = create_resp.json()
    assert create_body["success"] is True
    conversation_id = create_body["data"]["id"]

    msg_resp = await client.post(
        f"/v1/conversations/{conversation_id}/messages",
        json={"content": "Who owns feature Y in project X?"},
    )
    assert msg_resp.status_code == 200
    msg_body = msg_resp.json()
    assert msg_body["success"] is True
    assert msg_body["data"]["phase"] in {
        "0-no-llm",
        "1-llm",
        "1-llm-error",
        "1-qa",
        "1-qa-no-llm",
        "2-qa",
        "2-qa-no-llm",
        "3-qa",
        "3-qa-no-llm",
        "4-qa-proposed",
        "4-action-proposed",
    }
    assert "citations" in msg_body["data"]
    assert "proposed_actions" in msg_body["data"]

    get_resp = await client.get(f"/v1/conversations/{conversation_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()["data"]
    assert len(detail["messages"]) == 2
    roles = {m["role"] for m in detail["messages"]}
    assert roles == {"user", "assistant"}
