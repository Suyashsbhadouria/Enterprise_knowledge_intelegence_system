"""Tests for source intent and live-fetch architecture."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ekcip_knowledge.cache import RedisKnowledgeCache
from ekcip_knowledge.live_fetch import LiveDataFetcher, _document_to_hit
from ekcip_knowledge.retrieval import KnowledgeRetriever
from ekcip_knowledge.source_intent import infer_live_sources, parse_vector_sources
from ekcip_shared.config import Settings


def test_parse_vector_sources_defaults_to_confluence():
    assert parse_vector_sources("") == ("confluence",)
    assert parse_vector_sources("confluence") == ("confluence",)


def test_infer_live_sources_from_issue_key():
    sources = infer_live_sources("Who owns SCRUM-12?", issue_keys=["SCRUM-12"])
    assert "jira" in sources


def test_infer_live_sources_slack_keyword():
    sources = infer_live_sources("What was posted in Slack about the outage?")
    assert "slack" in sources


def test_infer_live_sources_confluence_page():
    sources = infer_live_sources("Summarize page 12345", page_ids=["12345"])
    assert "confluence" in sources


def test_document_to_hit_marks_live_fetch():
    hit = _document_to_hit(
        {
            "source": "jira",
            "source_id": "SCRUM-1",
            "title": "Test",
            "content": "Body",
            "url": None,
            "metadata": {},
        }
    )
    assert hit.metadata.get("live_fetch") is True


@pytest.mark.asyncio
async def test_live_fetch_uses_redis_cache():
    settings = Settings()
    cache = MagicMock(spec=RedisKnowledgeCache)
    cache.get_hits = AsyncMock(return_value=[_document_to_hit({
        "source": "jira",
        "source_id": "X-1",
        "title": "Cached",
        "content": "cached body",
        "url": None,
        "metadata": {},
    })])
    cache.set_hits = AsyncMock()
    fetcher = LiveDataFetcher(settings, cache)
    hits = await fetcher.fetch(
        "Status of X-1",
        issue_keys=["X-1"],
        sources=frozenset({"jira"}),
    )
    assert len(hits) == 1
    assert hits[0].title == "Cached"
    cache.set_hits.assert_not_awaited()


@pytest.mark.asyncio
async def test_retriever_vector_search_confluence_only():
    settings = Settings(knowledge_vector_sources="confluence", knowledge_top_k=3)
    store = MagicMock()
    store.search = AsyncMock(return_value=[])
    embedding_router = MagicMock()
    embedding_router.embed = AsyncMock(return_value=([0.1, 0.2], "local"))
    live_fetcher = MagicMock()
    live_fetcher.fetch = AsyncMock(return_value=[])

    retriever = KnowledgeRetriever(
        store,
        embedding_router,
        settings=settings,
        live_fetcher=live_fetcher,
    )
    await retriever.retrieve("onboarding docs", issue_keys=["SCRUM-1"])

    store.search.assert_awaited_once()
    assert store.search.await_args.kwargs["sources"] == ["confluence"]
    live_fetcher.fetch.assert_awaited_once()
