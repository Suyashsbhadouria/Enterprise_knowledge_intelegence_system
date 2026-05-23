from ekcip_connectors.runtime.github import GitHubConnector
from ekcip_knowledge.embeddings import EmbeddingError, EmbeddingRouter
from ekcip_knowledge.store import KnowledgeStore
from ekcip_knowledge.types import KnowledgeChunkRecord
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


def build_github_connector(settings: Settings) -> GitHubConnector | None:
    if not settings.github_token:
        return None
    return GitHubConnector(settings.github_token)


async def sync_github_repos(
    store: KnowledgeStore,
    github: GitHubConnector,
    embedding_router: EmbeddingRouter,
    *,
    repos: list[str],
    days: int,
    max_results_per_repo: int,
    items_by_repo: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, object]:
    run_id = await store.start_sync_run("github")
    indexed = 0
    indexed_items: list[dict[str, str]] = []
    since_iso = GitHubConnector.since_iso(days)
    try:
        for repo in repos:
            item_list = (
                items_by_repo.get(repo)
                if items_by_repo is not None
                else await github.list_recent_items(
                    repo,
                    since_iso=since_iso,
                    max_results=max_results_per_repo,
                )
            )
            for item in item_list or []:
                document = github.item_document(repo, item)
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
                indexed_items.append(
                    {
                        "source_id": str(document["source_id"]),
                        "title": str(document["title"]),
                        "repo": repo,
                    }
                )
        await store.finish_sync_run(run_id, status="completed", issues_indexed=indexed)
        logger.info("github_sync_completed", items_indexed=indexed, repos=repos)
        return {
            "status": "completed",
            "items_indexed": indexed,
            "items": indexed_items,
            "repos": repos,
            "run_id": str(run_id),
        }
    except Exception as exc:
        await store.finish_sync_run(
            run_id,
            status="failed",
            issues_indexed=indexed,
            detail=str(exc)[:1000],
        )
        logger.error("github_sync_failed", error=str(exc), items_indexed=indexed)
        raise
