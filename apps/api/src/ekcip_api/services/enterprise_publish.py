"""Publish Nexus fixture to live Jira/Confluence/Slack, then re-index Postgres + Neo4j."""

from __future__ import annotations

from pathlib import Path

from ekcip_api.services.enterprise_fixture_seed import _index_documents, seed_enterprise_fixture
from ekcip_api.services.jira_sync import build_jira_connector
from ekcip_api.services.slack_sync import sync_slack_channels
from ekcip_connectors.fixtures.enterprise_publish import publish_nexus_to_live
from ekcip_connectors.meetings.transcript import meeting_documents_from_file
from ekcip_connectors.runtime.confluence import build_confluence_connector
from ekcip_connectors.runtime.slack import build_slack_connector
from ekcip_connectors.slack_channels import parse_channel_ids
from ekcip_graph.enterprise_seed import seed_neo4j_from_enterprise_data
from ekcip_knowledge.embeddings import build_embedding_router
from ekcip_knowledge.store import KnowledgeStore
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


async def _reindex_published_data(
    session: AsyncSession,
    settings: Settings,
    *,
    issue_key_map: dict[str, str],
    page_map: dict[str, str],
    clear_existing: bool,
) -> dict[str, object]:
    jira = build_jira_connector(settings)
    confluence = build_confluence_connector(settings)
    slack = build_slack_connector(settings)
    embedding_router = build_embedding_router(settings)
    store = KnowledgeStore(session)

    if clear_existing:
        await store.delete_chunks_for_sources(["jira", "confluence", "slack", "meetings"])

    jira_documents: list[dict[str, object]] = []
    if jira is not None:
        for fixture_key, real_key in issue_key_map.items():
            if real_key.startswith("DRY-"):
                continue
            try:
                issue = await jira.get_issue(real_key)
                jira_documents.append(jira.issue_document(issue))
            except Exception as exc:
                logger.warning("reindex_jira_issue_failed", key=real_key, error=str(exc))

    confluence_documents: list[dict[str, object]] = []
    if confluence is not None:
        for fixture_id, real_id in page_map.items():
            if real_id.startswith("DRY-"):
                continue
            try:
                page = await confluence.get_page(real_id)
                confluence_documents.append(confluence.page_document(page))
            except Exception as exc:
                logger.warning("reindex_confluence_page_failed", page_id=real_id, error=str(exc))

    jira_indexed = await _index_documents(store, embedding_router, jira_documents, source_label="jira")
    confluence_indexed = await _index_documents(
        store, embedding_router, confluence_documents, source_label="confluence"
    )

    slack_indexed = 0
    if slack is not None and settings.slack_channel_ids.strip():
        channel_ids = parse_channel_ids(settings.slack_channel_ids)
        slack_result = await sync_slack_channels(
            store,
            slack,
            embedding_router,
            channel_ids=channel_ids,
            days=settings.slack_sync_days,
            max_messages_per_channel=min(200, settings.slack_max_messages_per_channel),
        )
        slack_indexed = int(slack_result.get("messages_indexed") or 0)

    meetings_dir = Path(settings.meetings_transcripts_dir or "./data/meetings").expanduser().resolve()
    meeting_documents: list[dict[str, object]] = []
    if meetings_dir.is_dir():
        for path in sorted(meetings_dir.glob("*.txt")):
            meeting_documents.extend(meeting_documents_from_file(path))
    meetings_indexed = await _index_documents(
        store, embedding_router, meeting_documents, source_label="meetings"
    )

    neo4j_result = await seed_neo4j_from_enterprise_data(
        settings,
        jira_documents=jira_documents,
        confluence_documents=confluence_documents,
    )

    return {
        "reindexed": {
            "jira": jira_indexed,
            "confluence": confluence_indexed,
            "slack": slack_indexed,
            "meetings": meetings_indexed,
        },
        "chunk_counts": {
            "jira": await store.count_chunks(source="jira"),
            "confluence": await store.count_chunks(source="confluence"),
            "slack": await store.count_chunks(source="slack"),
            "meetings": await store.count_chunks(source="meetings"),
        },
        "neo4j": neo4j_result,
        "live_issue_keys": list(issue_key_map.values()),
    }


async def publish_enterprise_to_live_sources(
    session: AsyncSession,
    settings: Settings,
    *,
    dry_run: bool = False,
    clear_knowledge_before_reindex: bool = True,
    also_seed_local_fixture: bool = False,
) -> dict[str, object]:
    if not settings.jira_configured:
        raise ValueError("Jira not configured (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN).")

    jira = build_jira_connector(settings)
    if jira is None:
        raise ValueError("Could not build Jira connector.")

    confluence = build_confluence_connector(settings)
    slack = build_slack_connector(settings)

    publish_result = await publish_nexus_to_live(
        jira=jira,
        confluence=confluence,
        slack=slack,
        settings=settings,
        dry_run=dry_run,
    )

    reindex_result: dict[str, object] = {"status": "skipped", "reason": "dry_run"}
    if not dry_run:
        reindex_result = await _reindex_published_data(
            session,
            settings,
            issue_key_map=publish_result["issue_key_map"],
            page_map=publish_result["confluence_page_map"],
            clear_existing=clear_knowledge_before_reindex,
        )

    local_fixture: dict[str, object] | None = None
    if also_seed_local_fixture and not dry_run:
        local_fixture = await seed_enterprise_fixture(session, settings, clear_existing=False)

    return {
        "status": "completed",
        "mode": "enterprise_publish_live",
        "dry_run": dry_run,
        "publish": publish_result,
        "reindex": reindex_result,
        "local_fixture": local_fixture,
        "notes": [
            "Jira issues use summary prefix [Nexus CORE-101] and label from ENTERPRISE_PUBLISH_JIRA_LABEL.",
            "Confluence pages use title prefix [Nexus 10001].",
            "Slack messages are prefixed [Nexus Demo] and reference real Jira keys after mapping.",
            "Re-open Jira/Confluence/Slack UIs — fixture keys are mapped to your tenant's real keys.",
        ],
    }
