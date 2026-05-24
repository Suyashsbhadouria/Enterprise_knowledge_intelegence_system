"""Shared mention suggestion and resolution types."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MENTION_AT_PATTERN = re.compile(r"@([a-zA-Z0-9][a-zA-Z0-9_./-]*)")


@dataclass(frozen=True)
class MentionSuggestion:
    kind: str
    mention: str
    label: str
    description: str | None
    resolved_text: str
    metadata: dict[str, Any]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "mention": self.mention,
            "label": self.label,
            "description": self.description,
            "resolved_text": self.resolved_text,
            "metadata": self.metadata,
        }


def normalize_mention_query(text: str) -> str:
    return text.strip().lower()


def filter_suggestions(
    items: list[MentionSuggestion],
    query: str,
    *,
    limit: int = 25,
) -> list[MentionSuggestion]:
    if not query.strip():
        return items[:limit]
    needle = normalize_mention_query(query)
    scored: list[tuple[int, MentionSuggestion]] = []
    for item in items:
        haystacks = (
            normalize_mention_query(item.mention.lstrip("@")),
            normalize_mention_query(item.label),
            normalize_mention_query(item.description or ""),
        )
        if not any(needle in h for h in haystacks):
            continue
        rank = 0
        primary = haystacks[0]
        if primary.startswith(needle):
            rank -= 2
        elif primary == needle:
            rank -= 3
        scored.append((rank, item))
    scored.sort(key=lambda pair: (pair[0], pair[1].label.lower()))
    return [item for _, item in scored[:limit]]


def resolve_mentions_in_text(text: str, catalog: list[MentionSuggestion]) -> str:
    """Replace @mentions with connector-native tokens (channel ids, issue keys, etc.)."""
    if not text or not catalog:
        return text
    pairs = sorted(
        {item.mention: item.resolved_text for item in catalog if item.mention}.items(),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    resolved = text
    for mention, replacement in pairs:
        resolved = re.sub(
            re.escape(mention) + r"(?=\s|$|[,.!?])",
            replacement,
            resolved,
            flags=re.IGNORECASE,
        )
    return resolved
