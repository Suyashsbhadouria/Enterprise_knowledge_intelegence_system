from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from ekcip_orchestration.actions.detector import detect_action_drafts
from ekcip_orchestration.actions.types import ActionType


@pytest_asyncio.fixture
async def db_session(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


def test_detect_send_slack_message():
    drafts = detect_action_drafts(
        'Send a Slack message to channel C01234567 saying "Please confirm the API contract."',
        allowed_slack_channels=["C01234567"],
    )
    assert len(drafts) == 1
    assert drafts[0].action_type == ActionType.SEND_SLACK_MESSAGE
    assert drafts[0].payload["channel_id"] == "C01234567"
    assert "API contract" in drafts[0].payload["text"]


def test_detect_jira_comment():
    drafts = detect_action_drafts(
        "Add a comment on SCRUM-12 saying the auth spike is blocked.",
        allowed_slack_channels=[],
    )
    types = {draft.action_type for draft in drafts}
    assert ActionType.ADD_JIRA_COMMENT in types
    comment = next(d for d in drafts if d.action_type == ActionType.ADD_JIRA_COMMENT)
    assert comment.payload["issue_key"] == "SCRUM-12"


def test_detect_update_issue_status():
    drafts = detect_action_drafts(
        "Update status of ENG-5 to In Progress",
        allowed_slack_channels=[],
    )
    assert any(d.action_type == ActionType.UPDATE_ISSUE_STATUS for d in drafts)


@pytest.mark.asyncio
async def test_knowledge_status_reports_actions_phase(client):
    response = await client.get("/v1/knowledge/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["actions_phase"] == 4
    assert data["actions_enabled"] is True
    assert data["actions_require_approval"] is True


async def _seed_pending_action(
    client,
    db_session,
    action_type: ActionType,
    payload: dict,
    preview: str,
):
    from ekcip_api.db.models import Conversation, Message, ProposedAction

    create_resp = await client.post("/v1/conversations", json={"title": "Phase 4 actions"})
    conversation_id = UUID(create_resp.json()["data"]["id"])
    action_id = uuid4()

    conversation = await db_session.get(Conversation, conversation_id)
    message = Message(conversation_id=conversation.id, role="user", content="seed")
    db_session.add(message)
    await db_session.flush()
    db_session.add(
        ProposedAction(
            id=action_id,
            conversation_id=conversation.id,
            triggering_message_id=message.id,
            action_type=action_type.value,
            payload=payload,
            preview=preview,
            status="pending",
        )
    )
    await db_session.commit()
    return action_id


@pytest.mark.asyncio
async def test_action_approve_flow_without_execute(client, db_session, monkeypatch):
    from ekcip_api.services import action_executor

    async def mock_execute(*args, **kwargs):
        raise AssertionError("execute should not run when execute=false")

    monkeypatch.setattr(action_executor, "_execute_payload", mock_execute)

    action_id = await _seed_pending_action(
        client,
        db_session,
        ActionType.SEND_SLACK_MESSAGE,
        {"channel_id": "C01234567", "text": "hello"},
        "Post to Slack",
    )

    approve_resp = await client.post(
        f"/v1/actions/{action_id}/approve",
        json={"execute": False},
    )
    assert approve_resp.status_code == 200
    body = approve_resp.json()["data"]
    assert body["status"] == "approved"
    assert body["executed_at"] is None


@pytest.mark.asyncio
async def test_action_reject(client, db_session):
    action_id = await _seed_pending_action(
        client,
        db_session,
        ActionType.ADD_JIRA_COMMENT,
        {"issue_key": "SCRUM-1", "body": "test"},
        "Comment on SCRUM-1",
    )

    reject_resp = await client.post(
        f"/v1/actions/{action_id}/reject",
        json={"reason": "not now"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["data"]["status"] == "rejected"
