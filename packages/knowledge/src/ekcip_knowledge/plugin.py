"""Semantic Kernel–style knowledge plugin (plain Python, Phase 1)."""

from ekcip_knowledge.retrieval import KnowledgeRetriever
from ekcip_knowledge.types import Citation, RetrievalHit


class KnowledgePlugin:
    """Wraps retrieval and formats cited context for the LLM."""

    def __init__(self, retriever: KnowledgeRetriever) -> None:
        self._retriever = retriever

    async def retrieve(
        self,
        query: str,
        *,
        issue_keys: list[str] | None = None,
        page_ids: list[str] | None = None,
        github_ids: list[str] | None = None,
        slack_ids: list[str] | None = None,
        meeting_ids: list[str] | None = None,
        sources: list[str] | None = None,
        top_k: int = 5,
    ) -> tuple[list[RetrievalHit], list[Citation]]:
        return await self._retriever.retrieve(
            query,
            issue_keys=issue_keys,
            page_ids=page_ids,
            github_ids=github_ids,
            slack_ids=slack_ids,
            meeting_ids=meeting_ids,
            sources=sources,
            top_k=top_k,
        )

    @staticmethod
    def format_context(hits: list[RetrievalHit], citations: list[Citation]) -> str:
        if not hits:
            return (
                "No knowledge matched this question from live sources or indexed Confluence pages. "
                "Verify connector credentials, mention specific issue keys or pages with @, "
                "or sync Confluence documentation for semantic search."
            )
        sections: list[str] = []
        for index, hit in enumerate(hits, start=1):
            cite = next((c for c in citations if c.source_id == hit.source_id), None)
            label = cite.title if cite else hit.title
            sections.append(
                f"[{index}] {hit.source_id} — {label}\n"
                f"URL: {hit.url or 'n/a'}\n"
                f"{hit.content[:4000]}"
            )
        return "\n\n---\n\n".join(sections)

    @staticmethod
    def format_citations_footer(citations: list[Citation]) -> str:
        if not citations:
            return ""
        lines = ["\n\n**Sources:**"]
        for cite in citations:
            link = f" ({cite.url})" if cite.url else ""
            lines.append(f"- [{cite.source_id}] {cite.title}{link}")
        return "\n".join(lines)
