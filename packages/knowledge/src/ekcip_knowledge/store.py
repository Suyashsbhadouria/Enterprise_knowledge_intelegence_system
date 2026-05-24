import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ekcip_knowledge.embeddings import cosine_similarity
from ekcip_knowledge.models import KnowledgeChunk, KnowledgeSyncRun
from ekcip_knowledge.types import KnowledgeChunkRecord, RetrievalHit


class KnowledgeStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_chunk(self, record: KnowledgeChunkRecord, embedding: list[float]) -> uuid.UUID:
        await self._session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.source == record.source,
                KnowledgeChunk.source_id == record.source_id,
                KnowledgeChunk.chunk_index == record.chunk_index,
            )
        )
        chunk = KnowledgeChunk(
            source=record.source,
            source_id=record.source_id,
            chunk_index=record.chunk_index,
            title=record.title,
            content=record.content,
            url=record.url,
            metadata_json=record.metadata,
            embedding_json=embedding,
            indexed_at=datetime.now(timezone.utc),
        )
        self._session.add(chunk)
        await self._session.flush()
        return chunk.id

    async def delete_chunks_for_sources(self, sources: list[str]) -> int:
        if not sources:
            return 0
        result = await self._session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.source.in_(sources))
        )
        return int(result.rowcount or 0)

    async def count_chunks(self, source: str | None = None) -> int:
        query = select(func.count()).select_from(KnowledgeChunk)
        if source:
            query = query.where(KnowledgeChunk.source == source)
        result = await self._session.execute(query)
        return int(result.scalar_one())

    async def count_distinct_source_ids(self, source: str) -> int:
        result = await self._session.execute(
            select(func.count(func.distinct(KnowledgeChunk.source_id))).where(
                KnowledgeChunk.source == source
            )
        )
        return int(result.scalar_one())

    async def search(
        self,
        query_embedding: list[float],
        *,
        source: str | None = "jira",
        sources: list[str] | None = None,
        top_k: int = 5,
    ) -> list[RetrievalHit]:
        query = select(KnowledgeChunk)
        if sources:
            query = query.where(KnowledgeChunk.source.in_(sources))
        elif source:
            query = query.where(KnowledgeChunk.source == source)
        result = await self._session.execute(query)
        rows = list(result.scalars().all())
        scored: list[tuple[float, KnowledgeChunk]] = []
        for row in rows:
            score = cosine_similarity(query_embedding, row.embedding_json)
            scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        hits: list[RetrievalHit] = []
        for score, row in scored[:top_k]:
            if score <= 0:
                continue
            hits.append(
                RetrievalHit(
                    chunk_id=row.id,
                    source=row.source,
                    source_id=row.source_id,
                    title=row.title,
                    content=row.content,
                    url=row.url,
                    score=score,
                    metadata=dict(row.metadata_json or {}),
                )
            )
        return hits

    async def search_by_title_substring(
        self,
        source: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[RetrievalHit]:
        if not query.strip():
            return []
        pattern = f"%{query.strip()}%"
        result = await self._session.execute(
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.source == source,
                KnowledgeChunk.title.ilike(pattern),
            )
            .limit(limit * 3)
        )
        rows = list(result.scalars().all())
        seen: set[str] = set()
        hits: list[RetrievalHit] = []
        for row in rows:
            if row.source_id in seen:
                continue
            seen.add(row.source_id)
            hits.append(
                RetrievalHit(
                    chunk_id=row.id,
                    source=row.source,
                    source_id=row.source_id,
                    title=row.title,
                    content=row.content,
                    url=row.url,
                    score=1.0,
                    metadata=dict(row.metadata_json or {}),
                )
            )
            if len(hits) >= limit:
                break
        return hits

    async def get_by_source_ids(self, source: str, source_ids: list[str]) -> list[RetrievalHit]:
        if not source_ids:
            return []
        result = await self._session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.source == source,
                KnowledgeChunk.source_id.in_(source_ids),
            )
        )
        rows = list(result.scalars().all())
        return [
            RetrievalHit(
                chunk_id=row.id,
                source=row.source,
                source_id=row.source_id,
                title=row.title,
                content=row.content,
                url=row.url,
                score=1.0,
                metadata=dict(row.metadata_json or {}),
            )
            for row in rows
        ]

    async def start_sync_run(self, source: str) -> uuid.UUID:
        run = KnowledgeSyncRun(
            source=source,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self._session.add(run)
        await self._session.flush()
        return run.id

    async def finish_sync_run(
        self,
        run_id: uuid.UUID,
        *,
        status: str,
        issues_indexed: int,
        detail: str | None = None,
    ) -> None:
        result = await self._session.execute(
            select(KnowledgeSyncRun).where(KnowledgeSyncRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return
        run.status = status
        run.issues_indexed = issues_indexed
        run.detail = detail
        run.finished_at = datetime.now(timezone.utc)
