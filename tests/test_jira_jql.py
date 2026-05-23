from ekcip_connectors.jira_jql import (
    bounded_jql_for_project,
    is_likely_unbounded,
    resolve_sync_jql,
)


def test_unbounded_detection():
    assert is_likely_unbounded("ORDER BY updated DESC") is True
    assert is_likely_unbounded("updated >= -90d ORDER BY updated DESC") is False
    assert is_likely_unbounded('project = "ABC" ORDER BY updated DESC') is False


def test_resolve_sync_jql_uses_project_when_given():
    jql = resolve_sync_jql("ORDER BY updated DESC", default="ORDER BY updated DESC", project_key="REL")
    assert jql == bounded_jql_for_project("REL")


def test_resolve_sync_jql_fixes_unbounded_default():
    jql = resolve_sync_jql(None, default="ORDER BY updated DESC")
    assert "updated >=" in jql
