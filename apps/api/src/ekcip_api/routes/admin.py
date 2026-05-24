from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ekcip_api.dependencies import DbSession, SettingsDep
from ekcip_api.middleware.trace import get_trace_id
from ekcip_connectors.fixtures.enterprise_catalog import build_meeting_transcript_files
from ekcip_api.services.dev_seed import seed_all_sources
from ekcip_api.services.enterprise_fixture_seed import seed_enterprise_fixture
from ekcip_api.services.knowledge_source_stats import apply_entity_counts, get_cached_source_stats, set_cached_source_stats
from ekcip_api.services.enterprise_publish import publish_enterprise_to_live_sources
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


class SeedRequest(BaseModel):
    max_results: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Max Jira issues / Confluence pages per project or space",
    )


class EnterpriseFixtureSeedRequest(BaseModel):
    clear_existing: bool = Field(
        default=True,
        description="Remove existing jira/confluence/slack/meetings chunks before seeding",
    )


class EnterprisePublishRequest(BaseModel):
    dry_run: bool = Field(
        default=False,
        description="If true, only validate mappings and return planned creates (no API writes)",
    )
    clear_knowledge_before_reindex: bool = Field(
        default=True,
        description="Clear knowledge chunks before re-indexing from live systems",
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


@router.post("/seed-enterprise")
async def seed_enterprise_fixture_data(
    request: Request,
    session: DbSession,
    settings: SettingsDep,
    payload: EnterpriseFixtureSeedRequest | None = None,
) -> JSONResponse:
    """
    Development-only: load interconnected Nexus Dynamics fixture data
    (Jira, Confluence, Slack, meetings). No GitHub. No live connector APIs required.
    """
    if settings.app_env != "development":
        raise HTTPException(
            status_code=403,
            detail="Enterprise fixture seed is only available when APP_ENV=development",
        )

    body = payload or EnterpriseFixtureSeedRequest()
    try:
        result = await seed_enterprise_fixture(
            session,
            settings,
            clear_existing=body.clear_existing,
        )
        await session.commit()
        indexed = result.get("indexed_this_run") or {}
        set_cached_source_stats(
            request.app,
            apply_entity_counts(
                get_cached_source_stats(request.app),
                jira=int(indexed.get("jira", 0)),
                confluence=int(indexed.get("confluence", 0)),
                slack=int(indexed.get("slack", 0)),
                meetings=len(build_meeting_transcript_files()),
            ),
        )
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"Enterprise fixture seed failed: {exc}",
        ) from exc

    envelope = ApiEnvelope.ok(result, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post("/publish-enterprise")
async def publish_enterprise_to_live(
    request: Request,
    session: DbSession,
    settings: SettingsDep,
    payload: EnterprisePublishRequest | None = None,
) -> JSONResponse:
    """
    Development-only: create Nexus Dynamics content in your real Jira, Confluence, and Slack,
    then re-index Postgres knowledge + Neo4j from live records.
    """
    if settings.app_env != "development":
        raise HTTPException(
            status_code=403,
            detail="Publish endpoint is only available when APP_ENV=development",
        )

    body = payload or EnterprisePublishRequest()
    try:
        result = await publish_enterprise_to_live_sources(
            session,
            settings,
            dry_run=body.dry_run,
            clear_knowledge_before_reindex=body.clear_knowledge_before_reindex,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"Enterprise publish failed: {exc}",
        ) from exc

    envelope = ApiEnvelope.ok(result, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))
