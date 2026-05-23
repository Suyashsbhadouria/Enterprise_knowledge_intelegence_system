"""Bounded GitHub repo list helpers (Phase 2)."""

import re

_REPO_PATTERN = re.compile(r"^[\w.-]+/[\w.-]+$")


def parse_repo_list(raw: str) -> list[str]:
    repos: list[str] = []
    for part in raw.split(","):
        normalized = part.strip()
        if not normalized:
            continue
        if not _REPO_PATTERN.match(normalized):
            raise ValueError(
                f"Invalid GitHub repo '{normalized}'. Use owner/repo format, e.g. acme/platform."
            )
        if normalized not in repos:
            repos.append(normalized)
    return repos


def resolve_sync_repos(requested: str | None, *, default: str) -> list[str]:
    raw = (requested or default).strip()
    if not raw:
        raise ValueError(
            "GitHub sync requires at least one repo. Set GITHUB_REPOS=owner/repo or pass repos in the body."
        )
    return parse_repo_list(raw)
