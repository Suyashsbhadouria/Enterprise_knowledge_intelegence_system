from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ekcip_knowledge.plugin import KnowledgePlugin
from ekcip_knowledge.types import Citation, RetrievalHit
from ekcip_llm.types import LlmCompletionResult
from ekcip_orchestration.qa_graph import QaGraphRunner


@pytest.mark.asyncio
async def test_qa_graph_returns_answer_with_citations():
    hit = RetrievalHit(
        chunk_id=uuid4(),
        source="jira",
        source_id="PROJ-1",
        title="Auth task",
        content="Status: In Progress. Assignee: Alex.",
        url="https://jira.example/browse/PROJ-1",
        score=0.9,
    )
    citation = Citation(
        source="jira",
        source_id="PROJ-1",
        title="Auth task",
        url=hit.url,
        excerpt=hit.content[:100],
        score=0.9,
    )

    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=([hit], [citation]))
    plugin = KnowledgePlugin(retriever)

    llm_router = MagicMock()
    llm_router.configured_providers.return_value = ["gemini"]
    llm_router.complete = AsyncMock(
        return_value=LlmCompletionResult(
            content="PROJ-1 is in progress and assigned to Alex.",
            provider="gemini",
            model="gemini-2.0-flash",
        )
    )

    runner = QaGraphRunner(plugin, llm_router)
    result = await runner.run(question="What is the status of PROJ-1?")

    assert "PROJ-1" in result.answer
    assert result.phase == "3-qa"
    assert len(result.citations) == 1
    assert result.issue_keys == ["PROJ-1"]
