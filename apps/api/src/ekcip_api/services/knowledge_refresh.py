"""Refresh knowledge from live connectors before each user query (no stale index reads)."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from ekcip_connectors.confluence_cql import resolve_sync_cql
from ekcip_connectors.github_repos import resolve_sync_repos
from ekcip_connectors.jira_jql import resolve_sync_jql
from ekcip_connectors.slack_channels import resolve_sync_channels
from ekcip_api.services.confluence_sync import sync_confluence_pages
from ekcip_api.services.github_sync import build_github_connector, sync_github_repos
from ekcip_api.services.jira_sync import build_jira_connector, sync_jira_issues
from ekcip_api.services.meetings_sync import resolve_meetings_directory, sync_meeting_transcripts
from ekcip_api.services.slack_sync import build_slack_connector, sync_slack_channels
from ekcip_connectors.runtime.confluence import build_confluence_connector
from ekcip_knowledge.embeddings import EmbeddingError, EmbeddingRouter, build_embedding_router
from ekcip_knowledge.store import KnowledgeStore
from ekcip_knowledge.types import KnowledgeChunkRecord
from ekcip_orchestration.qa_graph import (
    CONFLUENCE_PAGE_ID_PATTERN,
    CONFLUENCE_PAGE_REF_PATTERN,
    GITHUB_REF_PATTERN,
    ISSUE_KEY_PATTERN,
    MEETING_REF_PATTERN,
    SLACK_MESSAGE_REF_PATTERN,
)
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

_GITHUB_ISSUE_REF = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$", re.IGNORECASE)
_GITHUB_PR_REF = re.compile(r"^([\w.-]+/[\w.-]+)!(\d+)$", re.IGNORECASE)
_GITHUB_COMMIT_REF = re.compile(r"^([\w.-]+/[\w.-]+)@([a-f0-9]{7,40})$", re.IGNORECASE)


@dataclass(frozen=True)
class QueryReferences:
    issue_keys: tuple[str, ...]
    page_ids: tuple[str, ...]
    github_refs: tuple[str, ...]
    slack_ids: tuple[str, ...]
    meeting_ids: tuple[str, ...]


def parse_query_references(question: str) -> QueryReferences:
    page_ids = list(
        dict.fromkeys(
            CONFLUENCE_PAGE_ID_PATTERN.findall(question)
            + CONFLUENCE_PAGE_REF_PATTERN.findall(question)
        )
    )
    return QueryReferences(
        issue_keys=tuple(dict.fromkeys(ISSUE_KEY_PATTERN.findall(question))),
        page_ids=tuple(page_ids),
        github_refs=tuple(dict.fromkeys(GITHUB_REF_PATTERN.findall(question))),
        slack_ids=tuple(dict.fromkeys(SLACK_MESSAGE_REF_PATTERN.findall(question))),
        meeting_ids=tuple(dict.fromkeys(MEETING_REF_PATTERN.findall(question))),
    )


async def _upsert_document(
    store: KnowledgeStore,
    embedding_router: EmbeddingRouter,
    document: dict[str, Any],
) -> bool:
    if not document.get("source_id"):
        return False
    try:
        embedding, provider = await embedding_router.embed(str(document["content"]))
    except EmbeddingError as exc:
        raise RuntimeError(f"Embedding failed ({exc.provider}): {exc}") from exc
    metadata = dict(document.get("metadata") or {})
    metadata["embedding_provider"] = provider
    metadata["live_refresh"] = True
    record = KnowledgeChunkRecord(
        source=str(document["source"]),
        source_id=str(document["source_id"]),
        title=str(document["title"]),
        content=str(document["content"]),
        url=document.get("url") if isinstance(document.get("url"), str) else None,
        metadata=metadata,
        chunk_index=int(metadata.get("chunk_index", 0)),
    )
    await store.upsert_chunk(record, embedding)
    return True


async def _sync_jira_bounded(
    settings: Settings,
    store: KnowledgeStore,
    embedding_router: EmbeddingRouter,
    max_results: int,
) -> dict[str, Any] | None:
    jira = build_jira_connector(settings)
    if jira is None:
        return None
    jql = resolve_sync_jql(None, default=settings.jira_sync_jql)
    return await sync_jira_issues(
        store,
        jira,
        embedding_router,
        jql=jql,
        max_results=max_results,
    )


async def _sync_confluence_bounded(
    settings: Settings,
    store: KnowledgeStore,
    embedding_router: EmbeddingRouter,
    max_results: int,
) -> dict[str, Any] | None:
    confluence = build_confluence_connector(settings)
    if confluence is None:
        return None
    cql = resolve_sync_cql(None, default=settings.confluence_sync_cql)
    return await sync_confluence_pages(
        store,
        confluence,
        embedding_router,
        cql=cql,
        max_results=max_results,
    )


async def _sync_github_bounded(
    settings: Settings,
    store: KnowledgeStore,
    embedding_router: EmbeddingRouter,
    max_results: int,
) -> dict[str, Any] | None:
    github = build_github_connector(settings)
    if github is None:
        return None
    repos = resolve_sync_repos(None, default=settings.github_repos)
    return await sync_github_repos(
        store,
        github,
        embedding_router,
        repos=repos,
        days=settings.github_sync_days,
        max_results_per_repo=max_results,
        max_commits_per_repo=min(settings.github_max_commits_per_repo, max_results),
    )


async def _sync_slack_bounded(
    settings: Settings,
    store: KnowledgeStore,
    embedding_router: EmbeddingRouter,
    max_results: int,
) -> dict[str, Any] | None:
    slack = build_slack_connector(settings)
    if slack is None:
        return None
    channel_ids = resolve_sync_channels(None, default=settings.slack_channel_ids)
    return await sync_slack_channels(
        store,
        slack,
        embedding_router,
        channel_ids=channel_ids,
        days=settings.slack_sync_days,
        max_messages_per_channel=max_results,
    )


async def _sync_meetings_bounded(
    settings: Settings,
    store: KnowledgeStore,
    embedding_router: EmbeddingRouter,
    max_files: int,
) -> dict[str, Any] | None:
    directory = resolve_meetings_directory(settings)
    if directory is None:
        return None
    return await sync_meeting_transcripts(
        store,
        embedding_router,
        directory=directory,
        days=settings.meetings_sync_days,
        max_files=max_files,
        max_chars=settings.meetings_chunk_max_chars,
    )


async def refresh_configured_sources(
    session: AsyncSession,
    settings: Settings,
) -> dict[str, Any]:
    """Pull latest bounded data from every configured connector into the knowledge index."""
    store = KnowledgeStore(session)
    embedding_router = build_embedding_router(settings)
    if not embedding_router.configured_providers():
        return {"status": "skipped", "reason": "no_embedding_provider"}

    max_results = settings.knowledge_query_sync_max_results
    tasks = {
        "jira": _sync_jira_bounded(settings, store, embedding_router, max_results),
        "confluence": _sync_confluence_bounded(settings, store, embedding_router, max_results),
        "github": _sync_github_bounded(settings, store, embedding_router, max_results),
        "slack": _sync_slack_bounded(settings, store, embedding_router, max_results),
        "meetings": _sync_meetings_bounded(settings, store, embedding_router, max_files=max_results),
    }
    results: dict[str, Any] = {}
    for name, coro in tasks.items():
        try:
            outcome = await coro
            results[name] = outcome or {"status": "skipped", "reason": "not_configured"}
        except Exception as exc:
            logger.warning("query_refresh_source_failed", source=name, error=str(exc)[:300])
            results[name] = {"status": "failed", "error": str(exc)[:300]}
    return results


async def refresh_live_references(
    session: AsyncSession,
    settings: Settings,
    refs: QueryReferences,
) -> dict[str, Any]:
    """Re-fetch explicitly referenced records from live APIs (overrides stale chunks)."""
    store = KnowledgeStore(session)
    embedding_router = build_embedding_router(settings)
    if not embedding_router.configured_providers():
        return {"status": "skipped", "reason": "no_embedding_provider"}

    refreshed: list[str] = []
    errors: list[str] = []

    jira = build_jira_connector(settings)
    if jira and refs.issue_keys:
        for key in refs.issue_keys:
            try:
                issue = await jira.get_issue(key)
                document = jira.issue_document(issue)
                if await _upsert_document(store, embedding_router, document):
                    refreshed.append(f"jira:{key}")
            except Exception as exc:
                errors.append(f"jira:{key}: {exc}")

    confluence = build_confluence_connector(settings)
    if confluence and refs.page_ids:
        for page_id in refs.page_ids:
            try:
                page = await confluence.get_page(page_id)
                document = confluence.page_document(page)
                if await _upsert_document(store, embedding_router, document):
                    refreshed.append(f"confluence:{page_id}")
            except Exception as exc:
                errors.append(f"confluence:{page_id}: {exc}")

    github = build_github_connector(settings)
    if github and refs.github_refs:
        for ref in refs.github_refs:
            try:
                document = await _refresh_github_ref(github, ref)
                if document and await _upsert_document(store, embedding_router, document):
                    refreshed.append(f"github:{ref}")
            except Exception as exc:
                errors.append(f"github:{ref}: {exc}")

    slack = build_slack_connector(settings)
    if slack and refs.slack_ids:
        for slack_ref in refs.slack_ids:
            channel_id, _, message_ts = slack_ref.partition(":")
            if not channel_id or not message_ts:
                continue
            try:
                info = await slack.get_channel_info(channel_id)
                channel_name = str(info.get("name") or channel_id)
                message = await slack.get_message(channel_id, message_ts)
                document = slack.message_document(channel_id, channel_name, message)
                if document and await _upsert_document(store, embedding_router, document):
                    refreshed.append(f"slack:{slack_ref}")
            except Exception as exc:
                errors.append(f"slack:{slack_ref}: {exc}")

    if refs.meeting_ids:
        directory = resolve_meetings_directory(settings)
        if directory:
            from ekcip_connectors.meetings.reader import list_transcript_files
            from ekcip_connectors.meetings.transcript import meeting_documents_from_file

            paths = list_transcript_files(directory, days=3650, max_files=500)
            wanted = {mid.lower() for mid in refs.meeting_ids}
            for path in paths:
                stem = path.stem.lower()
                if not any(w in stem or stem in w for w in wanted):
                    continue
                try:
                    for document in meeting_documents_from_file(
                        path, max_chars=settings.meetings_chunk_max_chars
                    ):
                        if await _upsert_document(store, embedding_router, document):
                            refreshed.append(f"meetings:{document['source_id']}")
                except Exception as exc:
                    errors.append(f"meetings:{path.name}: {exc}")

    return {"refreshed": refreshed, "errors": errors}


async def _refresh_github_ref(github: Any, ref: str) -> dict[str, Any] | None:
    issue_match = _GITHUB_ISSUE_REF.match(ref)
    if issue_match:
        repo, number = issue_match.group(1), int(issue_match.group(2))
        item = await github.get_item(repo, number)
        return github.item_document(repo, item)
    pr_match = _GITHUB_PR_REF.match(ref)
    if pr_match:
        repo, number = pr_match.group(1), int(pr_match.group(2))
        item = await github.get_item(repo, number)
        return github.item_document(repo, item)
    commit_match = _GITHUB_COMMIT_REF.match(ref)
    if commit_match:
        repo, sha = commit_match.group(1), commit_match.group(2)
        commit = await github.get_commit(repo, sha)
        return github.commit_document(repo, commit)
    return None


async def refresh_knowledge_for_query(
    session: AsyncSession,
    settings: Settings,
    question: str,
) -> dict[str, Any]:
    """
    Deprecated. Live data is fetched on demand during QA retrieval with Redis caching.
    """
    if settings.knowledge_refresh_on_query:
        logger.warning(
            "knowledge_refresh_on_query_deprecated",
            hint="Use live fetch + KNOWLEDGE_VECTOR_SOURCES=confluence instead",
        )
    return {"status": "disabled", "reason": "use_live_fetch_on_retrieve"}
