"""Fetch knowledge from live connectors on demand (not from the vector index)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from ekcip_connectors.github_repos import resolve_sync_repos
from ekcip_connectors.jira_jql import resolve_sync_jql
from ekcip_connectors.meetings.reader import list_transcript_files
from ekcip_connectors.meetings.transcript import meeting_documents_from_file
from ekcip_connectors.runtime.confluence import build_confluence_connector
from ekcip_connectors.runtime.github import build_github_connector
from ekcip_connectors.runtime.jira import JiraConnector
from ekcip_connectors.runtime.slack import build_slack_connector
from ekcip_connectors.slack_channels import resolve_sync_channels
from ekcip_graph.intent import classify_graph_intent
from ekcip_knowledge.cache import RedisKnowledgeCache
from ekcip_knowledge.source_intent import infer_live_sources
from ekcip_knowledge.types import RetrievalHit
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

_GITHUB_ISSUE_REF = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$", re.IGNORECASE)
_GITHUB_PR_REF = re.compile(r"^([\w.-]+/[\w.-]+)!(\d+)$", re.IGNORECASE)
_GITHUB_COMMIT_REF = re.compile(r"^([\w.-]+/[\w.-]+)@([a-f0-9]{7,40})$", re.IGNORECASE)


def _document_to_hit(document: dict[str, Any], *, score: float = 1.0) -> RetrievalHit:
    metadata = dict(document.get("metadata") or {})
    metadata["live_fetch"] = True
    return RetrievalHit(
        chunk_id=uuid.uuid4(),
        source=str(document["source"]),
        source_id=str(document["source_id"]),
        title=str(document["title"]),
        content=str(document["content"]),
        url=document.get("url") if isinstance(document.get("url"), str) else None,
        score=score,
        metadata=metadata,
    )


def _build_jira_connector(settings: Settings) -> JiraConnector | None:
    if not settings.jira_configured:
        return None
    return JiraConnector(
        settings.jira_base_url or "",
        settings.jira_email or "",
        settings.jira_api_token or "",
    )


class LiveDataFetcher:
    """Pull Jira, GitHub, Slack, meetings, and Confluence pages live; cache in Redis."""

    def __init__(self, settings: Settings, cache: RedisKnowledgeCache) -> None:
        self._settings = settings
        self._cache = cache
        self._max_results = settings.knowledge_live_fetch_max_results

    async def fetch(
        self,
        question: str,
        *,
        issue_keys: list[str] | None = None,
        page_ids: list[str] | None = None,
        github_ids: list[str] | None = None,
        slack_ids: list[str] | None = None,
        meeting_ids: list[str] | None = None,
        sources: frozenset[str] | None = None,
    ) -> list[RetrievalHit]:
        live_sources = sources or infer_live_sources(
            question,
            issue_keys=issue_keys,
            page_ids=page_ids,
            github_ids=github_ids,
            slack_ids=slack_ids,
            meeting_ids=meeting_ids,
        )
        if not live_sources:
            return []

        cache_key = RedisKnowledgeCache.build_key(
            "live_fetch",
            {
                "sources": sorted(live_sources),
                "question": question,
                "issue_keys": issue_keys or [],
                "page_ids": page_ids or [],
                "github_ids": github_ids or [],
                "slack_ids": slack_ids or [],
                "meeting_ids": meeting_ids or [],
            },
        )
        cached = await self._cache.get_hits(cache_key)
        if cached is not None:
            logger.debug("live_fetch_cache_hit", sources=list(live_sources))
            return cached

        hits: list[RetrievalHit] = []
        if "jira" in live_sources:
            hits.extend(await self._fetch_jira(question, issue_keys or []))
        if "confluence" in live_sources:
            hits.extend(await self._fetch_confluence(page_ids or []))
        if "github" in live_sources:
            hits.extend(await self._fetch_github(github_ids or [], question))
        if "slack" in live_sources:
            hits.extend(await self._fetch_slack(slack_ids or [], question))
        if "meetings" in live_sources:
            hits.extend(await self._fetch_meetings(meeting_ids or [], question))

        await self._cache.set_hits(cache_key, hits)
        logger.info("live_fetch_completed", sources=list(live_sources), hits=len(hits))
        return hits

    async def _fetch_jira(self, question: str, issue_keys: list[str]) -> list[RetrievalHit]:
        jira = _build_jira_connector(self._settings)
        if jira is None:
            return []
        documents: list[dict[str, Any]] = []
        seen: set[str] = set()

        for key in issue_keys:
            try:
                issue = await jira.get_issue(key)
                doc = jira.issue_document(issue)
                if doc["source_id"] not in seen:
                    documents.append(doc)
                    seen.add(doc["source_id"])
            except Exception as exc:
                logger.warning("live_fetch_jira_issue_failed", key=key, error=str(exc)[:200])

        if not documents:
            intent = classify_graph_intent(question, issue_keys=issue_keys)
            jql = self._jira_jql_for_question(question, intent)
            if jql:
                try:
                    issues = await jira.search_issues(jql, max_results=self._max_results)
                    for issue in issues:
                        doc = jira.issue_document(issue)
                        if doc["source_id"] not in seen:
                            documents.append(doc)
                            seen.add(doc["source_id"])
                except Exception as exc:
                    logger.warning("live_fetch_jira_search_failed", error=str(exc)[:200])

        return [_document_to_hit(doc) for doc in documents[: self._max_results]]

    def _jira_jql_for_question(self, question: str, intent: Any) -> str | None:
        if intent.project_keys:
            key = intent.project_keys[0]
            return f'project = "{key}" AND updated >= -90d ORDER BY updated DESC'
        if intent.issue_keys:
            keys = ", ".join(f'"{k}"' for k in intent.issue_keys)
            return f"key in ({keys})"
        safe = question.strip().replace('"', '\\"')[:120]
        if not safe:
            return resolve_sync_jql(None, default=self._settings.jira_sync_jql)
        return f'summary ~ "{safe}*" AND updated >= -90d ORDER BY updated DESC'

    async def _fetch_confluence(self, page_ids: list[str]) -> list[RetrievalHit]:
        confluence = build_confluence_connector(self._settings)
        if confluence is None or not page_ids:
            return []
        hits: list[RetrievalHit] = []
        for page_id in page_ids:
            try:
                page = await confluence.get_page(page_id)
                doc = confluence.page_document(page)
                hits.append(_document_to_hit(doc))
            except Exception as exc:
                logger.warning("live_fetch_confluence_failed", page_id=page_id, error=str(exc)[:200])
        return hits

    async def _fetch_github(self, github_ids: list[str], question: str) -> list[RetrievalHit]:
        github = build_github_connector(self._settings)
        if github is None:
            return []
        documents: list[dict[str, Any]] = []
        seen: set[str] = set()

        for ref in github_ids:
            try:
                doc = await self._github_ref_document(github, ref)
                if doc and doc["source_id"] not in seen:
                    documents.append(doc)
                    seen.add(doc["source_id"])
            except Exception as exc:
                logger.warning("live_fetch_github_ref_failed", ref=ref, error=str(exc)[:200])

        if not documents and self._settings.github_repos.strip():
            repos = resolve_sync_repos(None, default=self._settings.github_repos)
            since = github.since_iso(self._settings.github_sync_days)
            per_repo = max(3, self._max_results // max(len(repos), 1))
            for repo in repos[:5]:
                try:
                    items = await github.list_recent_items(
                        repo, since_iso=since, max_results=per_repo
                    )
                    for item in items:
                        doc = github.item_document(repo, item)
                        if doc["source_id"] not in seen:
                            documents.append(doc)
                            seen.add(doc["source_id"])
                except Exception as exc:
                    logger.warning("live_fetch_github_repo_failed", repo=repo, error=str(exc)[:200])

        return [_document_to_hit(doc) for doc in documents[: self._max_results]]

    async def _github_ref_document(self, github: Any, ref: str) -> dict[str, Any] | None:
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

    async def _fetch_slack(self, slack_ids: list[str], question: str) -> list[RetrievalHit]:
        slack = build_slack_connector(self._settings)
        if slack is None:
            return []
        documents: list[dict[str, Any]] = []
        seen: set[str] = set()

        for slack_ref in slack_ids:
            channel_id, _, message_ts = slack_ref.partition(":")
            if not channel_id or not message_ts:
                continue
            try:
                info = await slack.get_channel_info(channel_id)
                channel_name = str(info.get("name") or channel_id)
                message = await slack.get_message(channel_id, message_ts)
                doc = slack.message_document(channel_id, channel_name, message)
                if doc and doc["source_id"] not in seen:
                    documents.append(doc)
                    seen.add(doc["source_id"])
            except Exception as exc:
                logger.warning("live_fetch_slack_message_failed", ref=slack_ref, error=str(exc)[:200])

        if not documents:
            channel_ids = resolve_sync_channels(None, default=self._settings.slack_channel_ids)
            if not channel_ids:
                joined = await slack.list_joined_channels(limit=10)
                channel_ids = [c["id"] for c in joined]
            oldest = slack.oldest_timestamp(self._settings.slack_sync_days)
            per_channel = max(5, self._max_results // max(len(channel_ids), 1))
            needle = question.lower()
            for channel_id in channel_ids[:5]:
                try:
                    info = await slack.get_channel_info(channel_id)
                    channel_name = str(info.get("name") or channel_id)
                    messages = await slack.fetch_channel_messages(
                        channel_id,
                        oldest=oldest,
                        max_messages=per_channel,
                    )
                    for message in messages:
                        doc = slack.message_document(channel_id, channel_name, message)
                        if not doc or doc["source_id"] in seen:
                            continue
                        if needle and needle not in doc["content"].lower():
                            continue
                        documents.append(doc)
                        seen.add(doc["source_id"])
                except Exception as exc:
                    logger.warning(
                        "live_fetch_slack_channel_failed",
                        channel_id=channel_id,
                        error=str(exc)[:200],
                    )

        return [_document_to_hit(doc) for doc in documents[: self._max_results]]

    async def _fetch_meetings(self, meeting_ids: list[str], question: str) -> list[RetrievalHit]:
        raw_dir = self._settings.meetings_transcripts_dir.strip()
        if not raw_dir:
            return []
        directory = Path(raw_dir).expanduser()
        if not directory.is_dir():
            return []

        paths = list_transcript_files(
            directory,
            days=self._settings.meetings_sync_days,
            max_files=self._settings.meetings_max_files,
        )
        wanted = {mid.lower() for mid in meeting_ids}
        needle = question.lower()
        hits: list[RetrievalHit] = []
        seen: set[str] = set()

        for path in paths:
            stem = path.stem.lower()
            if wanted and not any(w in stem or stem in w for w in wanted):
                continue
            try:
                for document in meeting_documents_from_file(
                    path, max_chars=self._settings.meetings_chunk_max_chars
                ):
                    if document["source_id"] in seen:
                        continue
                    if wanted or (needle and needle in document["content"].lower()):
                        hits.append(_document_to_hit(document))
                        seen.add(document["source_id"])
            except Exception as exc:
                logger.warning("live_fetch_meeting_failed", file=path.name, error=str(exc)[:200])

        return hits[: self._max_results]
