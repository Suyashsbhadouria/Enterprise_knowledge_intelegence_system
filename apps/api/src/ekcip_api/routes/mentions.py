from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ekcip_api.dependencies import AuthSubject, DbSession, SettingsDep
from ekcip_api.middleware.trace import get_trace_id
from ekcip_api.services.mention_catalog import build_mention_catalog
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


class MentionSuggestionResponse(BaseModel):
    kind: str
    mention: str
    label: str
    description: str | None = None
    resolved_text: str
    metadata: dict = Field(default_factory=dict)


class MentionSuggestData(BaseModel):
    suggestions: list[MentionSuggestionResponse]


@router.get("/suggest")
async def suggest_mentions(
    request: Request,
    session: DbSession,
    settings: SettingsDep,
    _subject: AuthSubject,
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=25, ge=1, le=50),
) -> JSONResponse:
    items = await build_mention_catalog(session, settings, query=q, limit=limit)
    data = MentionSuggestData(
        suggestions=[
            MentionSuggestionResponse.model_validate(item.to_api_dict())
            for item in items
        ]
    )
    envelope = ApiEnvelope.ok(data.model_dump(mode="json"), trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))
