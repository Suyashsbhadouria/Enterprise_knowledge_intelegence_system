from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ekcip_api.dependencies import DbSession
from ekcip_api.middleware.trace import get_trace_id
from ekcip_connectors.confluence_cql import resolve_sync_cql
from ekcip_connectors.github_repos import resolve_sync_repos
from ekcip_connectors.jira_jql import resolve_sync_jql
from ekcip_connectors.runtime.confluence import build_confluence_connector
from ekcip_connectors.slack_channels import resolve_sync_channels
from ekcip_api.services.confluence_sync import sync_confluence_pages
from ekcip_api.services.github_sync import build_github_connector, sync_github_repos
from ekcip_api.services.jira_sync import build_jira_connector, sync_jira_issues
from ekcip_api.services.knowledge_source_stats import (
    apply_entity_counts,
    get_cached_source_stats,
    set_cached_source_stats,
    update_stats_after_sync,
)
from ekcip_api.services.meetings_sync import resolve_meetings_directory, sync_meeting_transcripts
from ekcip_api.services.slack_sync import build_slack_connector, sync_slack_channels
from ekcip_connectors.meetings.transcript import SUPPORTED_EXTENSIONS
from ekcip_graph.client import verify_neo4j_connection
from ekcip_knowledge.embeddings import build_embedding_router
from ekcip_knowledge.store import KnowledgeStore
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


def _apply_sync_stats(request: Request, source: str, result: dict[str, object]) -> None:
    current = get_cached_source_stats(request.app)
    set_cached_source_stats(request.app, update_stats_after_sync(current, source, result))


class JiraSyncRequest(BaseModel):
    jql: str | None = Field(
        default=None,
        description="Jira JQL query; defaults to JIRA_SYNC_JQL from settings",
    )
    max_results: int = Field(default=50, ge=1, le=200)


class ConfluenceSyncRequest(BaseModel):
    cql: str | None = Field(
        default=None,
        description="Confluence CQL query; defaults to CONFLUENCE_SYNC_CQL from settings",
    )
    max_results: int = Field(default=50, ge=1, le=200)


class GitHubSyncRequest(BaseModel):
    repos: str | None = Field(
        default=None,
        description="Comma-separated owner/repo list; defaults to GITHUB_REPOS from settings",
    )
    days: int | None = Field(default=None, ge=1, le=365)
    max_results_per_repo: int = Field(default=50, ge=1, le=200)
    max_commits_per_repo: int = Field(default=50, ge=1, le=500)


class SlackSyncRequest(BaseModel):
    channel_ids: str | None = Field(
        default=None,
        description="Comma-separated Slack channel IDs; defaults to SLACK_CHANNEL_IDS",
    )
    days: int | None = Field(default=None, ge=1, le=365)
    max_messages_per_channel: int = Field(default=100, ge=1, le=500)


class MeetingsSyncRequest(BaseModel):
    directory: str | None = Field(
        default=None,
        description="Directory of transcript exports; defaults to MEETINGS_TRANSCRIPTS_DIR",
    )
    days: int | None = Field(default=None, ge=1, le=365)
    max_files: int = Field(default=100, ge=1, le=500)


