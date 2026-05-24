import pytest

from ekcip_connectors.jira_issue_resolve import resolve_jira_issue_key


class FakeJira:
    def __init__(
        self,
        *,
        existing: set[str] | None = None,
        nexus_issues: list[dict] | None = None,
    ) -> None:
        self.existing = {key.upper() for key in (existing or set())}
        self.nexus_issues = nexus_issues or []

    async def get_issue(self, issue_key: str) -> dict:
        if issue_key.upper() not in self.existing:
            raise RuntimeError(f"Jira get_issue failed: HTTP 404")
        return {"key": issue_key}

    async def search_issues_by_label(self, label: str, *, max_results: int = 100) -> list[dict]:
        return self.nexus_issues


@pytest.mark.asyncio
async def test_resolve_returns_live_key_when_it_exists():
    jira = FakeJira(existing={"SCRUM-42"})
    resolved = await resolve_jira_issue_key(jira, "SCRUM-42", nexus_label="nexus-dynamics-demo")
    assert resolved == "SCRUM-42"


@pytest.mark.asyncio
async def test_resolve_maps_nexus_fixture_key():
    jira = FakeJira(
        nexus_issues=[
            {
                "key": "SCRUM-99",
                "fields": {"summary": "[Nexus ACME-205] Meridian cutover risk"},
            }
        ]
    )
    resolved = await resolve_jira_issue_key(jira, "ACME-205", nexus_label="nexus-dynamics-demo")
    assert resolved == "SCRUM-99"


@pytest.mark.asyncio
async def test_resolve_raises_when_fixture_not_published():
    jira = FakeJira(nexus_issues=[])
    with pytest.raises(ValueError, match="ACME-205"):
        await resolve_jira_issue_key(jira, "ACME-205", nexus_label="nexus-dynamics-demo")
