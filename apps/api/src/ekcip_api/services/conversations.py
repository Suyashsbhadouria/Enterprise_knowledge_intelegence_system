from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ekcip_api.db.models import Conversation, Message
from ekcip_api.schemas.conversations import (
    AssistantReply,
    CitationResponse,
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
    PostMessageRequest,
)
from ekcip_api.services.action_proposals import preview_action_drafts, propose_actions_for_message
from ekcip_api.services.qa_factory import build_qa_runner
from ekcip_orchestration.actions.response import (
    format_action_proposal_reply,
    is_action_primary_request,
)
from ekcip_llm.router import LlmRouter
from ekcip_llm.types import LlmMessage, LlmRole
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


async def create_conversation(
    session: AsyncSession,
    *,
    title: str | None,
    created_by: str,
) -> ConversationResponse:
    conversation = Conversation(title=title, created_by=created_by)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return ConversationResponse.model_validate(conversation, from_attributes=True)


async def get_conversation_detail(
    session: AsyncSession,
    conversation_id: UUID,
) -> ConversationDetailResponse | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return None
    messages = sorted(conversation.messages, key=lambda m: m.created_at)
    return ConversationDetailResponse(
        conversation=ConversationResponse.model_validate(conversation, from_attributes=True),
        messages=[MessageResponse.model_validate(m, from_attributes=True) for m in messages],
    )


def _history_to_llm_messages(messages: list[Message]) -> list[LlmMessage]:
    llm_messages: list[LlmMessage] = []
    for message in messages:
        if message.role not in {"user", "assistant", "system"}:
            continue
        llm_messages.append(LlmMessage(role=LlmRole(message.role), content=message.content))
    return llm_messages


async def post_message(
    session: AsyncSession,
    conversation_id: UUID,
    payload: PostMessageRequest,
    llm_router: LlmRouter,
    settings: Settings,
) -> AssistantReply | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return None

    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
    )
    session.add(user_message)
    await session.flush()

    history = sorted(conversation.messages, key=lambda m: m.created_at)
    draft_preview = preview_action_drafts(settings, question=payload.content)
    action_primary = is_action_primary_request(payload.content, draft_preview)

    if action_primary:
        proposed = await propose_actions_for_message(
            session,
            settings,
            conversation_id=conversation_id,
            triggering_message_id=user_message.id,
            question=payload.content,
            answer="",
            drafts=draft_preview,
        )
        assistant_content = format_action_proposal_reply(draft_preview)
        qa_result = None
    else:
        qa_runner = build_qa_runner(session, settings, llm_router)
        qa_result = await qa_runner.run(
            question=payload.content,
            history=_history_to_llm_messages(history),
        )
        proposed = await propose_actions_for_message(
            session,
            settings,
            conversation_id=conversation_id,
            triggering_message_id=user_message.id,
            question=payload.content,
            answer=qa_result.answer,
            drafts=draft_preview or None,
        )
        assistant_content = qa_result.answer
        if proposed:
            assistant_content = (
                f"{format_action_proposal_reply(draft_preview)}\n\n"
                "---\n\n"
                "**Additional context from knowledge search:**\n\n"
                f"{qa_result.answer}"
            )

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
    )
    session.add(assistant_message)
    await session.commit()
    await session.refresh(assistant_message)

    citations = (
        [
            CitationResponse(
                source=c.source,
                source_id=c.source_id,
                title=c.title,
                url=c.url,
                excerpt=c.excerpt,
                score=c.score,
            )
            for c in qa_result.citations
        ]
        if qa_result is not None
        else []
    )
    if action_primary and proposed:
        phase = "4-action-proposed"
    elif proposed:
        phase = "4-qa-proposed"
    elif qa_result is not None:
        phase = qa_result.phase
    else:
        phase = "4-qa"

    note_parts = [f"phase={phase}"]
    if qa_result is not None and qa_result.issue_keys:
        note_parts.append(f"keys={','.join(qa_result.issue_keys)}")
    if qa_result is not None and qa_result.llm_provider and qa_result.llm_model:
        note_parts.append(f"llm={qa_result.llm_provider}/{qa_result.llm_model}")
    if proposed:
        note_parts.append(f"proposed_actions={len(proposed)}")
    if action_primary:
        note_parts.append("mode=action_primary")

    return AssistantReply(
        message=MessageResponse.model_validate(assistant_message, from_attributes=True),
        phase=phase,
        note="; ".join(note_parts),
        llm_provider=qa_result.llm_provider if qa_result else None,
        llm_model=qa_result.llm_model if qa_result else None,
        citations=citations,
        proposed_actions=proposed,
    )
