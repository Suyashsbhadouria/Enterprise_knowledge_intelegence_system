"""Resolve Nexus fixture issue keys to live Jira keys before writes."""

from __future__ import annotations

from ekcip_connectors.fixtures.enterprise_publish import index_existing_nexus_issues
from ekcip_connectors.runtime.jira import JiraConnector
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


async def _issue_exists(jira: JiraConnector, issue_key: str) -> bool:
    try:
        await jira.get_issue(issue_key)
        return True
    except RuntimeError as exc:
        if "404" in str(exc):
            return False
        raise


async def resolve_jira_issue_key(
    jira: JiraConnector,
    issue_key: str,
    *,
    nexus_label: str | None,
) -> str:
    """Return a Jira key that exists in the tenant.

    Accepts live keys (SCRUM-42) or Nexus fixture keys (ACME-205) when matching
    published issues carry summary prefix ``[Nexus ACME-205]`` and the demo label.
    """
    candidate = issue_key.strip()
    if not candidate:
        raise ValueError("issue_key is required")

    if await _issue_exists(jira, candidate):
        return candidate

    fixture_upper = candidate.upper()
    if not nexus_label:
        raise ValueError(
            f"Jira issue '{candidate}' does not exist. "
            "Use a real issue key from your Jira project, or publish Nexus demo data first."
        )

    issues = await jira.search_issues_by_label(nexus_label, max_results=200)
    key_map = index_existing_nexus_issues(issues)
    resolved = key_map.get(fixture_upper)
    if resolved:
        logger.info(
            "jira_issue_key_resolved",
            fixture_key=fixture_upper,
            live_key=resolved,
        )
        return resolved

    published = ", ".join(sorted(key_map.keys())[:8])
    suffix = "…" if len(key_map) > 8 else ""
    raise ValueError(
        f"Jira issue '{candidate}' does not exist and no published Nexus issue matches "
        f"fixture key '{fixture_upper}'. "
        f"Run POST /v1/admin/publish-enterprise, or use a live key from Jira. "
        f"Published fixture keys: {published or 'none'}{suffix}"
    )
