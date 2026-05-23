from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ekcip_api.db.models import ProposedAction
from ekcip_api.schemas.actions import ProposedActionResponse
from ekcip_connectors.slack_channels import parse_channel_ids
from ekcip_orchestration.actions.detector import detect_action_drafts
from ekcip_orchestration.actions.response import (
    format_action_proposal_reply,
    is_action_primary_request,
)
from ekcip_orchestration.actions.types import ProposedActionDraft
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


def _allowed_slack_channels(settings: Settings) -> list[str]:
    if not settings.slack_channel_ids.strip():
        return []
    return parse_channel_ids(settings.slack_channel_ids)


def _to_response(action: ProposedAction) -> ProposedActionResponse:
    return ProposedActionResponse.model_validate(action, from_attributes=True)


async def persist_action_drafts(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    triggering_message_id: UUID,
    drafts: list[ProposedActionDraft],
) -> list[ProposedActionResponse]:
    saved: list[ProposedActionResponse] = []
    for draft in drafts:
        row = ProposedAction(
            conversation_id=conversation_id,
            triggering_message_id=triggering_message_id,
            action_type=draft.action_type.value,
            payload=dict(draft.payload),
            preview=draft.preview,
            rationale=draft.rationale,
            status="pending",
        )
        session.add(row)
        await session.flush()
        saved.append(_to_response(row))
    return saved


def preview_action_drafts(
    settings: Settings,
    *,
    question: str,
    answer: str = "",
) -> list[ProposedActionDraft]:
    if not settings.actions_enabled:
        return []
    return detect_action_drafts(
        question,
        answer=answer,
        allowed_slack_channels=_allowed_slack_channels(settings),
        actions_enabled=settings.actions_enabled,
    )


async def propose_actions_for_message(
    session: AsyncSession,
    settings: Settings,
    *,
    conversation_id: UUID,
    triggering_message_id: UUID,
    question: str,
    answer: str,
    drafts: list[ProposedActionDraft] | None = None,
) -> list[ProposedActionResponse]:
    if not settings.actions_enabled:
        return []
    resolved_drafts = drafts if drafts is not None else preview_action_drafts(
        settings, question=question, answer=answer
    )
    if not resolved_drafts:
        return []
    saved = await persist_action_drafts(
        session,
        conversation_id=conversation_id,
        triggering_message_id=triggering_message_id,
        drafts=resolved_drafts,
    )
    logger.info(
        "actions_proposed",
        conversation_id=str(conversation_id),
        count=len(saved),
        types=[item.action_type.value for item in saved],
    )
    return saved


async def get_action(session: AsyncSession, action_id: UUID) -> ProposedAction | None:
    result = await session.execute(select(ProposedAction).where(ProposedAction.id == action_id))
    return result.scalar_one_or_none()


async def list_conversation_actions(
    session: AsyncSession,
    conversation_id: UUID,
) -> list[ProposedActionResponse]:
    result = await session.execute(
        select(ProposedAction)
        .where(ProposedAction.conversation_id == conversation_id)
        .order_by(ProposedAction.created_at.desc())
    )
    rows = list(result.scalars().all())
    return [_to_response(row) for row in rows]


async def reject_action(
    session: AsyncSession,
    action: ProposedAction,
    *,
    reason: str | None,
) -> ProposedActionResponse:
    if action.status != "pending":
        raise ValueError(f"Action {action.id} is not pending (status={action.status})")
    action.status = "rejected"
    action.error = reason
    await session.commit()
    await session.refresh(action)
    return _to_response(action)


async def mark_approved(
    session: AsyncSession,
    action: ProposedAction,
    *,
    approved_by: str,
) -> None:
    action.status = "approved"
    action.approved_by = approved_by
    action.approved_at = datetime.now(timezone.utc)
