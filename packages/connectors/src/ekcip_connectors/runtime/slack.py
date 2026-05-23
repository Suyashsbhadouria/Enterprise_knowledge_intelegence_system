"""Slack Web API client for read-only channel history ingest (Phase 2)."""

import time
from typing import Any

import httpx

from ekcip_connectors.ports import ConnectorCapability, ConnectorHealth, ConnectorPort
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

_API_ROOT = "https://slack.com/api"


class SlackConnector(ConnectorPort):
    name = "slack"
    capabilities = (ConnectorCapability.READ,)

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def _api_get(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{_API_ROOT}/{method}",
                headers=self._headers(),
                params=params,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Slack {method} failed: HTTP {response.status_code}")
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack {method} error: {data.get('error', 'unknown')}")
        return data

    async def health(self) -> ConnectorHealth:
        try:
            await self.ping()
            return ConnectorHealth(name=self.name, ready=True, mode="slack-web-api")
        except Exception as exc:
            return ConnectorHealth(
                name=self.name,
                ready=False,
                mode="slack-web-api",
                detail=str(exc)[:300],
            )

    async def ping(self) -> dict[str, Any]:
        data = await self._api_get("auth.test", {})
        return {
            "team": data.get("team"),
            "user": data.get("user"),
            "bot_id": data.get("bot_id"),
        }

    @staticmethod
    def oldest_timestamp(days: int) -> str:
        return str(int(time.time()) - max(days, 1) * 86400)

    async def get_channel_info(self, channel_id: str) -> dict[str, Any]:
        data = await self._api_get("conversations.info", {"channel": channel_id})
        channel = data.get("channel") or {}
        return {
            "id": channel.get("id", channel_id),
            "name": channel.get("name", channel_id),
            "is_private": bool(channel.get("is_private")),
        }

    async def fetch_channel_messages(
        self,
        channel_id: str,
        *,
        oldest: str,
        max_messages: int,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(messages) < max_messages:
            params: dict[str, Any] = {
                "channel": channel_id,
                "limit": min(200, max_messages - len(messages)),
                "oldest": oldest,
            }
            if cursor:
                params["cursor"] = cursor
            data = await self._api_get("conversations.history", params)
            batch = list(data.get("messages") or [])
            if not batch:
                break
            messages.extend(batch)
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return messages[:max_messages]

    def message_document(
        self,
        channel_id: str,
        channel_name: str,
        message: dict[str, Any],
    ) -> dict[str, Any] | None:
        text = str(message.get("text") or "").strip()
        if not text:
            return None
        ts = str(message.get("ts") or "")
        if not ts:
            return None
        source_id = f"{channel_id}:{ts.replace('.', '')}"
        user = str(message.get("user") or message.get("username") or "unknown")
        thread_ts = message.get("thread_ts")
        permalink_base = f"slack://channel?team=&id={channel_id}&message={ts}"
        parts = [
            f"Slack message in #{channel_name}",
            f"Channel: {channel_id}",
            f"User: {user}",
            f"Timestamp: {ts}",
            f"Text:\n{text[:8000]}",
        ]
        if thread_ts and thread_ts != ts:
            parts.insert(3, f"Thread root: {thread_ts}")
        return {
            "source": "slack",
            "source_id": source_id,
            "title": f"#{channel_name} — {text[:80]}",
            "content": "\n".join(parts),
            "url": permalink_base,
            "metadata": {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "user": user,
                "ts": ts,
                "thread_ts": thread_ts,
            },
        }


def build_slack_connector(settings: Settings) -> SlackConnector | None:
    if not settings.slack_bot_token:
        return None
    return SlackConnector(settings.slack_bot_token)