@router.get("/status")
async def knowledge_status(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    source_stats = get_cached_source_stats(request.app)
    neo4j_status = await verify_neo4j_connection(settings)
    envelope = ApiEnvelope.ok(
        {
            **source_stats.to_status_fields(),
            "jira_configured": settings.jira_configured,
            "confluence_configured": settings.confluence_configured,
            "github_configured": settings.github_configured,
            "slack_configured": settings.slack_configured,
            "confluence_wiki_base_url": settings.confluence_wiki_base_url,
            "neo4j_configured": settings.neo4j_configured,
            "neo4j_status": neo4j_status.get("status"),
            "graph_phase": 3,
            "actions_phase": 4,
            "meetings_phase": 5,
            "meetings_configured": settings.meetings_configured,
            "meetings_transcripts_dir": settings.meetings_transcripts_dir or None,
            "actions_enabled": settings.actions_enabled,
            "actions_require_approval": settings.actions_require_approval,
            "embedding_providers": build_embedding_router(settings).configured_providers(),
            "local_embedding_model": settings.local_embedding_model,
            "local_embeddings_enabled": settings.local_embeddings_enabled,
        },
        trace_id=get_trace_id(request),
    )
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post("/jira/sync")
async def sync_jira(
    request: Request,
    session: DbSession,
    payload: JiraSyncRequest | None = None,
) -> JSONResponse:
    settings = request.app.state.settings
    jira = build_jira_connector(settings)
    if jira is None:
        raise HTTPException(
            status_code=400,
            detail="Jira not configured. Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN.",
        )
    embedding_router = build_embedding_router(settings)
    if not embedding_router.configured_providers():
        raise HTTPException(
            status_code=400,
            detail="No embedding provider configured. Set GEMINI_API_KEY or HUGGINGFACE_API_KEY.",
        )

    body = payload or JiraSyncRequest()
    jql = resolve_sync_jql(
        body.jql,
        default=settings.jira_sync_jql,
    )
    store = KnowledgeStore(session)
    try:
        result = await sync_jira_issues(
            store,
            jira,
            embedding_router,
            jql=jql,
            max_results=body.max_results,
        )
        await session.commit()
        _apply_sync_stats(request, "jira", result)
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"Jira sync failed: {exc}") from exc

    envelope = ApiEnvelope.ok(result, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post("/confluence/sync")
async def sync_confluence(
    request: Request,
    session: DbSession,
    payload: ConfluenceSyncRequest | None = None,
) -> JSONResponse:
    settings = request.app.state.settings
    confluence = build_confluence_connector(settings)
    if confluence is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Confluence not configured. Set CONFLUENCE_BASE_URL (or JIRA_BASE_URL) "
                "plus JIRA_EMAIL and JIRA_API_TOKEN (same Atlassian API token)."
            ),
        )
    embedding_router = build_embedding_router(settings)
    if not embedding_router.configured_providers():
        raise HTTPException(
            status_code=400,
            detail="No embedding provider configured. Set GEMINI_API_KEY or HUGGINGFACE_API_KEY.",
        )

    body = payload or ConfluenceSyncRequest()
    cql = resolve_sync_cql(
        body.cql,
        default=settings.confluence_sync_cql,
    )
    store = KnowledgeStore(session)
    try:
        result = await sync_confluence_pages(
            store,
            confluence,
            embedding_router,
            cql=cql,
            max_results=body.max_results,
        )
        await session.commit()
        _apply_sync_stats(request, "confluence", result)
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"Confluence sync failed: {exc}") from exc

    envelope = ApiEnvelope.ok(result, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post("/github/sync")
async def sync_github(
    request: Request,
    session: DbSession,
    payload: GitHubSyncRequest | None = None,
) -> JSONResponse:
    settings = request.app.state.settings
    github = build_github_connector(settings)
    if github is None:
        raise HTTPException(
            status_code=400,
            detail="GitHub not configured. Set GITHUB_TOKEN and GITHUB_REPOS=owner/repo.",
        )
    embedding_router = build_embedding_router(settings)
    if not embedding_router.configured_providers():
        raise HTTPException(
            status_code=400,
            detail="No embedding provider configured. Set GEMINI_API_KEY or HUGGINGFACE_API_KEY.",
        )

    body = payload or GitHubSyncRequest()
    try:
        repos = resolve_sync_repos(body.repos, default=settings.github_repos)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store = KnowledgeStore(session)
    try:
        result = await sync_github_repos(
            store,
            github,
            embedding_router,
            repos=repos,
            days=body.days or settings.github_sync_days,
            max_results_per_repo=body.max_results_per_repo,
            max_commits_per_repo=body.max_commits_per_repo or settings.github_max_commits_per_repo,
        )
        await session.commit()
        _apply_sync_stats(request, "github", result)
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"GitHub sync failed: {exc}") from exc

    envelope = ApiEnvelope.ok(result, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post("/slack/sync")
async def sync_slack(
    request: Request,
    session: DbSession,
    payload: SlackSyncRequest | None = None,
) -> JSONResponse:
    settings = request.app.state.settings
    slack = build_slack_connector(settings)
    if slack is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Slack not configured. Set SLACK_BOT_TOKEN and "
                "SLACK_CHANNEL_IDS=C01234567,... (channels the bot is in)."
            ),
        )
    embedding_router = build_embedding_router(settings)
    if not embedding_router.configured_providers():
        raise HTTPException(
            status_code=400,
            detail="No embedding provider configured. Set GEMINI_API_KEY or HUGGINGFACE_API_KEY.",
        )

    body = payload or SlackSyncRequest()
    try:
        channel_ids = resolve_sync_channels(body.channel_ids, default=settings.slack_channel_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store = KnowledgeStore(session)
    try:
        result = await sync_slack_channels(
            store,
            slack,
            embedding_router,
            channel_ids=channel_ids,
            days=body.days or settings.slack_sync_days,
            max_messages_per_channel=body.max_messages_per_channel,
        )
        await session.commit()
        _apply_sync_stats(request, "slack", result)
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"Slack sync failed: {exc}") from exc

    envelope = ApiEnvelope.ok(result, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post("/meetings/sync")
async def sync_meetings(
    request: Request,
    session: DbSession,
    payload: MeetingsSyncRequest | None = None,
) -> JSONResponse:
    settings = request.app.state.settings
    embedding_router = build_embedding_router(settings)
    if not embedding_router.configured_providers():
        raise HTTPException(
            status_code=400,
            detail="No embedding provider configured. Set GEMINI_API_KEY or HUGGINGFACE_API_KEY.",
        )

    body = payload or MeetingsSyncRequest()
    directory = resolve_meetings_directory(settings, body.directory)
    if directory is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Meetings directory not configured or missing. Set MEETINGS_TRANSCRIPTS_DIR "
                "to a folder containing .vtt, .srt, .txt, or .md transcript exports."
            ),
        )

    store = KnowledgeStore(session)
    try:
        result = await sync_meeting_transcripts(
            store,
            embedding_router,
            directory=directory,
            days=body.days or settings.meetings_sync_days,
            max_files=body.max_files or settings.meetings_max_files,
            max_chars=settings.meetings_chunk_max_chars,
        )
        await session.commit()
        _apply_sync_stats(request, "meetings", result)
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"Meetings sync failed: {exc}") from exc

    envelope = ApiEnvelope.ok(result, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.post("/meetings/upload")
async def upload_meeting_transcript(
    request: Request,
    session: DbSession,
    file: UploadFile = File(...),
) -> JSONResponse:
    settings = request.app.state.settings
    embedding_router = build_embedding_router(settings)
    if not embedding_router.configured_providers():
        raise HTTPException(
            status_code=400,
            detail="No embedding provider configured. Set GEMINI_API_KEY or HUGGINGFACE_API_KEY.",
        )

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported transcript type '{suffix}'. Use .vtt, .srt, .txt, or .md.",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Transcript must be UTF-8 text.") from exc

    upload_dir = resolve_meetings_directory(settings)
    if upload_dir is None:
        configured = settings.meetings_transcripts_dir.strip()
        if not configured:
            raise HTTPException(
                status_code=400,
                detail="Set MEETINGS_TRANSCRIPTS_DIR before uploading transcripts.",
            )
        upload_dir = Path(configured).expanduser()
        upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "upload.txt").name
    saved_path = (upload_dir / safe_name).resolve()
    saved_path.write_text(text, encoding="utf-8")

    store = KnowledgeStore(session)
    try:
        result = await sync_meeting_transcripts(
            store,
            embedding_router,
            directory=upload_dir,
            days=3650,
            max_files=1,
            max_chars=settings.meetings_chunk_max_chars,
            files=[saved_path],
        )
        await session.commit()
        _apply_sync_stats(request, "meetings", result)
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"Meetings upload failed: {exc}") from exc

    envelope = ApiEnvelope.ok(result, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))
