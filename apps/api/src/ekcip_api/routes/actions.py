from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ekcip_api.dependencies import AuthSubject, DbSession, SettingsDep
from ekcip_api.middleware.trace import get_trace_id
from ekcip_api.schemas.actions import ApproveActionRequest, RejectActionRequest
from ekcip_api.services import action_executor, action_proposals
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


@router.get("/conversations/{conversation_id}/actions")
async def list_conversation_actions(
    request: Request,
    conversation_id: UUID,
    session: DbSession,
    _subject: AuthSubject,
) -> JSONResponse:
    actions = await action_proposals.list_conversation_actions(session, conversation_id)
    envelope = ApiEnvelope.ok(
        {"actions": [item.model_dump(mode="json") for item in actions]},
        trace_id=get_trace_id(request),
    )
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post("/{action_id}/approve")
async def approve_action(
    request: Request,
    action_id: UUID,
    payload: ApproveActionRequest,
    session: DbSession,
    settings: SettingsDep,
    subject: AuthSubject,
) -> JSONResponse:
    action = await action_proposals.get_action(session, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    approved_by = subject or "anonymous"
    try:
        updated = await action_executor.approve_and_execute(
            session,
            action,
            settings=settings,
            approved_by=approved_by,
            execute=payload.execute,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    envelope = ApiEnvelope.ok(updated.model_dump(mode="json"), trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post("/{action_id}/reject")
async def reject_action(
    request: Request,
    action_id: UUID,
    payload: RejectActionRequest,
    session: DbSession,
    _subject: AuthSubject,
) -> JSONResponse:
    action = await action_proposals.get_action(session, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    try:
        updated = await action_proposals.reject_action(session, action, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    envelope = ApiEnvelope.ok(updated.model_dump(mode="json"), trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))
