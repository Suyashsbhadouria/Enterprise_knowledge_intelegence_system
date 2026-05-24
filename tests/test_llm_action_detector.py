"""Tests for LLM action block parsing."""

from ekcip_orchestration.actions.llm_detector import parse_llm_action_response
from ekcip_orchestration.actions.types import ActionType


def test_parse_llm_action_block_send_slack():
    raw = """I'll post that to #social once you approve.

```ekcip_actions
{
  "intent": "action",
  "actions": [
    {
      "action_type": "send_slack_message",
      "payload": {
        "channel_id": "@social",
        "text": "I am on leave tomorrow"
      },
      "preview": "Post to #social: I am on leave tomorrow",
      "rationale": "User requested leave announcement"
    }
  ]
}
```"""
    parsed = parse_llm_action_response(
        raw,
        slack_channel_names={"social": "C0B56PL2Z63"},
        allowed_slack_channels=["C0B56PL2Z63"],
        original_question="send a message to @social telling everyone that i am on leave tomorrow",
    )
    assert parsed.intent == "action"
    assert "approve" in parsed.visible_reply.lower()
    assert "```ekcip_actions" not in parsed.visible_reply
    assert len(parsed.drafts) == 1
    assert parsed.drafts[0].action_type == ActionType.SEND_SLACK_MESSAGE
    assert parsed.drafts[0].payload["channel_id"] == "C0B56PL2Z63"
    assert "on leave tomorrow" in parsed.drafts[0].payload["text"].lower()


def test_parse_falls_back_to_heuristics_without_block():
    parsed = parse_llm_action_response(
        "Sure, I can help with that.",
        slack_channel_names={"social": "C0B56PL2Z63"},
        allowed_slack_channels=["C0B56PL2Z63"],
        original_question="send a message to @social telling everyone that i am on leave tomorrow",
    )
    assert parsed.intent == "action"
    assert len(parsed.drafts) >= 1
