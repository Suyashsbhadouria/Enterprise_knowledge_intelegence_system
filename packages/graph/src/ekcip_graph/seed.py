from typing import Any

from ekcip_graph.client import create_neo4j_driver
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

SEED_CYPHER = """
MERGE (p:Project {id: 'EKCIP-DEMO', key: 'EKCIP', name: 'EKCIP Demo Project'})
MERGE (f:Feature {id: 'EKCIP-F1', key: 'FEATURE-Y', name: 'Feature Y'})
MERGE (person:Person {id: 'ekcip-demo-user', email: 'demo@ekcip.local', name: 'Demo Engineer'})
MERGE (i1:Issue {id: 'jira-seed-1', source: 'jira', key: 'SEED-1', status: 'In Progress', title: 'EKCIP seed: Auth integration'})
MERGE (i2:Issue {id: 'jira-seed-2', source: 'jira', key: 'SEED-2', status: 'To Do', title: 'EKCIP seed: API documentation'})
MERGE (p)-[:CONTAINS]->(f)
MERGE (p)-[:CONTAINS]->(i1)
MERGE (p)-[:CONTAINS]->(i2)
MERGE (person)-[:ASSIGNED_TO]->(i1)
MERGE (f)-[:TRACKED_BY]->(i1)
MERGE (i2)-[:BLOCKS]->(i1)
RETURN p.key AS project_key, f.name AS feature_name
"""


async def seed_neo4j_demo_graph(settings: Settings) -> dict[str, Any]:
    if not settings.neo4j_configured:
        return {"status": "skipped", "reason": "neo4j_not_configured"}

    driver = create_neo4j_driver(settings)
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run(SEED_CYPHER)
            record = await result.single()
            count_result = await session.run(
                "MATCH (n) RETURN count(n) AS node_count"
            )
            count_record = await count_result.single()
            node_count = count_record.get("node_count") if count_record else 0
        logger.info("neo4j_seed_completed", node_count=node_count)
        return {
            "status": "completed",
            "project_key": record.get("project_key") if record else "EKCIP",
            "feature_name": record.get("feature_name") if record else "Feature Y",
            "node_count": node_count,
        }
    finally:
        await driver.close()
