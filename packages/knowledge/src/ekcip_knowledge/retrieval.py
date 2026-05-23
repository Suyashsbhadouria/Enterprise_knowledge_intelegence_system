from ekcip_knowledge.embeddings import EmbeddingRouter
from ekcip_knowledge.store import KnowledgeStore
from ekcip_knowledge.types import Citation, RetrievalHit

DEFAULT_KNOWLEDGE_SOURCES = ("jira", "confluence", "github", "slack")


class KnowledgeRetriever:
    def __init__(self, store: KnowledgeStore, embedding_router: EmbeddingRouter) -> None:
        self._store = store
        self._embedding_router = embedding_router

    async def retrieve(
        self,
        query: str,
        *,
        issue_keys: list[str] | None = None,
        page_ids: list[str] | None = None,
        github_ids: list[str] | None = None,
        slack_ids: list[str] | None = None,
        sources: list[str] | None = None,
        top_k: int = 5,
    ) -> tuple[list[RetrievalHit], list[Citation]]:
        active_sources = list(sources or DEFAULT_KNOWLEDGE_SOURCES)
        hits: list[RetrievalHit] = []
        if issue_keys and "jira" in active_sources:
            direct = await self._store.get_by_source_ids("jira", issue_keys)
            hits.extend(direct)
        if page_ids and "confluence" in active_sources:
            direct_pages = await self._store.get_by_source_ids("confluence", page_ids)
            hits.extend(direct_pages)
        if github_ids and "github" in active_sources:
            direct_github = await self._store.get_by_source_ids("github", github_ids)
            hits.extend(direct_github)
        if slack_ids and "slack" in active_sources:
            direct_slack = await self._store.get_by_source_ids("slack", slack_ids)
            hits.extend(direct_slack)

        try:
            query_embedding, _ = await self._embedding_router.embed(query)
            vector_hits = await self._store.search(
                query_embedding,
                sources=active_sources,
                top_k=top_k,
            )
        except Exception:
            vector_hits = []

        seen: set[str] = set()
        merged: list[RetrievalHit] = []
        for hit in hits + vector_hits:
            key = f"{hit.source}:{hit.source_id}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(hit)
        merged = merged[:top_k]

        citations = [
            Citation(
                source=hit.source,
                source_id=hit.source_id,
                title=hit.title,
                url=hit.url,
                excerpt=hit.content[:500],
                score=hit.score,
            )
            for hit in merged
        ]
        return merged, citations
