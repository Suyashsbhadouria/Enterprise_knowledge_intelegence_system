"""Execute approved coordination actions against real connectors (Phase 4)."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ekcip_api.db.models import ProposedAction
from ekcip_api.schemas.actions import ProposedActionResponse
from ekcip_api.services.action_proposals import _to_response, mark_approved
from ekcip_connectors.runtime.jira import JiraConnector
from ekcip_connectors.runtime.slack import SlackConnector, build_slack_connector
from ekcip_connectors.slack_channels import parse_channel_ids
from ekcip_orchestration.actions.types import (
    ActionType,
    AddJiraCommentPayload,
    CreateReminderPayload,
    ScheduleSlackMessagePayload,
    SendSlackMessagePayload,
    UpdateIssueStatusPayload,
)
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


def _build_jira(settings: Settings) -> JiraConnector | None:
    if not settings.jira_configured:
        return None
    return JiraConnector(
        settings.jira_base_url or "",
        settings.jira_email or "",
        settings.jira_api_token or "",
    )


def _allowed_slack_channels(settings: Settings) -> set[str]:
    if not settings.slack_channel_ids.strip():
        return set()
    return set(parse_channel_ids(settings.slack_channel_ids))


def _ensure_slack_channel(channel_id: str, allowed: set[str]) -> None:
    if allowed and channel_id not in allowed:
        raise ValueError(
            f"Slack channel {channel_id} is not in SLACK_CHANNEL_IDS allowlist. "
            "Add the channel ID to .env before posting."
        )


async def _execute_payload(
    action_type: str,
    payload: dict,
    *,
    settings: Settings,
) -> dict:
    slack = build_slack_connector(settings)
    jira = _build_jira(settings)
    allowed_channels = _allowed_slack_channels(settings)

    if action_type == ActionType.SEND_SLACK_MESSAGE.value:
        if slack is None:
            raise RuntimeError("Slack is not configured (SLACK_BOT_TOKEN + SLACK_CHANNEL_IDS)")
        model = SendSlackMessagePayload.model_validate(payload)
        _ensure_slack_channel(model.channel_id, allowed_channels)
        return await slack.post_message(
            model.channel_id,
            model.text,
            thread_ts=model.thread_ts,
        )

    if action_type == ActionType.SCHEDULE_SLACK_MESSAGE.value:
        if slack is None:
            raise RuntimeError("Slack is not configured (SLACK_BOT_TOKEN + SLACK_CHANNEL_IDS)")
        model = ScheduleSlackMessagePayload.model_validate(payload)
        _ensure_slack_channel(model.channel_id, allowed_channels)
        return await slack.schedule_message(
            model.channel_id,
            model.text,
            post_at=model.post_at,
        )

    if action_type == ActionType.ADD_JIRA_COMMENT.value:
        if jira is None:
            raise RuntimeError("Jira is not configured")
        model = AddJiraCommentPayload.model_validate(payload)
        return await jira.add_comment(model.issue_key, model.body)

    if action_type == ActionType.UPDATE_ISSUE_STATUS.value:
        if jira is None:
            raise RuntimeError("Jira is not configured")
        model = UpdateIssueStatusPayload.model_validate(payload)
        return await jira.transition_issue(model.issue_key, model.status_name)

    if action_type == ActionType.CREATE_REMINDER.value:
        model = CreateReminderPayload.model_validate(payload)
        if model.channel_id and slack is not None:
            _ensure_slack_channel(model.channel_id, allowed_channels)
            scheduled = await slack.schedule_message(
                model.channel_id,
                model.message,
                post_at=model.remind_at,
            )
            return {"reminder": "slack_scheduled_message", **scheduled}
        return {
            "reminder": "stored",
            "message": model.message,
            "remind_at": model.remind_at,
            "note": "Set SLACK_BOT_TOKEN and channel to deliver via Slack.",
        }

    raise ValueError(f"Unsupported action type: {action_type}")


async def execute_approved_action(
    session: AsyncSession,
    action: ProposedAction,
    *,
    settings: Settings,
    approved_by: str,
) -> ProposedActionResponse:
    if action.status == "executed":
        return _to_response(action)
    if action.status == "rejected":
        raise ValueError(f"Action {action.id} was rejected")
    if action.status == "failed":
        raise ValueError(f"Action {action.id} previously failed: {action.error}")
    if action.status == "pending":
        if settings.actions_require_approval:
            raise ValueError("Action requires approval before execution")
        await mark_approved(session, action, approved_by=approved_by)
    elif action.status != "approved":
        raise ValueError(f"Action {action.id} cannot execute (status={action.status})")

    try:
        result = await _execute_payload(action.action_type, dict(action.payload), settings=settings)
        action.status = "executed"
        action.executed_at = datetime.now(timezone.utc)
        action.result = result
        action.error = None
        logger.info(
            "action_executed",
            action_id=str(action.id),
            action_type=action.action_type,
        )
    except Exception as exc:
        action.status = "failed"
        action.error = str(exc)[:2000]
        logger.warning(
            "action_failed",
            action_id=str(action.id),
            action_type=action.action_type,
            error=action.error,
        )
    await session.commit()
    await session.refresh(action)
    return _to_response(action)


async def approve_and_execute(
    session: AsyncSession,
    action: ProposedAction,
    *,
    settings: Settings,
    approved_by: str,
    execute: bool,
) -> ProposedActionResponse:
    if action.status != "pending":
        raise ValueError(f"Action {action.id} is not pending (status={action.status})")
    await mark_approved(session, action, approved_by=approved_by)
    await session.flush()
    if not execute:
        await session.commit()
        await session.refresh(action)
        return _to_response(action)
    return await execute_approved_action(
        session,
        action,
        settings=settings,
        approved_by=approved_by,
    )
