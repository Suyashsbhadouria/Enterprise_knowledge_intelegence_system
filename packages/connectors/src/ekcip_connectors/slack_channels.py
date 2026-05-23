"""Slack channel ID helpers for bounded history ingest (Phase 2)."""

import re

_CHANNEL_ID_PATTERN = re.compile(r"^C[A-Z0-9]{8,}$")


def parse_channel_ids(raw: str) -> list[str]:
    channels: list[str] = []
    for part in raw.split(","):
        normalized = part.strip().upper()
        if not normalized:
            continue
        if not _CHANNEL_ID_PATTERN.match(normalized):
            raise ValueError(
                f"Invalid Slack channel id '{part.strip()}'. "
                "Use public channel IDs like C01234567 from Slack channel details."
            )
        if normalized not in channels:
            channels.append(normalized)
    return channels


def resolve_sync_channels(requested: str | None, *, default: str) -> list[str]:
    raw = (requested or default).strip()
    if not raw:
        raise ValueError(
            "Slack sync requires channel IDs. Set SLACK_CHANNEL_IDS=C01234567,... "
            "or pass channel_ids in the body."
        )
    return parse_channel_ids(raw)
