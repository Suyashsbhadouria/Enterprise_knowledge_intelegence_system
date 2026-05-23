"""Bounded JQL helpers for Jira Cloud (unbounded queries return HTTP 400)."""

import re

_UNBOUNDED_ONLY = re.compile(
    r"^\s*order\s+by\s+",
    re.IGNORECASE,
)


def is_likely_unbounded(jql: str) -> bool:
    normalized = jql.strip()
    if not normalized:
        return True
    if _UNBOUNDED_ONLY.match(normalized):
        return True
    lowered = normalized.lower()
    has_restriction = any(
        token in lowered
        for token in (
            "project ",
            "project=",
            "updated ",
            "updated>",
            "updated>=",
            "created ",
            "created>",
            "created>=",
            "assignee ",
            "assignee=",
            "status ",
            "status=",
            "key ",
            "key=",
            "issuekey ",
            "parent ",
        )
    )
    return not has_restriction


def bounded_jql_for_project(project_key: str, *, days: int = 90) -> str:
    return f'project = "{project_key}" AND updated >= -{days}d ORDER BY updated DESC'


def bounded_jql_recent(*, days: int = 90) -> str:
    return f"updated >= -{days}d ORDER BY updated DESC"


def resolve_sync_jql(
    requested: str | None,
    *,
    default: str,
    project_key: str | None = None,
) -> str:
    """Pick a Jira-safe JQL string."""
    jql = (requested or default).strip()
    if project_key:
        return bounded_jql_for_project(project_key)
    if is_likely_unbounded(jql):
        return bounded_jql_recent()
    return jql
