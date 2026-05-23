from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ekcip_orchestration.actions.types import ActionType


class ProposedActionResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    triggering_message_id: UUID
    action_type: ActionType
    payload: dict[str, Any]
    preview: str
    rationale: str | None = None
    status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime


class ApproveActionRequest(BaseModel):
    execute: bool = Field(
        default=True,
        description="When true, run the action immediately after recording approval.",
    )


class RejectActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
