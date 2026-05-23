from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeChunkRecord(BaseModel):
    id: UUID | None = None
    source: str
    source_id: str
    chunk_index: int = 0
    title: str
    content: str
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    indexed_at: datetime | None = None


class RetrievalHit(BaseModel):
    chunk_id: UUID
    source: str
    source_id: str
    title: str
    content: str
    url: str | None
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    source: str
    source_id: str
    title: str
    url: str | None = None
    excerpt: str
    score: float
