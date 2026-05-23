from ekcip_connectors.runtime.confluence import ConfluenceConnector
from ekcip_knowledge.embeddings import EmbeddingError, EmbeddingRouter
from ekcip_knowledge.store import KnowledgeStore
from ekcip_knowledge.types import KnowledgeChunkRecord
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


async def sync_confluence_pages(
    store: KnowledgeStore,
    confluence: ConfluenceConnector,
    embedding_router: EmbeddingRouter,
    *,
    cql: str,
    max_results: int,
    pages: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    run_id = await store.start_sync_run("confluence")
    indexed = 0
    indexed_pages: list[dict[str, str]] = []
    try:
        page_list = pages if pages is not None else await confluence.search_pages(cql, max_results=max_results)
        for page in page_list:
            document = confluence.page_document(page)
            if not document.get("source_id"):
                continue
            try:
                embedding, provider = await embedding_router.embed(document["content"])
            except EmbeddingError as exc:
                raise RuntimeError(f"Embedding failed ({exc.provider}): {exc}") from exc
            record = KnowledgeChunkRecord(
                source=document["source"],
                source_id=document["source_id"],
                title=document["title"],
                content=document["content"],
                url=document.get("url"),
                metadata={**document.get("metadata", {}), "embedding_provider": provider},
            )
            await store.upsert_chunk(record, embedding)
            indexed += 1
            indexed_pages.append(
                {
                    "page_id": str(document["source_id"]),
                    "title": str(document["title"]),
                    "space_key": str((document.get("metadata") or {}).get("space_key", "")),
                }
            )
        await store.finish_sync_run(run_id, status="completed", issues_indexed=indexed)
        logger.info("confluence_sync_completed", pages_indexed=indexed, cql=cql)
        return {
            "status": "completed",
            "pages_indexed": indexed,
            "pages": indexed_pages,
            "run_id": str(run_id),
        }
    except Exception as exc:
        await store.finish_sync_run(
            run_id,
            status="failed",
            issues_indexed=indexed,
            detail=str(exc)[:1000],
        )
        logger.error("confluence_sync_failed", error=str(exc), pages_indexed=indexed)
        raise
