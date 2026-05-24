from pathlib import Path

from ekcip_connectors.meetings.reader import list_transcript_files
from ekcip_connectors.meetings.transcript import meeting_documents_from_file
from ekcip_knowledge.embeddings import EmbeddingError, EmbeddingRouter
from ekcip_knowledge.store import KnowledgeStore
from ekcip_knowledge.types import KnowledgeChunkRecord
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


def resolve_meetings_directory(settings: Settings, override: str | None = None) -> Path | None:
    raw = (override or settings.meetings_transcripts_dir or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        return None
    return path


async def sync_meeting_transcripts(
    store: KnowledgeStore,
    embedding_router: EmbeddingRouter,
    *,
    directory: Path,
    days: int,
    max_files: int,
    max_chars: int = 2000,
    files: list[Path] | None = None,
) -> dict[str, object]:
    run_id = await store.start_sync_run("meetings")
    indexed = 0
    indexed_transcripts: list[dict[str, str]] = []
    transcript_paths = files if files is not None else list_transcript_files(
        directory,
        days=days,
        max_files=max_files,
    )
    try:
        for path in transcript_paths:
            documents = meeting_documents_from_file(path, max_chars=max_chars)
            if not documents:
                continue
            for document in documents:
                try:
                    embedding, provider = await embedding_router.embed(document["content"])
                except EmbeddingError as exc:
                    raise RuntimeError(f"Embedding failed ({exc.provider}): {exc}") from exc
                record = KnowledgeChunkRecord(
                    source=document["source"],
                    source_id=document["source_id"],
                    chunk_index=int(document["metadata"].get("chunk_index", 0)),
                    title=document["title"],
                    content=document["content"],
                    url=document.get("url"),
                    metadata={**document.get("metadata", {}), "embedding_provider": provider},
                )
                await store.upsert_chunk(record, embedding)
                indexed += 1
            indexed_transcripts.append(
                {
                    "meeting_id": str(documents[0]["metadata"]["meeting_id"]),
                    "filename": path.name,
                    "chunks": str(len(documents)),
                }
            )
        await store.finish_sync_run(run_id, status="completed", issues_indexed=indexed)
        logger.info(
            "meetings_sync_completed",
            transcripts_indexed=len(indexed_transcripts),
            chunks_indexed=indexed,
            directory=str(directory),
        )
        return {
            "status": "completed",
            "transcripts_indexed": len(indexed_transcripts),
            "chunks_indexed": indexed,
            "transcripts": indexed_transcripts,
            "directory": str(directory),
            "run_id": str(run_id),
        }
    except Exception as exc:
        await store.finish_sync_run(
            run_id,
            status="failed",
            issues_indexed=indexed,
            detail=str(exc)[:1000],
        )
        logger.error("meetings_sync_failed", error=str(exc), chunks_indexed=indexed)
        raise
