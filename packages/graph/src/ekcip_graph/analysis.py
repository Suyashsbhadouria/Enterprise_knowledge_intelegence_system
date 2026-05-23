"""Coordination analysis over graph + vector context (Phase 3)."""

from ekcip_graph.types import GraphRetrievalResult, GraphSnippet
from ekcip_knowledge.types import RetrievalHit


def detect_blockers(
    *,
    graph: GraphRetrievalResult,
    hits: list[RetrievalHit],
) -> str | None:
    """Summarize blockers from graph scan and Jira chunk metadata."""
    lines: list[str] = []

    for snippet in graph.snippets:
        if snippet.kind == "blockers":
            lines.append(snippet.detail)

    for hit in hits:
        status = str((hit.metadata or {}).get("status", "")).lower()
        title = hit.title.lower()
        if "block" in status or "block" in title:
            assignee = (hit.metadata or {}).get("assignee", "Unassigned")
            lines.append(
                f"- {hit.source_id}: {hit.title} [{(hit.metadata or {}).get('status', '')}] "
                f"→ {assignee}"
            )

    if not lines:
        return None

    unique = list(dict.fromkeys(lines))
    return "Blocker analysis (from graph + indexed Jira):\n" + "\n".join(unique[:20])


def merge_context_sections(
    *,
    vector_context: str,
    graph_context: str,
    analysis: str | None,
) -> str:
    sections = [
        "## Vector knowledge (Jira + Confluence chunks)",
        vector_context,
        "## Graph relationships (Neo4j)",
        graph_context,
    ]
    if analysis:
        sections.extend(["## Coordination analysis", analysis])
    return "\n\n".join(sections)
