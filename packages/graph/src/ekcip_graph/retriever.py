"""Neo4j Cypher retrieval for relationship-aware Q&A (Phase 3)."""

from typing import Any

from ekcip_graph.client import create_neo4j_driver
from ekcip_graph.intent import GraphIntent
from ekcip_graph.types import GraphRetrievalResult, GraphSnippet
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

_ISSUE_DETAIL_CYPHER = """
MATCH (i:Issue {key: $issue_key})
OPTIONAL MATCH (person:Person)-[:ASSIGNED_TO]->(i)
OPTIONAL MATCH (p:Project)-[:CONTAINS]->(i)
RETURN i.key AS issue_key, i.title AS title, i.status AS status,
       p.key AS project_key, person.name AS assignee_name
LIMIT 1
"""

_PROJECT_ISSUES_CYPHER = """
MATCH (p:Project {key: $project_key})-[:CONTAINS]->(i:Issue)
OPTIONAL MATCH (person:Person)-[:ASSIGNED_TO]->(i)
RETURN i.key AS issue_key, i.title AS title, i.status AS status,
       person.name AS assignee_name
ORDER BY i.key
LIMIT $limit
"""

_BLOCKERS_CYPHER = """
MATCH (p:Project)-[:CONTAINS]->(i:Issue)
WHERE ($project_key IS NULL OR p.key = $project_key)
  AND (
    toLower(i.status) CONTAINS 'block'
    OR toLower(coalesce(i.title, '')) CONTAINS 'block'
  )
OPTIONAL MATCH (person:Person)-[:ASSIGNED_TO]->(i)
RETURN p.key AS project_key, i.key AS issue_key, i.title AS title,
       i.status AS status, person.name AS assignee_name
ORDER BY i.key
LIMIT $limit
"""

_RECENT_ISSUES_CYPHER = """
MATCH (p:Project)-[:CONTAINS]->(i:Issue)
OPTIONAL MATCH (person:Person)-[:ASSIGNED_TO]->(i)
RETURN p.key AS project_key, i.key AS issue_key, i.title AS title,
       i.status AS status, person.name AS assignee_name
ORDER BY i.key
LIMIT $limit
"""

_NODE_COUNT_CYPHER = "MATCH (n) RETURN count(n) AS node_count"


def format_graph_context(result: GraphRetrievalResult) -> str:
    if not result.snippets:
        return (
            "No graph relationships matched this question. "
            "Run POST /v1/admin/seed or sync Jira/Confluence to populate Neo4j."
        )
    lines = [
        f"Graph context (modes: {', '.join(result.query_modes) or 'none'})",
    ]
    if result.node_count is not None:
        lines.append(f"Neo4j nodes indexed: {result.node_count}")
    for index, snippet in enumerate(result.snippets, start=1):
        ids = ", ".join(snippet.source_ids) if snippet.source_ids else "n/a"
        lines.append(f"[G{index}] {snippet.label} ({snippet.kind}) — {ids}\n{snippet.detail}")
    return "\n\n".join(lines)


