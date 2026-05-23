from ekcip_connectors.runtime.slack import SlackConnector
from ekcip_knowledge.embeddings import EmbeddingError, EmbeddingRouter
from ekcip_knowledge.store import KnowledgeStore
from ekcip_knowledge.types import KnowledgeChunkRecord
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


def build_slack_connector(settings: Settings) -> SlackConnector | None:
    if not settings.slack_bot_token:
        return None
    return SlackConnector(settings.slack_bot_token)


async def sync_slack_channels(
    store: KnowledgeStore,
    slack: SlackConnector,
    embedding_router: EmbeddingRouter,
    *,
    channel_ids: list[str],
    days: int,
    max_messages_per_channel: int,
    messages_by_channel: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, object]:
    run_id = await store.start_sync_run("slack")
    indexed = 0
    indexed_messages: list[dict[str, str]] = []
    oldest = SlackConnector.oldest_timestamp(days)
    try:
        for channel_id in channel_ids:
            info = await slack.get_channel_info(channel_id)
            channel_name = str(info.get("name") or channel_id)
            message_list = (
                messages_by_channel.get(channel_id)
                if messages_by_channel is not None
                else await slack.fetch_channel_messages(
                    channel_id,
                    oldest=oldest,
                    max_messages=max_messages_per_channel,
                )
            )
            for message in message_list or []:
                document = slack.message_document(channel_id, channel_name, message)
                if document is None or not document.get("source_id"):
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
                indexed_messages.append(
                    {
                        "source_id": str(document["source_id"]),
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                    }
                )
        await store.finish_sync_run(run_id, status="completed", issues_indexed=indexed)
        logger.info("slack_sync_completed", messages_indexed=indexed, channels=channel_ids)
        return {
            "status": "completed",
            "messages_indexed": indexed,
            "messages": indexed_messages,
            "channels": channel_ids,
            "run_id": str(run_id),
        }
    except Exception as exc:
        await store.finish_sync_run(
            run_id,
            status="failed",
            issues_indexed=indexed,
            detail=str(exc)[:1000],
        )
        logger.error("slack_sync_failed", error=str(exc), messages_indexed=indexed)
        raise
