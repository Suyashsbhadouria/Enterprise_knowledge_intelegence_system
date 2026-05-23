from ekcip_connectors.runtime.jira import JiraConnector
from ekcip_knowledge.embeddings import EmbeddingError, EmbeddingRouter
from ekcip_knowledge.store import KnowledgeStore
from ekcip_knowledge.types import KnowledgeChunkRecord
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


def build_jira_connector(settings: Settings) -> JiraConnector | None:
    if not (settings.jira_base_url and settings.jira_email and settings.jira_api_token):
        return None
    return JiraConnector(
        settings.jira_base_url,
        settings.jira_email,
        settings.jira_api_token,
    )


async def sync_jira_issues(
    store: KnowledgeStore,
    jira: JiraConnector,
    embedding_router: EmbeddingRouter,
    *,
    jql: str,
    max_results: int,
    issues: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    run_id = await store.start_sync_run("jira")
    indexed = 0
    indexed_keys: list[str] = []
    try:
        issue_list = issues if issues is not None else await jira.search_issues(jql, max_results=max_results)
        for issue in issue_list:
            document = jira.issue_document(issue)
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
            indexed_keys.append(str(document["source_id"]))
        await store.finish_sync_run(run_id, status="completed", issues_indexed=indexed)
        logger.info("jira_sync_completed", issues_indexed=indexed, jql=jql)
        return {
            "status": "completed",
            "issues_indexed": indexed,
            "issue_keys": indexed_keys,
            "run_id": str(run_id),
        }
    except Exception as exc:
        await store.finish_sync_run(
            run_id,
            status="failed",
            issues_indexed=indexed,
            detail=str(exc)[:1000],
        )
        logger.error("jira_sync_failed", error=str(exc), issues_indexed=indexed)
        raise
