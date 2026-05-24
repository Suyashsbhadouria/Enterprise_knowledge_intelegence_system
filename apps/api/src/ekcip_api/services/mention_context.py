"""Resolve @mentions in user messages and build Slack channel name maps."""

from __future__ import annotations

from ekcip_api.services.mention_catalog import build_mention_catalog
from ekcip_connectors.mentions import resolve_mentions_in_text
from ekcip_connectors.slack_channels import parse_channel_ids
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


def _configured_slack_channel_ids(raw: str) -> list[str]:
    if not raw.strip():
        return []
    try:
        return parse_channel_ids(raw)
    except ValueError:
        logger.warning("slack_channel_ids_lenient_parse", raw=raw[:80])
        return [part.strip().upper() for part in raw.split(",") if part.strip()]


async def prepare_user_message_context(
    session: AsyncSession,
    settings: Settings,
    user_text: str,
) -> tuple[str, dict[str, str], list[str]]:
    """
    Returns (resolved_text, slack_name_to_id, allowed_slack_channel_ids).

    User-facing text keeps @names; resolved text substitutes channel ids and
  issue keys for downstream QA, refresh, and action detection.
    """
    catalog = await build_mention_catalog(session, settings, query="", limit=500)
    resolved = resolve_mentions_in_text(user_text, catalog)

    name_to_id: dict[str, str] = {}
    for item in catalog:
        if item.kind != "slack_channel":
            continue
        channel_name = str(item.metadata.get("channel_name") or "")
        channel_id = str(item.metadata.get("channel_id") or "")
        if channel_name and channel_id:
            name_to_id[channel_name] = channel_id

    configured = _configured_slack_channel_ids(settings.slack_channel_ids)
    allowed_ids = list(dict.fromkeys([*configured, *name_to_id.values()]))

    return resolved, name_to_id, allowed_ids
