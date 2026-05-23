from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=512)


class ConversationResponse(BaseModel):
    id: UUID
    title: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class PostMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=32000)


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime


class CitationResponse(BaseModel):
    source: str
    source_id: str
    title: str
    url: str | None = None
    excerpt: str
    score: float


class AssistantReply(BaseModel):
    message: MessageResponse
    phase: str = "1-qa"
    note: str
    llm_provider: str | None = None
    llm_model: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)


class ConversationDetailResponse(BaseModel):
    conversation: ConversationResponse
    messages: list[MessageResponse]
