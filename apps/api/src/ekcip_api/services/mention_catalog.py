"""Build @mention suggestions from live Slack, Jira, GitHub, Confluence, and indexed knowledge."""

from __future__ import annotations

import re

from ekcip_connectors.github_repos import parse_repo_list
from ekcip_connectors.jira_jql import resolve_sync_jql
from ekcip_connectors.mentions import MentionSuggestion, filter_suggestions
from ekcip_api.services.jira_sync import build_jira_connector
from ekcip_api.services.slack_sync import build_slack_connector
from ekcip_knowledge.store import KnowledgeStore
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

_ISSUE_KEY_IN_TEXT = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


async def _slack_channel_suggestions(settings: Settings) -> list[MentionSuggestion]:
    slack = build_slack_connector(settings)
    if slack is None:
        return []
    try:
        channels = await slack.list_joined_channels(limit=200)
    except Exception as exc:
        logger.warning("mention_slack_channels_failed", error=str(exc)[:300])
        return []

    items: list[MentionSuggestion] = []
    for channel in channels:
        name = channel["name"]
        channel_id = channel["id"]
        items.append(
            MentionSuggestion(
                kind="slack_channel",
                mention=f"@{name}",
                label=f"#{name}",
                description=f"Slack channel · {channel_id}",
                resolved_text=channel_id,
                metadata={"channel_id": channel_id, "channel_name": name},
            )
        )
    return items


async def _jira_issue_suggestions(
    settings: Settings,
    query: str,
    *,
    limit: int,
) -> list[MentionSuggestion]:
    jira = build_jira_connector(settings)
    if jira is None:
        return []

    issues: list[dict] = []
    try:
        if query.strip():
            safe = query.strip().replace('"', '\\"')
            if _ISSUE_KEY_IN_TEXT.match(query.strip().upper()):
                key = query.strip().upper()
                issue = await jira.get_issue(key)
                issues = [issue]
            else:
                jql = (
                    f'(key ~ "{safe}*" OR summary ~ "{safe}*") '
                    f'AND updated >= -90d ORDER BY updated DESC'
                )
                issues = await jira.search_issues(jql, max_results=limit)
        else:
            jql = resolve_sync_jql(None, default=settings.jira_sync_jql)
            issues = await jira.search_issues(jql, max_results=limit)
    except Exception as exc:
        logger.warning("mention_jira_search_failed", error=str(exc)[:300])
        return []

    items: list[MentionSuggestion] = []
    for issue in issues:
        key = str(issue.get("key") or "")
        if not key:
            continue
        fields = issue.get("fields") or {}
        summary = str(fields.get("summary") or key)
        status = (fields.get("status") or {}).get("name", "")
        items.append(
            MentionSuggestion(
                kind="jira_issue",
                mention=f"@{key}",
                label=key,
                description=summary if not status else f"{summary} · {status}",
                resolved_text=key,
                metadata={"issue_key": key, "summary": summary, "status": status},
            )
        )
    return items


def _github_repo_suggestions(settings: Settings) -> list[MentionSuggestion]:
    if not settings.github_repos.strip():
        return []
    try:
        repos = parse_repo_list(settings.github_repos)
    except ValueError:
        return []
    return [
        MentionSuggestion(
            kind="github_repo",
            mention=f"@{repo}",
            label=repo,
            description="GitHub repository",
            resolved_text=repo,
            metadata={"repo": repo},
        )
        for repo in repos
    ]


async def _jira_project_suggestions(settings: Settings, *, limit: int) -> list[MentionSuggestion]:
    jira = build_jira_connector(settings)
    if jira is None:
        return []
    try:
        projects = await jira.list_projects(max_results=limit)
    except Exception as exc:
        logger.warning("mention_jira_projects_failed", error=str(exc)[:300])
        return []
    items: list[MentionSuggestion] = []
    for project in projects:
        key = str(project.get("key") or "")
        name = str(project.get("name") or key)
        if not key:
            continue
        items.append(
            MentionSuggestion(
                kind="jira_project",
                mention=f"@{key}",
                label=f"{key} — {name}",
                description="Jira project",
                resolved_text=key,
                metadata={"project_key": key, "project_name": name},
            )
        )
    return items


async def _confluence_page_suggestions(
    session: AsyncSession,
    query: str,
    *,
    limit: int,
) -> list[MentionSuggestion]:
    store = KnowledgeStore(session)
    try:
        chunks = await store.search_by_title_substring("confluence", query, limit=limit)
    except Exception:
        chunks = []
    items: list[MentionSuggestion] = []
    for chunk in chunks:
        page_id = str(chunk.source_id)
        title = chunk.title
        items.append(
            MentionSuggestion(
                kind="confluence_page",
                mention=f"@page-{page_id}",
                label=title,
                description=f"Confluence page · {page_id}",
                resolved_text=f"page {page_id}",
                metadata={"page_id": page_id, "title": title, "url": chunk.url},
            )
        )
    return items


async def _indexed_slack_suggestions(session: AsyncSession, query: str, *, limit: int) -> list[MentionSuggestion]:
    store = KnowledgeStore(session)
    try:
        chunks = await store.search_by_title_substring("slack", query, limit=limit)
    except Exception:
        return []
    items: list[MentionSuggestion] = []
    seen: set[str] = set()
    for chunk in chunks:
        channel_name = str((chunk.metadata or {}).get("channel_name") or "")
        channel_id = str((chunk.metadata or {}).get("channel_id") or chunk.source_id.split(":")[0])
        if not channel_name or channel_name in seen:
            continue
        seen.add(channel_name)
        items.append(
            MentionSuggestion(
                kind="slack_channel",
                mention=f"@{channel_name}",
                label=f"#{channel_name}",
                description="From indexed Slack history",
                resolved_text=channel_id,
                metadata={"channel_id": channel_id, "channel_name": channel_name},
            )
        )
    return items


async def build_mention_catalog(
    session: AsyncSession,
    settings: Settings,
    *,
    query: str = "",
    limit: int = 25,
) -> list[MentionSuggestion]:
    """Aggregate mentionables; filter client-side by query substring."""
    per_source = max(limit, 10)
    slack_live, slack_indexed, jira_issues, github, jira_projects = await _gather(
        session,
        settings,
        query,
        per_source=per_source,
    )

    merged: list[MentionSuggestion] = []
    seen: set[tuple[str, str]] = set()
    for item in (
        *slack_live,
        *slack_indexed,
        *jira_issues,
        *jira_projects,
        *github,
    ):
        key = (item.kind, item.mention.lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)

    confluence = await _confluence_page_suggestions(session, query, limit=per_source)
    if confluence:
        merged.extend(confluence)

    return filter_suggestions(merged, query, limit=limit)


async def _gather(
    session: AsyncSession,
    settings: Settings,
    query: str,
    *,
    per_source: int,
):
    import asyncio

    return await asyncio.gather(
        _slack_channel_suggestions(settings),
        _indexed_slack_suggestions(session, query, limit=per_source),
        _jira_issue_suggestions(settings, query, limit=per_source),
        asyncio.to_thread(_github_repo_suggestions, settings),
        _jira_project_suggestions(settings, limit=per_source),
    )
