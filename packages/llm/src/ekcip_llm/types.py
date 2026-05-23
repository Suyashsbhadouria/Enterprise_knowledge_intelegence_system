from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class LlmRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LlmMessage(BaseModel):
    role: LlmRole
    content: str


class LlmCompletionResult(BaseModel):
    content: str
    provider: str
    model: str


class LlmCompletionRequest(BaseModel):
    messages: list[LlmMessage]
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    task: Literal["chat", "summarize", "plan", "extract"] = "chat"
