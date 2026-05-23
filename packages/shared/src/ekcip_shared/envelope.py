from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiMeta(BaseModel):
    page: int | None = None
    limit: int | None = None
    total: int | None = None
    trace_id: str | None = None


class ApiEnvelope(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: str | None = None
    meta: ApiMeta = Field(default_factory=ApiMeta)

    @classmethod
    def ok(cls, data: T, *, trace_id: str | None = None, **meta: Any) -> "ApiEnvelope[T]":
        return cls(
            success=True,
            data=data,
            meta=ApiMeta(trace_id=trace_id, **{k: v for k, v in meta.items() if k in ApiMeta.model_fields}),
        )

    @classmethod
    def fail(cls, message: str, *, trace_id: str | None = None) -> "ApiEnvelope[None]":
        return cls(success=False, data=None, error=message, meta=ApiMeta(trace_id=trace_id))
