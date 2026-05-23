from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from ekcip_shared.config import Settings


def create_neo4j_driver(settings: Settings) -> AsyncDriver:
    if not settings.neo4j_configured:
        raise ValueError(
            "Neo4j is not configured. Set NEO4J_URI and NEO4J_PASSWORD (Aura URI from console.neo4j.io)."
        )
    return AsyncGraphDatabase.driver(
        settings.neo4j_driver_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


async def verify_neo4j_connection(settings: Settings) -> dict[str, Any]:
    if not settings.neo4j_configured:
        return {"status": "skipped", "mode": "unconfigured", "detail": "NEO4J_URI or NEO4J_PASSWORD missing"}

    driver = create_neo4j_driver(settings)
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            if record and record.get("ok") == 1:
                return {
                    "status": "up",
                    "mode": "aura" if settings.neo4j_is_aura else "self-hosted",
                    "database": settings.neo4j_database,
                }
        return {"status": "down", "mode": "unknown", "error": "unexpected response"}
    except Exception as exc:
        return {
            "status": "down",
            "mode": "aura" if settings.neo4j_is_aura else "self-hosted",
            "error": str(exc),
        }
    finally:
        await driver.close()


async def close_neo4j_driver(driver: AsyncDriver | None) -> None:
    if driver is not None:
        await driver.close()
