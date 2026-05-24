"""Parse Teams / Google Meet / plain-text meeting transcript exports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = {".txt", ".md", ".vtt", ".srt"}
VTT_TIMESTAMP = re.compile(
    r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\s*$"
)
SRT_TIMESTAMP = re.compile(
    r"^\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}\s*$"
)
SRT_INDEX = re.compile(r"^\d+$")
MARKDOWN_HEADING = re.compile(r"^#\s+(.+)$")


@dataclass(frozen=True)
class ParsedTranscript:
    meeting_id: str
    title: str
    text: str
    format: str
    filename: str


def _meeting_id_from_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    normalized = re.sub(r"[^\w.-]+", "-", stem.lower()).strip("-")
    return normalized or "meeting"


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return stem or "Meeting transcript"


def chunk_transcript_text(text: str, *, max_chars: int = 2000) -> list[str]:
    normalized = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    paragraphs = [part.strip() for part in normalized.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        start = 0
        while start < len(paragraph):
            chunks.append(paragraph[start : start + max_chars].strip())
            start += max_chars
        current = ""
    if current:
        chunks.append(current)
    return chunks


def _parse_vtt(raw: str) -> str:
    lines = raw.splitlines()
    utterances: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line or line.upper() == "WEBVTT" or line.startswith("NOTE"):
            continue
        if VTT_TIMESTAMP.match(line):
            cue_lines: list[str] = []
            while index < len(lines) and lines[index].strip():
                cue_lines.append(lines[index].strip())
                index += 1
            if cue_lines:
                utterances.append(" ".join(cue_lines))
            continue
        utterances.append(line)
    return "\n".join(utterances)


def _parse_srt(raw: str) -> str:
    lines = raw.splitlines()
    utterances: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        if SRT_INDEX.match(line):
            if index < len(lines) and SRT_TIMESTAMP.match(lines[index].strip()):
                index += 1
                cue_lines: list[str] = []
                while index < len(lines) and lines[index].strip():
                    cue_lines.append(lines[index].strip())
                    index += 1
                if cue_lines:
                    utterances.append(" ".join(cue_lines))
            continue
        if SRT_TIMESTAMP.match(line):
            cue_lines = []
            while index < len(lines) and lines[index].strip():
                cue_lines.append(lines[index].strip())
                index += 1
            if cue_lines:
                utterances.append(" ".join(cue_lines))
    return "\n".join(utterances)


def _parse_markdown(raw: str, *, fallback_title: str) -> tuple[str, str]:
    title = fallback_title
    body_lines: list[str] = []
    for line in raw.splitlines():
        heading = MARKDOWN_HEADING.match(line.strip())
        if heading and not body_lines:
            title = heading.group(1).strip()
            continue
        body_lines.append(line)
    return title, "\n".join(body_lines).strip()


def _parse_plain_text(raw: str, *, fallback_title: str) -> tuple[str, str]:
    lines = raw.splitlines()
    if not lines:
        return fallback_title, ""
    first = lines[0].strip()
    if first and len(first) <= 120 and not first.endswith(":"):
        return first, "\n".join(lines[1:]).strip()
    return fallback_title, raw.strip()


def parse_transcript(raw: str, *, filename: str) -> ParsedTranscript:
    suffix = Path(filename).suffix.lower()
    meeting_id = _meeting_id_from_filename(filename)
    fallback_title = _title_from_filename(filename)

    if suffix == ".vtt":
        text = _parse_vtt(raw)
        title = fallback_title
        fmt = "vtt"
    elif suffix == ".srt":
        text = _parse_srt(raw)
        title = fallback_title
        fmt = "srt"
    elif suffix == ".md":
        title, text = _parse_markdown(raw, fallback_title=fallback_title)
        fmt = "md"
    else:
        title, text = _parse_plain_text(raw, fallback_title=fallback_title)
        fmt = "txt"

    return ParsedTranscript(
        meeting_id=meeting_id,
        title=title,
        text=text,
        format=fmt,
        filename=filename,
    )


def file_uri_for_path(path: Path) -> str | None:
    """Absolute file:// URI for citations; None if the path cannot be expressed as a URI."""
    try:
        return path.resolve().as_uri()
    except ValueError:
        return None


def meeting_documents_from_file(
    path: Path,
    *,
    max_chars: int = 2000,
) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    file_url = file_uri_for_path(path)
    parsed = parse_transcript(raw, filename=path.name)
    if not parsed.text.strip():
        return []

    chunks = chunk_transcript_text(parsed.text, max_chars=max_chars)
    documents: list[dict[str, Any]] = []
    for chunk_index, chunk in enumerate(chunks):
        documents.append(
            {
                "source": "meetings",
                "source_id": f"{parsed.meeting_id}:{chunk_index}",
                "title": parsed.title,
                "content": chunk,
                "url": file_url,
                "metadata": {
                    "meeting_id": parsed.meeting_id,
                    "format": parsed.format,
                    "filename": parsed.filename,
                    "chunk_index": chunk_index,
                    "chunk_total": len(chunks),
                },
            }
        )
    return documents
