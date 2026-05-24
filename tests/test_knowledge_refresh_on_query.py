from unittest.mock import MagicMock

import pytest

from ekcip_api.services.knowledge_refresh import (
    parse_query_references,
    refresh_knowledge_for_query,
)
from ekcip_shared.config import Settings


def test_parse_query_references_extracts_ids():
    refs = parse_query_references(
        "Check SCRUM-12 and page 12345, acme/app#7, C01234567890:1234567890.123456"
    )
    assert "SCRUM-12" in refs.issue_keys
    assert "12345" in refs.page_ids
    assert any("acme/app#7" in ref for ref in refs.github_refs)


@pytest.mark.asyncio
async def test_refresh_knowledge_for_query_always_disabled():
    settings = Settings(knowledge_refresh_on_query=True)
    session = MagicMock()
    result = await refresh_knowledge_for_query(session, settings, "Status of SCRUM-1?")
    assert result["status"] == "disabled"
