from ekcip_knowledge.cache import RedisKnowledgeCache
from ekcip_knowledge.embeddings import EmbeddingRouter
from ekcip_knowledge.live_fetch import LiveDataFetcher
from ekcip_knowledge.source_intent import infer_live_sources, parse_vector_sources
from ekcip_knowledge.store import KnowledgeStore
from ekcip_knowledge.types import Citation, RetrievalHit
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

DEFAULT_KNOWLEDGE_SOURCES = ("jira", "confluence", "github", "slack", "meetings")


class KnowledgeRetriever:
    """
    Confluence-only vector search (Postgres embeddings) plus live connector fetches
    for Jira, GitHub, Slack, and meetings. Live results are Redis-cached briefly.
    """

    def __init__(
        self,
        store: KnowledgeStore,
        embedding_router: EmbeddingRouter,
        *,
        settings: Settings,
        live_fetcher: LiveDataFetcher | None = None,
    ) -> None:
        self._store = store
        self._embedding_router = embedding_router
        self._settings = settings
        self._live_fetcher = live_fetcher
        self._vector_sources = parse_vector_sources(settings.knowledge_vector_sources)
        self._top_k = settings.knowledge_top_k

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
        top_k: int | None = None,
    ) -> tuple[list[RetrievalHit], list[Citation]]:
        limit = top_k or self._top_k
        live_sources = infer_live_sources(
            query,
            issue_keys=issue_keys,
            page_ids=page_ids,
            github_ids=github_ids,
            slack_ids=slack_ids,
            meeting_ids=meeting_ids,
        )
        if sources:
            live_sources = frozenset(s for s in sources if s in live_sources)

        hits: list[RetrievalHit] = []

        if self._live_fetcher is not None and live_sources:
            try:
                live_hits = await self._live_fetcher.fetch(
                    query,
                    issue_keys=issue_keys,
                    page_ids=page_ids,
                    github_ids=github_ids,
                    slack_ids=slack_ids,
                    meeting_ids=meeting_ids,
                    sources=live_sources,
                )
                hits.extend(live_hits)
            except Exception as exc:
                logger.warning("live_fetch_failed", error=str(exc)[:300])

        vector_sources = [s for s in self._vector_sources if not sources or s in sources]
        if vector_sources:
            try:
                query_embedding, _ = await self._embedding_router.embed(query)
                vector_hits = await self._store.search(
                    query_embedding,
                    sources=list(vector_sources),
                    top_k=limit,
                )
                hits.extend(vector_hits)
            except Exception as exc:
                logger.warning("vector_search_failed", error=str(exc)[:300])

        seen: set[str] = set()
        merged: list[RetrievalHit] = []
        for hit in hits:
            key = f"{hit.source}:{hit.source_id}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(hit)
        merged.sort(key=lambda h: h.score, reverse=True)
        merged = merged[:limit]

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
