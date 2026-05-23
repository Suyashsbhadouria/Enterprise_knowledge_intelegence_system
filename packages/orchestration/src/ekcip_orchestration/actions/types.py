"""Phase 4 action plane: typed proposals executed only after approval."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    SEND_SLACK_MESSAGE = "send_slack_message"
    SCHEDULE_SLACK_MESSAGE = "schedule_slack_message"
    ADD_JIRA_COMMENT = "add_jira_comment"
    UPDATE_ISSUE_STATUS = "update_issue_status"
    CREATE_REMINDER = "create_reminder"


class SendSlackMessagePayload(BaseModel):
    channel_id: str
    text: str
    thread_ts: str | None = None


class ScheduleSlackMessagePayload(BaseModel):
    channel_id: str
    text: str
    post_at: int = Field(description="Unix timestamp when Slack should post the message")


class AddJiraCommentPayload(BaseModel):
    issue_key: str
    body: str


class UpdateIssueStatusPayload(BaseModel):
    issue_key: str
    status_name: str


class CreateReminderPayload(BaseModel):
    message: str
    remind_at: int = Field(description="Unix timestamp for reminder delivery")
    channel_id: str | None = None


ActionPayload = (
    SendSlackMessagePayload
    | ScheduleSlackMessagePayload
    | AddJiraCommentPayload
    | UpdateIssueStatusPayload
    | CreateReminderPayload
)


class ProposedActionDraft(BaseModel):
    """In-memory proposal before persistence."""

    action_type: ActionType
    payload: dict[str, Any]
    preview: str
    rationale: str | None = None


class ProposedActionRecord(BaseModel):
    """API-facing proposed action."""

    id: str
    conversation_id: str
    triggering_message_id: str
    action_type: ActionType
    payload: dict[str, Any]
    preview: str
    status: Literal["pending", "approved", "rejected", "executed", "failed"]
    rationale: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    executed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
