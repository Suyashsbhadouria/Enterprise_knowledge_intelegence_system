"""Slack Web API client: read ingest (Phase 2) and write actions (Phase 4)."""

import time
from typing import Any

import httpx

from ekcip_connectors.ports import ConnectorCapability, ConnectorHealth, ConnectorPort
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

_API_ROOT = "https://slack.com/api"

# Bot token scopes required for read-only channel ingest (OAuth & Permissions → reinstall after changes).
SLACK_READ_SCOPES = (
    "channels:history",
    "channels:read",
    "groups:history",
    "groups:read",
)

SLACK_WRITE_SCOPES = ("chat:write",)

_SCOPE_HINTS: dict[str, str] = {
    "conversations.info": "channels:read (public channels) and/or groups:read (private channels)",
    "conversations.history": "channels:history (public) and/or groups:history (private)",
}


class SlackConnector(ConnectorPort):
    name = "slack"
    capabilities = (
        ConnectorCapability.READ,
        ConnectorCapability.WRITE,
    )

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def _api_post(self, method: str, json_body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{_API_ROOT}/{method}",
                headers=self._headers(),
                json=json_body,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Slack {method} failed: HTTP {response.status_code}")
        data = response.json()
        if not data.get("ok"):
            error = str(data.get("error", "unknown"))
            if error == "missing_scope":
                hint = ", ".join((*SLACK_READ_SCOPES, *SLACK_WRITE_SCOPES))
                raise RuntimeError(
                    f"Slack {method} error: missing_scope. Add Bot Token Scopes: {hint}. "
                    "Reinstall the app and update SLACK_BOT_TOKEN."
                )
            raise RuntimeError(f"Slack {method} error: {error}")
        return data

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
            error = str(data.get("error", "unknown"))
            if error == "missing_scope":
                hint = _SCOPE_HINTS.get(
                    method,
                    ", ".join(SLACK_READ_SCOPES),
                )
                raise RuntimeError(
                    f"Slack {method} error: missing_scope. Add these Bot Token Scopes: {hint}. "
                    "Reinstall the app to your workspace, then copy the new xoxb- token into SLACK_BOT_TOKEN."
                )
            raise RuntimeError(f"Slack {method} error: {error}")
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

    async def list_joined_channels(self, *, limit: int = 200) -> list[dict[str, str]]:
        """List workspace channels the bot is a member of (id + name)."""
        channels: list[dict[str, str]] = []
        cursor: str | None = None
        while len(channels) < limit:
            params: dict[str, Any] = {
                "types": "public_channel,private_channel",
                "exclude_archived": "true",
                "limit": min(200, limit - len(channels)),
            }
            if cursor:
                params["cursor"] = cursor
            data = await self._api_get("conversations.list", params)
            for channel in data.get("channels") or []:
                if not channel.get("is_member"):
                    continue
                channel_id = str(channel.get("id") or "")
                name = str(channel.get("name") or "")
                if channel_id and name:
                    channels.append({"id": channel_id, "name": name})
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return channels[:limit]

    async def get_channel_info(self, channel_id: str) -> dict[str, Any]:
        """Resolve channel name; falls back to channel_id if read scope is missing."""
        try:
            data = await self._api_get("conversations.info", {"channel": channel_id})
            channel = data.get("channel") or {}
            return {
                "id": channel.get("id", channel_id),
                "name": channel.get("name", channel_id),
                "is_private": bool(channel.get("is_private")),
            }
        except RuntimeError as exc:
            if "missing_scope" in str(exc):
                logger.warning(
                    "slack_channel_info_skipped_missing_scope",
                    channel_id=channel_id,
                )
                return {
                    "id": channel_id,
                    "name": channel_id,
                    "is_private": None,
                }
            raise

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

    async def get_message(self, channel_id: str, message_ts: str) -> dict[str, Any]:
        """Fetch a single channel message by timestamp (live)."""
        data = await self._api_get(
            "conversations.history",
            {
                "channel": channel_id,
                "latest": message_ts,
                "inclusive": True,
                "limit": 1,
            },
        )
        messages = list(data.get("messages") or [])
        if not messages:
            raise RuntimeError(f"Slack message not found: {channel_id}:{message_ts}")
        return messages[0]

    async def post_message(
        self,
        channel_id: str,
        text: str,
        *,
        thread_ts: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"channel": channel_id, "text": text}
        if thread_ts:
            body["thread_ts"] = thread_ts
        data = await self._api_post("chat.postMessage", body)
        return {
            "channel": data.get("channel", channel_id),
            "ts": data.get("ts"),
            "message": (data.get("message") or {}).get("text", text),
        }

    async def schedule_message(
        self,
        channel_id: str,
        text: str,
        *,
        post_at: int,
    ) -> dict[str, Any]:
        data = await self._api_post(
            "chat.scheduleMessage",
            {"channel": channel_id, "text": text, "post_at": post_at},
        )
        return {
            "channel": data.get("channel", channel_id),
            "scheduled_message_id": data.get("scheduled_message_id"),
            "post_at": post_at,
        }

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
