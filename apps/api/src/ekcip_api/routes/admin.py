from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ekcip_api.dependencies import DbSession, SettingsDep
from ekcip_api.middleware.trace import get_trace_id
from ekcip_api.services.dev_seed import seed_all_sources
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


class SeedRequest(BaseModel):
    max_results: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Max Jira issues / Confluence pages per project or space",
    )


@router.post("/seed")
async def seed_test_data(
    request: Request,
    session: DbSession,
    settings: SettingsDep,
    payload: SeedRequest | None = None,
) -> JSONResponse:
    """Development-only: index real Jira + Confluence from your tenant and build Neo4j graph."""
    if settings.app_env != "development":
        raise HTTPException(
            status_code=403,
            detail="Seed endpoint is only available when APP_ENV=development",
        )

    body = payload or SeedRequest()
    try:
        result = await seed_all_sources(
            session,
            settings,
            max_results=body.max_results,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"Seed failed: {exc}") from exc

    envelope = ApiEnvelope.ok(result, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))
