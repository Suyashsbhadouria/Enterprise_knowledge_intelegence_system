"""Cached per-source entity counts for dashboard and knowledge status."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from ekcip_api.services.github_sync import build_github_connector
from ekcip_api.services.jira_sync import build_jira_connector
from ekcip_api.services.meetings_sync import resolve_meetings_directory
from ekcip_api.services.slack_sync import build_slack_connector
from ekcip_connectors.confluence_cql import resolve_sync_cql
from ekcip_connectors.github_repos import resolve_sync_repos
from ekcip_connectors.jira_jql import resolve_sync_jql
from ekcip_connectors.meetings.reader import list_transcript_files
from ekcip_connectors.runtime.confluence import build_confluence_connector
from ekcip_connectors.slack_channels import resolve_sync_channels
from ekcip_knowledge.source_intent import parse_vector_sources
from ekcip_knowledge.store import KnowledgeStore
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


@dataclass(frozen=True)
class KnowledgeSourceStatsSnapshot:
    jira_entities: int = 0
    confluence_entities: int = 0
    github_entities: int = 0
    slack_entities: int = 0
    meetings_entities: int = 0
    synced_at: str | None = None

    @property
    def total_entities(self) -> int:
        return (
            self.jira_entities
            + self.confluence_entities
            + self.github_entities
            + self.slack_entities
            + self.meetings_entities
        )

    def to_status_fields(self) -> dict[str, int | str | None]:
        return {
            "jira_entities": self.jira_entities,
            "confluence_entities": self.confluence_entities,
            "github_entities": self.github_entities,
            "slack_entities": self.slack_entities,
            "meetings_entities": self.meetings_entities,
            "total_entities": self.total_entities,
            "stats_synced_at": self.synced_at,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_cached_source_stats(app) -> KnowledgeSourceStatsSnapshot:
    stats = getattr(app.state, "knowledge_source_stats", None)
    if isinstance(stats, KnowledgeSourceStatsSnapshot):
        return stats
    return KnowledgeSourceStatsSnapshot()


def set_cached_source_stats(app, stats: KnowledgeSourceStatsSnapshot) -> None:
    app.state.knowledge_source_stats = stats


async def _count_jira_entities(settings: Settings) -> int:
    jira = build_jira_connector(settings)
    if jira is None:
        return 0
    jql = resolve_sync_jql(None, default=settings.jira_sync_jql)
    issues = await jira.search_issues(jql, max_results=settings.knowledge_query_sync_max_results)
    return len(issues)


async def _count_confluence_entities(settings: Settings, store: KnowledgeStore) -> int:
    vector_sources = parse_vector_sources(settings.knowledge_vector_sources)
    if "confluence" in vector_sources:
        indexed_pages = await store.count_distinct_source_ids("confluence")
        if indexed_pages > 0:
            return indexed_pages

    confluence = build_confluence_connector(settings)
    if confluence is None:
        return 0
    cql = resolve_sync_cql(None, default=settings.confluence_sync_cql)
    pages = await confluence.search_pages(cql, max_results=settings.knowledge_query_sync_max_results)
    return len(pages)


async def _count_github_entities(settings: Settings) -> int:
    github = build_github_connector(settings)
    if not github or not settings.github_repos.strip():
        return 0
    repos = resolve_sync_repos(None, default=settings.github_repos)
    since_iso = github.since_iso(settings.github_sync_days)
    per_repo = settings.github_max_results_per_repo
    commits_per_repo = settings.github_max_commits_per_repo
    total = 0
    for repo in repos:
        items = await github.list_recent_items(repo, since_iso=since_iso, max_results=per_repo)
        commits = await github.list_recent_commits(
            repo, since_iso=since_iso, max_results=commits_per_repo
        )
        total += len(items or []) + len(commits or [])
    return total


async def _count_slack_entities(settings: Settings) -> int:
    slack = build_slack_connector(settings)
    if slack is None:
        return 0
    channel_ids = resolve_sync_channels(None, default=settings.slack_channel_ids)
    if not channel_ids:
        joined = await slack.list_joined_channels(limit=10)
        channel_ids = [str(channel["id"]) for channel in joined]
    oldest = slack.oldest_timestamp(settings.slack_sync_days)
    per_channel = settings.slack_max_messages_per_channel
    total = 0
    for channel_id in channel_ids:
        messages = await slack.fetch_channel_messages(
            channel_id,
            oldest=oldest,
            max_messages=per_channel,
        )
        total += len(messages or [])
    return total


async def _count_meetings_entities(settings: Settings) -> int:
    directory = resolve_meetings_directory(settings)
    if directory is None:
        return 0
    paths = list_transcript_files(
        directory,
        days=settings.meetings_sync_days,
        max_files=settings.meetings_max_files,
    )
    return len(paths)


async def compute_all_source_stats(
    session: AsyncSession,
    settings: Settings,
) -> KnowledgeSourceStatsSnapshot:
    store = KnowledgeStore(session)
    jira_entities = 0
    confluence_entities = 0
    github_entities = 0
    slack_entities = 0
    meetings_entities = 0

    if settings.jira_configured:
        try:
            jira_entities = await _count_jira_entities(settings)
        except Exception as exc:
            logger.warning("source_stats_jira_failed", error=str(exc)[:300])

    if settings.confluence_configured:
        try:
            confluence_entities = await _count_confluence_entities(settings, store)
        except Exception as exc:
            logger.warning("source_stats_confluence_failed", error=str(exc)[:300])

    if settings.github_configured:
        try:
            github_entities = await _count_github_entities(settings)
        except Exception as exc:
            logger.warning("source_stats_github_failed", error=str(exc)[:300])

    if settings.slack_configured:
        try:
            slack_entities = await _count_slack_entities(settings)
        except Exception as exc:
            logger.warning("source_stats_slack_failed", error=str(exc)[:300])

    if settings.meetings_configured:
        try:
            meetings_entities = await _count_meetings_entities(settings)
        except Exception as exc:
            logger.warning("source_stats_meetings_failed", error=str(exc)[:300])

    snapshot = KnowledgeSourceStatsSnapshot(
        jira_entities=jira_entities,
        confluence_entities=confluence_entities,
        github_entities=github_entities,
        slack_entities=slack_entities,
        meetings_entities=meetings_entities,
        synced_at=_now_iso(),
    )
    logger.info(
        "knowledge_source_stats_computed",
        jira=jira_entities,
        confluence=confluence_entities,
        github=github_entities,
        slack=slack_entities,
        meetings=meetings_entities,
    )
    return snapshot


def apply_entity_counts(
    current: KnowledgeSourceStatsSnapshot,
    *,
    jira: int | None = None,
    confluence: int | None = None,
    github: int | None = None,
    slack: int | None = None,
    meetings: int | None = None,
) -> KnowledgeSourceStatsSnapshot:
    updates: dict[str, int | str | None] = {"synced_at": _now_iso()}
    if jira is not None:
        updates["jira_entities"] = jira
    if confluence is not None:
        updates["confluence_entities"] = confluence
    if github is not None:
        updates["github_entities"] = github
    if slack is not None:
        updates["slack_entities"] = slack
    if meetings is not None:
        updates["meetings_entities"] = meetings
    return replace(current, **updates)


def update_stats_after_sync(
    current: KnowledgeSourceStatsSnapshot,
    source: str,
    result: dict[str, object],
) -> KnowledgeSourceStatsSnapshot:
    entity_count = _entity_count_from_sync_result(source, result)
    if entity_count is None:
        return current

    updates: dict[str, int | str | None] = {"synced_at": _now_iso()}
    if source == "jira":
        updates["jira_entities"] = entity_count
    elif source == "confluence":
        updates["confluence_entities"] = entity_count
    elif source == "github":
        updates["github_entities"] = entity_count
    elif source == "slack":
        updates["slack_entities"] = entity_count
    elif source == "meetings":
        updates["meetings_entities"] = entity_count
    else:
        return current

    return replace(current, **updates)


def _entity_count_from_sync_result(source: str, result: dict[str, object]) -> int | None:
    key_by_source = {
        "jira": "issues_indexed",
        "confluence": "pages_indexed",
        "github": "items_indexed",
        "slack": "messages_indexed",
        "meetings": "transcripts_indexed",
    }
    key = key_by_source.get(source)
    if key is None:
        return None
    value = result.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
