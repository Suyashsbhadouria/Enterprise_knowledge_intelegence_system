"""Bounded CQL helpers for Confluence Cloud (avoid unbounded space-wide scans)."""

import re

_UNBOUNDED_ONLY = re.compile(
    r"^\s*type\s*=\s*page\s+order\s+by\s+",
    re.IGNORECASE,
)


def is_likely_unbounded(cql: str) -> bool:
    normalized = cql.strip()
    if not normalized:
        return True
    if _UNBOUNDED_ONLY.match(normalized):
        return True
    lowered = normalized.lower()
    has_restriction = any(
        token in lowered
        for token in (
            "lastmodified ",
            "lastmodified>=",
            "lastmodified>",
            "created ",
            "created>=",
            "created>",
            "space ",
            "space=",
            "ancestor ",
            "ancestor=",
            "id ",
            "id=",
            "title ",
            "title~",
            "label ",
            "label=",
        )
    )
    return not has_restriction


def bounded_cql_recent(*, days: int = 90) -> str:
    return f'type=page AND lastModified >= now("-{days}d") order by lastModified desc'


def bounded_cql_for_space(space_key: str, *, days: int = 90) -> str:
    return (
        f'type=page AND space = "{space_key}" '
        f'AND lastModified >= now("-{days}d") order by lastModified desc'
    )


def resolve_sync_cql(
    requested: str | None,
    *,
    default: str,
    space_key: str | None = None,
) -> str:
    cql = (requested or default).strip()
    if space_key:
        return bounded_cql_for_space(space_key)
    if is_likely_unbounded(cql):
        return bounded_cql_recent()
    return cql
