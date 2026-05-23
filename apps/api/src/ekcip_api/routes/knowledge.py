from fastapi import APIRouter, HTTPException, Request
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
from ekcip_api.services.slack_sync import build_slack_connector, sync_slack_channels
from ekcip_graph.client import verify_neo4j_connection
from ekcip_knowledge.embeddings import build_embedding_router
from ekcip_knowledge.store import KnowledgeStore
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


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


@router.get("/status")
async def knowledge_status(request: Request, session: DbSession) -> JSONResponse:
    settings = request.app.state.settings
    store = KnowledgeStore(session)
    jira_chunks = await store.count_chunks(source="jira")
    confluence_chunks = await store.count_chunks(source="confluence")
    github_chunks = await store.count_chunks(source="github")
    slack_chunks = await store.count_chunks(source="slack")
    neo4j_status = await verify_neo4j_connection(settings)
    envelope = ApiEnvelope.ok(
        {
            "jira_chunks": jira_chunks,
            "confluence_chunks": confluence_chunks,
            "github_chunks": github_chunks,
            "slack_chunks": slack_chunks,
            "total_chunks": jira_chunks + confluence_chunks + github_chunks + slack_chunks,
            "jira_configured": settings.jira_configured,
            "confluence_configured": settings.confluence_configured,
            "github_configured": settings.github_configured,
            "slack_configured": settings.slack_configured,
            "confluence_wiki_base_url": settings.confluence_wiki_base_url,
            "neo4j_configured": settings.neo4j_configured,
            "neo4j_status": neo4j_status.get("status"),
            "graph_phase": 3,
            "actions_phase": 4,
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
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"Slack sync failed: {exc}") from exc

    envelope = ApiEnvelope.ok(result, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))
