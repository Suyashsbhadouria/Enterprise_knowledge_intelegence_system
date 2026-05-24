"""Redis cache for live connector fetch results (short TTL)."""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis

from ekcip_knowledge.types import RetrievalHit
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


class RedisKnowledgeCache:
    """Caches serialized retrieval hits from live API fetches."""

    def __init__(self, redis_url: str, *, ttl_seconds: int = 600) -> None:
        self._redis_url = redis_url
        self._ttl_seconds = ttl_seconds
        self._client: redis.Redis | None = None

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_hits(self, cache_key: str) -> list[RetrievalHit] | None:
        try:
            client = await self._get_client()
            raw = await client.get(cache_key)
            if not raw:
                return None
            payload = json.loads(raw)
            if not isinstance(payload, list):
                return None
            return [RetrievalHit.model_validate(item) for item in payload]
        except Exception as exc:
            logger.warning("knowledge_cache_get_failed", error=str(exc)[:200])
            return None

    async def set_hits(self, cache_key: str, hits: list[RetrievalHit]) -> None:
        if not hits:
            return
        try:
            client = await self._get_client()
            payload = json.dumps([hit.model_dump(mode="json") for hit in hits])
            await client.setex(cache_key, self._ttl_seconds, payload)
        except Exception as exc:
            logger.warning("knowledge_cache_set_failed", error=str(exc)[:200])

    @staticmethod
    def build_key(prefix: str, parts: dict[str, Any]) -> str:
        import hashlib

        normalized = json.dumps(parts, sort_keys=True, default=str)
        digest = hashlib.sha256(normalized.encode()).hexdigest()[:32]
        return f"ekcip:{prefix}:{digest}"
