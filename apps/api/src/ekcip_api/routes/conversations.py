from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ekcip_api.dependencies import AuthSubject, DbSession, SettingsDep
from ekcip_api.middleware.trace import get_trace_id
from ekcip_api.schemas.conversations import (
    CreateConversationRequest,
    PostMessageRequest,
)
from ekcip_api.services import conversations as conversation_service
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


@router.post("")
async def create_conversation(
    request: Request,
    payload: CreateConversationRequest,
    session: DbSession,
    subject: AuthSubject,
) -> JSONResponse:
    created_by = subject or "anonymous"
    conversation = await conversation_service.create_conversation(
        session,
        title=payload.title,
        created_by=created_by,
    )
    envelope = ApiEnvelope.ok(conversation.model_dump(mode="json"), trace_id=get_trace_id(request))
    return JSONResponse(status_code=201, content=envelope.model_dump(mode="json"))


@router.get("/{conversation_id}")
async def get_conversation(
    request: Request,
    conversation_id: UUID,
    session: DbSession,
    _subject: AuthSubject,
) -> JSONResponse:
    detail = await conversation_service.get_conversation_detail(session, conversation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    envelope = ApiEnvelope.ok(detail.model_dump(mode="json"), trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post("/{conversation_id}/messages")
async def post_message(
    request: Request,
    conversation_id: UUID,
    payload: PostMessageRequest,
    session: DbSession,
    settings: SettingsDep,
    _subject: AuthSubject,
) -> JSONResponse:
    llm_router = request.app.state.llm_router
    reply = await conversation_service.post_message(
        session, conversation_id, payload, llm_router, settings
    )
    if reply is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    envelope = ApiEnvelope.ok(reply.model_dump(mode="json"), trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))