class GraphRetriever:
    """Runs parameterized Cypher templates against the enterprise graph."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def retrieve(
        self,
        intent: GraphIntent,
        *,
        limit: int = 25,
    ) -> GraphRetrievalResult:
        if not self._settings.neo4j_configured or not intent.use_graph:
            return GraphRetrievalResult(snippets=(), query_modes=())

        snippets: list[GraphSnippet] = []
        modes: list[str] = []
        driver = create_neo4j_driver(self._settings)
        try:
            async with driver.session(database=self._settings.neo4j_database) as session:
                node_count = await self._fetch_node_count(session)

                for issue_key in intent.issue_keys:
                    rows = await self._run(session, _ISSUE_DETAIL_CYPHER, issue_key=issue_key)
                    if rows:
                        modes.append("local_issue")
                        snippets.append(_issue_snippet(rows[0]))

                for project_key in intent.project_keys:
                    rows = await self._run(
                        session,
                        _PROJECT_ISSUES_CYPHER,
                        project_key=project_key,
                        limit=limit,
                    )
                    if rows:
                        modes.append("project_overview")
                        snippets.append(_project_snippet(project_key, rows))

                if intent.wants_project_overview and not intent.project_keys and not intent.issue_keys:
                    rows = await self._run(session, _RECENT_ISSUES_CYPHER, limit=limit)
                    if rows:
                        modes.append("global_overview")
                        snippets.append(_global_snippet(rows))

                if intent.wants_blockers or (
                    intent.wants_project_overview and not intent.project_keys and not snippets
                ):
                    project_filter = intent.project_keys[0] if len(intent.project_keys) == 1 else None
                    rows = await self._run(
                        session,
                        _BLOCKERS_CYPHER,
                        project_key=project_filter,
                        limit=limit,
                    )
                    if rows:
                        modes.append("blocker_scan")
                        snippets.append(_blocker_snippet(rows))

                if intent.wants_assignee and intent.issue_keys:
                    pass
        except Exception as exc:
            logger.warning("graph_retrieve_failed", error=str(exc)[:300])
            return GraphRetrievalResult(snippets=(), query_modes=("error",))
        finally:
            await driver.close()

        deduped = _dedupe_snippets(snippets)
        return GraphRetrievalResult(
            snippets=tuple(deduped),
            query_modes=tuple(dict.fromkeys(modes)),
            node_count=node_count,
        )

    async def _fetch_node_count(self, session: Any) -> int | None:
        try:
            result = await session.run(_NODE_COUNT_CYPHER)
            record = await result.single()
            if record:
                return int(record.get("node_count", 0))
        except Exception:
            return None
        return None

    async def _run(self, session: Any, cypher: str, **params: Any) -> list[dict[str, Any]]:
        result = await session.run(cypher, **params)
        records = await result.data()
        return list(records)


def _issue_snippet(row: dict[str, Any]) -> GraphSnippet:
    key = str(row.get("issue_key", ""))
    assignee = row.get("assignee_name") or "Unassigned"
    status = row.get("status") or "unknown"
    title = row.get("title") or key
    project = row.get("project_key") or ""
    detail = (
        f"Issue {key} ({title}) in project {project}: status={status}, assignee={assignee}."
    )
    return GraphSnippet(
        kind="issue",
        label=f"Jira {key}",
        detail=detail,
        source_ids=(key,),
    )


def _project_snippet(project_key: str, rows: list[dict[str, Any]]) -> GraphSnippet:
    lines: list[str] = []
    keys: list[str] = []
    for row in rows[:15]:
        key = str(row.get("issue_key", ""))
        if key:
            keys.append(key)
        assignee = row.get("assignee_name") or "Unassigned"
        status = row.get("status") or "unknown"
        title = row.get("title") or key
        lines.append(f"- {key}: {title} [{status}] → {assignee}")
    extra = ""
    if len(rows) > 15:
        extra = f"\n... and {len(rows) - 15} more issues in project {project_key}."
    detail = f"Project {project_key} — {len(rows)} indexed issue(s):\n" + "\n".join(lines) + extra
    return GraphSnippet(
        kind="project",
        label=f"Project {project_key}",
        detail=detail,
        source_ids=tuple(keys),
    )


def _global_snippet(rows: list[dict[str, Any]]) -> GraphSnippet:
    lines: list[str] = []
    keys: list[str] = []
    for row in rows[:20]:
        key = str(row.get("issue_key", ""))
        if key:
            keys.append(key)
        project = row.get("project_key") or ""
        assignee = row.get("assignee_name") or "Unassigned"
        status = row.get("status") or "unknown"
        title = row.get("title") or key
        lines.append(f"- {key} ({project}): {title} [{status}] → {assignee}")
    detail = f"Indexed work across projects ({len(rows)} issues):\n" + "\n".join(lines)
    return GraphSnippet(
        kind="overview",
        label="Enterprise issue overview",
        detail=detail,
        source_ids=tuple(keys),
    )


def _blocker_snippet(rows: list[dict[str, Any]]) -> GraphSnippet:
    lines: list[str] = []
    keys: list[str] = []
    for row in rows[:15]:
        key = str(row.get("issue_key", ""))
        if key:
            keys.append(key)
        project = row.get("project_key") or ""
        assignee = row.get("assignee_name") or "Unassigned"
        status = row.get("status") or "unknown"
        title = row.get("title") or key
        lines.append(f"- {key} ({project}): {title} [{status}] → {assignee}")
    detail = f"Potential blockers ({len(rows)}):\n" + "\n".join(lines)
    return GraphSnippet(
        kind="blockers",
        label="Blocker scan",
        detail=detail,
        source_ids=tuple(keys),
    )


def _dedupe_snippets(snippets: list[GraphSnippet]) -> list[GraphSnippet]:
    seen: set[str] = set()
    out: list[GraphSnippet] = []
    for snippet in snippets:
        key = f"{snippet.kind}:{snippet.label}"
        if key in seen:
            continue
        seen.add(key)
        out.append(snippet)
    return out
