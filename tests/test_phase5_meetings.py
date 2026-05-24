import textwrap
from pathlib import Path

import pytest

from ekcip_connectors.meetings.transcript import (
    chunk_transcript_text,
    file_uri_for_path,
    meeting_documents_from_file,
    parse_transcript,
)


SAMPLE_VTT = textwrap.dedent(
    """\
    WEBVTT

    00:00:01.000 --> 00:00:04.000
    Alice Chen
    We need to unblock the auth rollout.

    00:00:05.000 --> 00:00:08.000
    Bob Smith
    API contract review is still pending.
    """
)

SAMPLE_TXT = textwrap.dedent(
    """\
    Sprint Planning — 2024-05-15

    Alice: We should prioritize SCRUM-12.
    Bob: Confluence page 123456 has the spec.
    """
)


def test_parse_vtt_transcript():
    parsed = parse_transcript(SAMPLE_VTT, filename="standup-2024-05-15.vtt")
    assert parsed.meeting_id == "standup-2024-05-15"
    assert "auth rollout" in parsed.text
    assert "Alice Chen" in parsed.text
    assert parsed.format == "vtt"


def test_parse_plain_text_transcript():
    parsed = parse_transcript(SAMPLE_TXT, filename="sprint-planning.txt")
    assert parsed.title == "Sprint Planning — 2024-05-15"
    assert "SCRUM-12" in parsed.text
    assert parsed.format == "txt"


def test_chunk_transcript_text_splits_long_content():
    body = "word " * 800
    chunks = chunk_transcript_text(body, max_chars=500)
    assert len(chunks) >= 2
    assert all(len(chunk) <= 500 for chunk in chunks)


def test_file_uri_for_path_supports_relative_path(tmp_path: Path):
    path = tmp_path / "standup.txt"
    path.write_text("hello", encoding="utf-8")
    uri = file_uri_for_path(path)
    assert uri is not None
    assert uri.startswith("file:///")


def test_meeting_documents_from_file(tmp_path: Path):
    path = tmp_path / "standup-2024-05-15.vtt"
    path.write_text(SAMPLE_VTT, encoding="utf-8")
    docs = meeting_documents_from_file(path)
    assert len(docs) >= 1
    assert docs[0]["source"] == "meetings"
    assert docs[0]["source_id"].startswith("standup-2024-05-15:")
    assert "auth rollout" in docs[0]["content"]


@pytest.mark.asyncio
async def test_knowledge_status_includes_meetings(client, monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MEETINGS_TRANSCRIPTS_DIR", str(tmp_path))
    from ekcip_shared.config import get_settings

    get_settings.cache_clear()

    response = await client.get("/v1/knowledge/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["meetings_phase"] == 5
    assert "meetings_entities" in data
    assert "meetings_configured" in data


@pytest.mark.asyncio
async def test_meetings_sync_indexes_directory(client, monkeypatch, tmp_path: Path):
    from ekcip_knowledge.embeddings import EmbeddingRouter

    (tmp_path / "standup-2024-05-15.vtt").write_text(SAMPLE_VTT, encoding="utf-8")

    async def mock_embed(self, text: str):
        return [0.1, 0.2, 0.3], "test"

    monkeypatch.setattr(EmbeddingRouter, "embed", mock_embed)
    monkeypatch.setattr(
        "ekcip_api.routes.knowledge.resolve_meetings_directory",
        lambda settings, override=None: tmp_path,
    )

    response = await client.post("/v1/knowledge/meetings/sync", json={})
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "completed"
    assert body["transcripts_indexed"] >= 1

    status = await client.get("/v1/knowledge/status")
    assert status.json()["data"]["meetings_entities"] >= 1
