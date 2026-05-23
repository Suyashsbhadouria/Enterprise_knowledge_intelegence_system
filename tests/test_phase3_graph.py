from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ekcip_graph.retriever import GraphRetriever, format_graph_context
from ekcip_graph.types import GraphRetrievalResult, GraphSnippet
from ekcip_knowledge.plugin import KnowledgePlugin
from ekcip_knowledge.types import Citation, RetrievalHit
from ekcip_llm.types import LlmCompletionResult
from ekcip_orchestration.qa_graph import QaGraphRunner
from ekcip_shared.config import Settings


@pytest.mark.asyncio
async def test_qa_graph_phase3_merges_graph_context():
    hit = RetrievalHit(
        chunk_id=uuid4(),
        source="jira",
        source_id="SCRUM-1",
        title="Blocked auth",
        content="Status: Blocked. Assignee: Alex.",
        url="https://jira.example/browse/SCRUM-1",
        score=0.85,
        metadata={"status": "Blocked", "assignee": "Alex"},
    )
    citation = Citation(
        source="jira",
        source_id="SCRUM-1",
        title="Blocked auth",
        url=hit.url,
        excerpt=hit.content[:100],
        score=0.85,
    )

    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=([hit], [citation]))
    plugin = KnowledgePlugin(retriever)

    graph_result = GraphRetrievalResult(
        snippets=(
            GraphSnippet(
                kind="issue",
                label="Jira SCRUM-1",
                detail="Issue SCRUM-1: Blocked auth in project SCRUM: status=Blocked, assignee=Alex.",
                source_ids=("SCRUM-1",),
            ),
        ),
        query_modes=("local_issue",),
        node_count=42,
    )
    graph_retriever = MagicMock()
    graph_retriever.retrieve = AsyncMock(return_value=graph_result)

    llm_router = MagicMock()
    llm_router.configured_providers.return_value = ["gemini"]
    llm_router.complete = AsyncMock(
        return_value=LlmCompletionResult(
            content="SCRUM-1 is blocked and assigned to Alex per the graph.",
            provider="gemini",
            model="gemini-2.0-flash",
        )
    )

    runner = QaGraphRunner(plugin, llm_router, graph_retriever)
    result = await runner.run(question="Who owns SCRUM-1 and are there blockers?")

    assert result.phase == "3-qa"
    assert "SCRUM-1" in result.answer
    assert result.graph_modes == ["local_issue"]
    graph_retriever.retrieve.assert_awaited_once()


def test_format_graph_context_empty():
    text = format_graph_context(GraphRetrievalResult(snippets=(), query_modes=()))
    assert "No graph relationships" in text


@pytest.mark.asyncio
async def test_graph_retriever_skips_when_unconfigured():
    settings = Settings(neo4j_uri="", neo4j_password=None)
    from ekcip_graph.intent import classify_graph_intent

    intent = classify_graph_intent("Status of SCRUM-1", issue_keys=["SCRUM-1"])
    retriever = GraphRetriever(settings)
    result = await retriever.retrieve(intent)
    assert not result.has_data
