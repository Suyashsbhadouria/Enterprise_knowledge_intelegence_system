from ekcip_connectors.confluence_cql import bounded_cql_for_space, resolve_sync_cql
from ekcip_connectors.jira_jql import bounded_jql_for_project, resolve_sync_jql
from ekcip_connectors.github_repos import parse_repo_list
from ekcip_connectors.runtime.confluence import build_confluence_connector
from ekcip_connectors.slack_channels import parse_channel_ids
from ekcip_api.services.confluence_sync import sync_confluence_pages
from ekcip_api.services.github_sync import build_github_connector, sync_github_repos
from ekcip_api.services.jira_sync import build_jira_connector, sync_jira_issues
from ekcip_api.services.slack_sync import build_slack_connector, sync_slack_channels
from ekcip_graph.enterprise_seed import seed_neo4j_from_enterprise_data
from ekcip_knowledge.embeddings import build_embedding_router
from ekcip_knowledge.store import KnowledgeStore
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


def _parse_csv_keys(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _select_jira_projects(
    projects: list[dict[str, object]],
    settings: Settings,
) -> list[dict[str, object]]:
    filter_keys = _parse_csv_keys(settings.seed_jira_project_keys)
    if filter_keys:
        allowed = {key.upper() for key in filter_keys}
        selected = [p for p in projects if str(p.get("key", "")).upper() in allowed]
    else:
        selected = list(projects)
    return selected[: settings.seed_max_projects]


def _select_confluence_spaces(
    spaces: list[dict[str, object]],
    settings: Settings,
) -> list[dict[str, object]]:
    filter_keys = _parse_csv_keys(settings.seed_confluence_space_keys)
    if filter_keys:
        allowed = {key.upper() for key in filter_keys}
        selected = [s for s in spaces if str(s.get("key", "")).upper() in allowed]
    else:
        selected = list(spaces)
    return selected[: settings.seed_max_confluence_spaces]


def build_sample_queries(
    *,
    project_keys: list[str],
    issue_keys: list[str],
    issue_titles: list[str],
    confluence_pages: list[dict[str, str]],
    github_items: list[dict[str, str]] | None = None,
    slack_messages: list[dict[str, str]] | None = None,
) -> list[str]:
    queries: list[str] = []
    if issue_keys:
        key = issue_keys[0]
        title = issue_titles[0] if issue_titles else key
        project = project_keys[0] if project_keys else "the project"
        queries.append(f"What is the status and assignee of {key} ({title})?")
        queries.append(
            f"In project {project}, summarize all indexed issues, owners, and blockers."
        )
    if len(issue_keys) >= 2:
        queries.append(
            f"Compare {issue_keys[0]} and {issue_keys[1]} — status, assignee, and latest updates."
        )
    if confluence_pages:
        page = confluence_pages[0]
        page_id = page.get("page_id", "")
        title = page.get("title", "the documentation page")
        space = page.get("space_key", "")
        queries.append(f"Summarize the Confluence page '{title}' (page {page_id}).")
        if issue_keys:
            queries.append(
                f"What does Confluence say about '{title}' in space {space}, "
                f"and how does it relate to Jira issue {issue_keys[0]}?"
            )
    if github_items:
        item = github_items[0]
        source_id = item.get("source_id", "")
        title = item.get("title", source_id)
        queries.append(f"What is the status of GitHub item {source_id} ({title})?")
    if slack_messages:
        msg = slack_messages[0]
        channel = msg.get("channel_name", "the channel")
        queries.append(f"Summarize recent Slack discussion in #{channel}.")
    if not queries:
        queries.append(
            "No indexed content yet. Run POST /v1/admin/seed after configuring connectors."
        )
    return queries


async def seed_all_sources(
    session: AsyncSession,
    settings: Settings,
    *,
    max_results: int | None = None,
) -> dict[str, object]:
    """Pull real Jira + Confluence data from your tenant; index and graph it."""
    per_project = max_results or settings.seed_max_results_per_project
    results: dict[str, object] = {"mode": "enterprise"}

    jira = build_jira_connector(settings)
    if jira is None:
        results["jira"] = {"status": "skipped", "reason": "jira_not_configured"}
        results["knowledge"] = {"status": "skipped", "reason": "jira_not_configured"}
        results["neo4j"] = {"status": "skipped", "reason": "jira_not_configured"}
        return results

    embedding_router = build_embedding_router(settings)
    if not embedding_router.configured_providers():
        results["jira"] = {"status": "skipped", "reason": "no_embedding_provider"}
        results["knowledge"] = {"status": "skipped", "reason": "no_embedding_provider"}
        results["neo4j"] = {"status": "skipped", "reason": "no_embedding_provider"}
        return results

    store = KnowledgeStore(session)
    jira_documents: list[dict[str, object]] = []
    all_issue_keys: list[str] = []
    all_issue_titles: list[str] = []
    project_keys: list[str] = []
    jira_sync_runs: list[dict[str, object]] = []

    try:
        projects = await jira.list_projects(max_results=settings.seed_max_projects)
        selected_projects = _select_jira_projects(projects, settings)
        if not selected_projects:
            results["jira"] = {"status": "failed", "reason": "no_matching_jira_projects"}
            results["knowledge"] = {"status": "skipped", "reason": "no_jira_projects"}
        else:
            for project in selected_projects:
                project_key = str(project.get("key", ""))
                if not project_key:
                    continue
                project_keys.append(project_key)
                jql = bounded_jql_for_project(project_key, days=settings.seed_jira_days)
                issues = await jira.search_issues(jql, max_results=per_project)
                documents = [jira.issue_document(issue) for issue in issues]
                jira_documents.extend(documents)
                for doc in documents:
                    key = str(doc.get("source_id", ""))
                    if key:
                        all_issue_keys.append(key)
                        all_issue_titles.append(str(doc.get("title", key)))
                sync_result = await sync_jira_issues(
                    store,
                    jira,
                    embedding_router,
                    jql=jql,
                    max_results=per_project,
                    issues=issues,
                )
                jira_sync_runs.append(
                    {
                        "project_key": project_key,
                        "jql": jql,
                        **sync_result,
                    }
                )

            results["jira_projects"] = project_keys
            results["jira_sync"] = jira_sync_runs
            results["knowledge"] = {
                "status": "completed",
                "issues_indexed": len(jira_documents),
                "projects_synced": len(project_keys),
            }
    except Exception as exc:
        results["knowledge"] = {"status": "failed", "error": str(exc)[:500]}
        logger.error("jira_enterprise_seed_failed", error=str(exc))

    results["jira_chunks"] = await store.count_chunks(source="jira")

    confluence_documents: list[dict[str, object]] = []
    all_confluence_pages: list[dict[str, str]] = []
    confluence = build_confluence_connector(settings)
    if confluence is None:
        results["confluence"] = {"status": "skipped", "reason": "confluence_not_configured"}
    else:
        conf_sync_runs: list[dict[str, object]] = []
        try:
            spaces = await confluence.list_spaces(max_results=settings.seed_max_confluence_spaces)
            selected_spaces = _select_confluence_spaces(spaces, settings)
            if selected_spaces:
                for space in selected_spaces:
                    space_key = str(space.get("key", ""))
                    if not space_key:
                        continue
                    cql = bounded_cql_for_space(space_key, days=settings.seed_jira_days)
                    pages = await confluence.search_pages(cql, max_results=per_project)
                    documents = [confluence.page_document(page) for page in pages]
                    confluence_documents.extend(documents)
                    sync_result = await sync_confluence_pages(
                        store,
                        confluence,
                        embedding_router,
                        cql=cql,
                        max_results=per_project,
                        pages=pages,
                    )
                    all_confluence_pages.extend(sync_result.get("pages") or [])
                    conf_sync_runs.append({"space_key": space_key, "cql": cql, **sync_result})
            else:
                cql = resolve_sync_cql(
                    settings.confluence_sync_cql,
                    default=settings.confluence_sync_cql,
                )
                pages = await confluence.search_pages(cql, max_results=per_project)
                confluence_documents = [confluence.page_document(page) for page in pages]
                sync_result = await sync_confluence_pages(
                    store,
                    confluence,
                    embedding_router,
                    cql=cql,
                    max_results=per_project,
                    pages=pages,
                )
                all_confluence_pages = list(sync_result.get("pages") or [])
                conf_sync_runs.append({"cql": cql, **sync_result})

            results["confluence"] = conf_sync_runs
        except Exception as exc:
            results["confluence"] = {"status": "failed", "error": str(exc)[:500]}
            logger.error("confluence_enterprise_seed_failed", error=str(exc))

    results["confluence_chunks"] = await store.count_chunks(source="confluence")
    all_github_items: list[dict[str, str]] = []
    all_slack_messages: list[dict[str, str]] = []

    github = build_github_connector(settings)
    if github is None or not settings.github_repos.strip():
        results["github"] = {"status": "skipped", "reason": "github_not_configured"}
    else:
        try:
            repos = parse_repo_list(settings.github_repos)
            gh_result = await sync_github_repos(
                store,
                github,
                embedding_router,
                repos=repos,
                days=settings.github_sync_days,
                max_results_per_repo=min(per_project, settings.github_max_results_per_repo),
            )
            all_github_items = list(gh_result.get("items") or [])
            results["github"] = gh_result
        except Exception as exc:
            results["github"] = {"status": "failed", "error": str(exc)[:500]}
            logger.error("github_enterprise_seed_failed", error=str(exc))

    slack = build_slack_connector(settings)
    if slack is None or not settings.slack_channel_ids.strip():
        results["slack"] = {"status": "skipped", "reason": "slack_not_configured"}
    else:
        try:
            channel_ids = parse_channel_ids(settings.slack_channel_ids)
            slack_result = await sync_slack_channels(
                store,
                slack,
                embedding_router,
                channel_ids=channel_ids,
                days=settings.slack_sync_days,
                max_messages_per_channel=settings.slack_max_messages_per_channel,
            )
            all_slack_messages = list(slack_result.get("messages") or [])
            results["slack"] = slack_result
        except Exception as exc:
            results["slack"] = {"status": "failed", "error": str(exc)[:500]}
            logger.error("slack_enterprise_seed_failed", error=str(exc))

    results["github_chunks"] = await store.count_chunks(source="github")
    results["slack_chunks"] = await store.count_chunks(source="slack")
    results["total_chunks"] = (
        int(results["jira_chunks"])
        + int(results["confluence_chunks"])
        + int(results["github_chunks"])
        + int(results["slack_chunks"])
    )

    results["neo4j"] = await seed_neo4j_from_enterprise_data(
        settings,
        jira_documents=jira_documents,
        confluence_documents=confluence_documents,
    )

    results["sample_queries"] = build_sample_queries(
        project_keys=project_keys,
        issue_keys=all_issue_keys[:10],
        issue_titles=all_issue_titles[:10],
        confluence_pages=all_confluence_pages[:10],
        github_items=all_github_items[:10],
        slack_messages=all_slack_messages[:10],
    )

    return results
