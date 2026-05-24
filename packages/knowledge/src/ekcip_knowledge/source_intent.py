"""Infer which live connectors to query for a user question."""

from __future__ import annotations

import re

from ekcip_graph.intent import classify_graph_intent

CONFLUENCE_KEYWORDS = re.compile(r"\b(confluence|wiki|runbook|documentation)\b", re.IGNORECASE)
GITHUB_KEYWORDS = re.compile(
    r"\b(github|pull request|merge request|commit|repository|repo)\b",
    re.IGNORECASE,
)
SLACK_KEYWORDS = re.compile(r"\b(slack|channel|thread|posted in)\b", re.IGNORECASE)
MEETING_KEYWORDS = re.compile(
    r"\b(meeting|transcript|standup|retro|sync call|workshop)\b",
    re.IGNORECASE,
)

LIVE_SOURCES = frozenset({"jira", "confluence", "github", "slack", "meetings"})


def parse_vector_sources(raw: str) -> tuple[str, ...]:
    """Sources stored in the knowledge index (embeddings). Default: confluence only."""
    items = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return items or ("confluence",)


def infer_live_sources(
    question: str,
    *,
    issue_keys: list[str] | None = None,
    page_ids: list[str] | None = None,
    github_ids: list[str] | None = None,
    slack_ids: list[str] | None = None,
    meeting_ids: list[str] | None = None,
) -> frozenset[str]:
    """Return connector sources to fetch live for this question (not vector index)."""
    sources: set[str] = set()
    keys = list(issue_keys or [])
    graph_intent = classify_graph_intent(question, issue_keys=keys)

    if keys or graph_intent.issue_keys or graph_intent.project_keys:
        sources.add("jira")
    if graph_intent.wants_blockers or graph_intent.wants_assignee or graph_intent.wants_project_overview:
        sources.add("jira")

    if page_ids or CONFLUENCE_KEYWORDS.search(question):
        sources.add("confluence")

    if github_ids or GITHUB_KEYWORDS.search(question):
        sources.add("github")

    if slack_ids or SLACK_KEYWORDS.search(question):
        sources.add("slack")

    if meeting_ids or MEETING_KEYWORDS.search(question):
        sources.add("meetings")

    return frozenset(source for source in sources if source in LIVE_SOURCES)
