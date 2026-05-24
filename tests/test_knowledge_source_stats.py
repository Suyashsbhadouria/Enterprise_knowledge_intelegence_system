from ekcip_api.services.knowledge_source_stats import (
    KnowledgeSourceStatsSnapshot,
    apply_entity_counts,
    update_stats_after_sync,
)


def test_update_stats_after_sync_uses_entity_counts():
    current = KnowledgeSourceStatsSnapshot(jira_entities=1, confluence_entities=2)
    updated = update_stats_after_sync(
        current,
        "jira",
        {"issues_indexed": 42, "status": "completed"},
    )
    assert updated.jira_entities == 42
    assert updated.confluence_entities == 2
    assert updated.synced_at is not None


def test_apply_entity_counts_updates_selected_sources():
    current = KnowledgeSourceStatsSnapshot()
    updated = apply_entity_counts(current, jira=10, meetings=3)
    assert updated.jira_entities == 10
    assert updated.meetings_entities == 3
    assert updated.github_entities == 0
