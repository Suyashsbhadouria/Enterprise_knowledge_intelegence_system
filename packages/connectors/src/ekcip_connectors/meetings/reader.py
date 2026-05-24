"""Discover transcript files on disk for bounded sync."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ekcip_connectors.meetings.transcript import SUPPORTED_EXTENSIONS


def list_transcript_files(
    directory: Path,
    *,
    days: int = 90,
    max_files: int = 100,
) -> list[Path]:
    if not directory.is_dir():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    candidates: list[tuple[float, Path]] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            continue
        candidates.append((mtime.timestamp(), path))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in candidates[:max_files]]
