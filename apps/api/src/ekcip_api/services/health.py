from typing import Any

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ekcip_connectors.ports import ConnectorPort
from ekcip_graph.client import verify_neo4j_connection
from ekcip_shared.config import Settings


async def check_postgres(engine: AsyncEngine) -> dict[str, Any]:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "up"}
    except Exception as exc:
        return {"status": "down", "error": str(exc)}


async def check_redis(url: str) -> dict[str, Any]:
    client = redis.from_url(url, decode_responses=True)
    try:
        await client.ping()
        return {"status": "up"}
    except Exception as exc:
        return {"status": "down", "error": str(exc)}
    finally:
        await client.aclose()


async def check_neo4j(settings: Settings) -> dict[str, Any]:
    return await verify_neo4j_connection(settings)


async def check_connectors(connectors: list[ConnectorPort]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for connector in connectors:
        health = await connector.health()
        results.append(health.model_dump())
    return results
