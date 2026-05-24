"""Tests for @mention resolution and Slack channel name detection."""

from ekcip_connectors.mentions import MentionSuggestion, resolve_mentions_in_text
from ekcip_orchestration.actions.detector import detect_action_drafts


def _slack_channel(name: str, channel_id: str) -> MentionSuggestion:
    return MentionSuggestion(
        kind="slack_channel",
        mention=f"@{name}",
        label=f"#{name}",
        description=None,
        resolved_text=channel_id,
        metadata={"channel_name": name, "channel_id": channel_id},
    )


def test_resolve_slack_channel_mention() -> None:
    catalog = [_slack_channel("general", "C01234567")]
    text = "Post update to @general about the release"
    assert resolve_mentions_in_text(text, catalog) == "Post update to C01234567 about the release"


def test_detect_slack_action_from_channel_name() -> None:
    drafts = detect_action_drafts(
        "Send a Slack message to @general saying deploy is done",
        slack_channel_names={"general": "C01234567"},
        allowed_slack_channels=["C01234567"],
    )
    assert len(drafts) == 1
    assert drafts[0].payload["channel_id"] == "C01234567"
    assert "general" in drafts[0].preview.lower() or "#general" in drafts[0].preview


def test_jira_key_not_treated_as_slack_channel() -> None:
    drafts = detect_action_drafts(
        "Send Slack to @SCRUM-12 with status",
        slack_channel_names={"scrum-12": "C999"},
        allowed_slack_channels=["C999"],
    )
    assert not any(d.payload.get("channel_id") == "C999" for d in drafts)
