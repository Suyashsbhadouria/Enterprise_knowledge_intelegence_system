"""Seed interconnected Nexus Dynamics fixture data (Jira, Confluence, Slack, meetings)."""

from pathlib import Path

from ekcip_connectors.fixtures.enterprise_catalog import (
    ENTERPRISE_MANIFEST,
    build_confluence_documents,
    build_jira_documents,
    build_meeting_transcript_files,
    build_slack_message_batches,
    build_test_queries,
)
from ekcip_connectors.meetings.transcript import meeting_documents_from_file
from ekcip_connectors.runtime.slack import SlackConnector
from ekcip_graph.enterprise_seed import seed_neo4j_from_enterprise_data
from ekcip_knowledge.embeddings import EmbeddingError, EmbeddingRouter, build_embedding_router
from ekcip_knowledge.store import KnowledgeStore
from ekcip_knowledge.types import KnowledgeChunkRecord
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

_FIXTURE_SOURCES = ("jira", "confluence", "slack", "meetings")
_SLACK_FIXTURE = SlackConnector("xoxb-enterprise-fixture")


async def _index_documents(
    store: KnowledgeStore,
    embedding_router: EmbeddingRouter,
    documents: list[dict[str, object]],
    *,
    source_label: str,
) -> int:
    run_id = await store.start_sync_run(source_label)
    indexed = 0
    try:
        for document in documents:
            content = str(document.get("content") or "")
            if not content.strip():
                continue
            try:
                embedding, provider = await embedding_router.embed(content)
            except EmbeddingError as exc:
                raise RuntimeError(f"Embedding failed ({exc.provider}): {exc}") from exc
            metadata = dict(document.get("metadata") or {})
            metadata["embedding_provider"] = provider
            record = KnowledgeChunkRecord(
                source=str(document["source"]),
                source_id=str(document["source_id"]),
                chunk_index=int(metadata.get("chunk_index", 0)),
                title=str(document.get("title") or document["source_id"]),
                content=content,
                url=document.get("url"),
                metadata=metadata,
            )
            await store.upsert_chunk(record, embedding)
            indexed += 1
        await store.finish_sync_run(run_id, status="completed", issues_indexed=indexed)
        return indexed
    except Exception as exc:
        await store.finish_sync_run(
            run_id,
            status="failed",
            issues_indexed=indexed,
            detail=str(exc)[:1000],
        )
        raise


async def seed_enterprise_fixture(
    session: AsyncSession,
    settings: Settings,
    *,
    clear_existing: bool = True,
    meetings_dir: Path | None = None,
) -> dict[str, object]:
    """
    Index synthetic Nexus Dynamics data into Postgres knowledge chunks and Neo4j.
    Does not call live Jira, Confluence, Slack, or GitHub APIs.
    """
    embedding_router = build_embedding_router(settings)
    if not embedding_router.configured_providers():
        return {
            "status": "failed",
            "reason": "no_embedding_provider",
            "hint": "Enable LOCAL_EMBEDDINGS_ENABLED or set a cloud embedding API key.",
        }

    store = KnowledgeStore(session)
    if clear_existing:
        cleared = await store.delete_chunks_for_sources(list(_FIXTURE_SOURCES))
        logger.info("enterprise_fixture_cleared_chunks", count=cleared)

    jira_documents = build_jira_documents()
    confluence_documents = build_confluence_documents()
    slack_batches = build_slack_message_batches()

    slack_documents: list[dict[str, object]] = []
    for channel_id, channel_name, message in slack_batches:
        document = _SLACK_FIXTURE.message_document(channel_id, channel_name, message)
        if document:
            slack_documents.append(document)

    target_dir = meetings_dir or Path(settings.meetings_transcripts_dir or "./data/meetings")
    target_dir = target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    meeting_documents: list[dict[str, object]] = []
    for filename, content in build_meeting_transcript_files():
        path = target_dir / filename
        path.write_text(content, encoding="utf-8")
        meeting_documents.extend(meeting_documents_from_file(path))

    jira_indexed = await _index_documents(store, embedding_router, jira_documents, source_label="jira")
    confluence_indexed = await _index_documents(
        store, embedding_router, confluence_documents, source_label="confluence"
    )
    slack_indexed = await _index_documents(store, embedding_router, slack_documents, source_label="slack")
    meetings_indexed = await _index_documents(
        store, embedding_router, meeting_documents, source_label="meetings"
    )

    neo4j_result = await seed_neo4j_from_enterprise_data(
        settings,
        jira_documents=jira_documents,
        confluence_documents=confluence_documents,
    )

    counts = {
        "jira": await store.count_chunks(source="jira"),
        "confluence": await store.count_chunks(source="confluence"),
        "slack": await store.count_chunks(source="slack"),
        "meetings": await store.count_chunks(source="meetings"),
    }

    return {
        "status": "completed",
        "mode": "enterprise_fixture",
        "organization": ENTERPRISE_MANIFEST["organization"],
        "manifest": ENTERPRISE_MANIFEST,
        "indexed_this_run": {
            "jira": jira_indexed,
            "confluence": confluence_indexed,
            "slack": slack_indexed,
            "meetings": meetings_indexed,
        },
        "chunk_counts": counts,
        "total_chunks": sum(counts.values()),
        "meetings_directory": str(target_dir),
        "neo4j": neo4j_result,
        "github": {"status": "skipped", "reason": "excluded_by_request"},
        "test_queries": build_test_queries(),
        "action_channel_ids": [ch["id"] for ch in ENTERPRISE_MANIFEST["slack_channels"]],
    }
