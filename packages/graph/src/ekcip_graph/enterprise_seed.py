"""Build Neo4j graph from real Jira and Confluence documents (no demo placeholders)."""

from typing import Any

from ekcip_graph.client import create_neo4j_driver
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

_DEMO_NODE_IDS = (
    "EKCIP-DEMO",
    "EKCIP-F1",
    "ekcip-demo-user",
    "jira-seed-1",
    "jira-seed-2",
)

_CLEAR_DEMO_CYPHER = """
MATCH (n)
WHERE n.id IN $demo_ids
DETACH DELETE n
"""

_ISSUES_CYPHER = """
UNWIND $rows AS row
MERGE (p:Project {id: row.project_id, key: row.project_key, name: row.project_name})
MERGE (i:Issue {
  id: row.issue_id,
  source: 'jira',
  key: row.issue_key,
  status: row.status,
  title: row.title
})
MERGE (p)-[:CONTAINS]->(i)
FOREACH (_ IN CASE WHEN row.assignee_id IS NULL THEN [] ELSE [1] END |
  MERGE (person:Person {
    id: row.assignee_id,
    email: coalesce(row.assignee_email, ''),
    name: row.assignee_name
  })
  MERGE (person)-[:ASSIGNED_TO]->(i)
)
"""

_PAGES_CYPHER = """
UNWIND $rows AS row
MERGE (s:Space {id: row.space_id, key: row.space_key, name: row.space_name})
MERGE (d:Document {
  id: row.page_id,
  source: 'confluence',
  title: row.title,
  url: row.url
})
MERGE (s)-[:CONTAINS]->(d)
"""


def _jira_rows(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for doc in documents:
        meta = doc.get("metadata") or {}
        project_key = str(meta.get("project") or "UNKNOWN")
        issue_key = str(doc.get("source_id") or "")
        if not issue_key:
            continue
        assignee_id = meta.get("assignee_account_id")
        assignee_name = str(meta.get("assignee") or "")
        if assignee_name == "Unassigned":
            assignee_id = None
            assignee_name = ""
        rows.append(
            {
                "project_id": f"jira-project-{project_key}",
                "project_key": project_key,
                "project_name": project_key,
                "issue_id": f"jira-{issue_key}",
                "issue_key": issue_key,
                "status": str(meta.get("status") or ""),
                "title": str(doc.get("title") or issue_key),
                "assignee_id": assignee_id,
                "assignee_email": meta.get("assignee_email"),
                "assignee_name": assignee_name or None,
            }
        )
    return rows


def _confluence_rows(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for doc in documents:
        meta = doc.get("metadata") or {}
        space_key = str(meta.get("space_key") or "UNKNOWN")
        page_id = str(doc.get("source_id") or "")
        if not page_id:
            continue
        rows.append(
            {
                "space_id": f"confluence-space-{space_key}",
                "space_key": space_key,
                "space_name": str(meta.get("space_name") or space_key),
                "page_id": f"confluence-{page_id}",
                "title": str(doc.get("title") or page_id),
                "url": doc.get("url"),
            }
        )
    return rows


async def seed_neo4j_from_enterprise_data(
    settings: Settings,
    *,
    jira_documents: list[dict[str, Any]],
    confluence_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    if not settings.neo4j_configured:
        return {"status": "skipped", "reason": "neo4j_not_configured"}

    jira_rows = _jira_rows(jira_documents)
    page_rows = _confluence_rows(confluence_documents)
    if not jira_rows and not page_rows:
        return {"status": "skipped", "reason": "no_documents_to_graph"}

    driver = create_neo4j_driver(settings)
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            await session.run(_CLEAR_DEMO_CYPHER, demo_ids=list(_DEMO_NODE_IDS))
            if jira_rows:
                await session.run(_ISSUES_CYPHER, rows=jira_rows)
            if page_rows:
                await session.run(_PAGES_CYPHER, rows=page_rows)
            count_result = await session.run("MATCH (n) RETURN count(n) AS node_count")
            count_record = await count_result.single()
            node_count = count_record.get("node_count") if count_record else 0

        logger.info(
            "neo4j_enterprise_seed_completed",
            jira_nodes=len(jira_rows),
            confluence_nodes=len(page_rows),
            node_count=node_count,
        )
        return {
            "status": "completed",
            "mode": "enterprise",
            "jira_issues_graphed": len(jira_rows),
            "confluence_pages_graphed": len(page_rows),
            "node_count": node_count,
        }
    finally:
        await driver.close()
