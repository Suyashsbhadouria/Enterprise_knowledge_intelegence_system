from ekcip_orchestration.actions.detector import detect_action_drafts
from ekcip_orchestration.actions.response import (
    format_action_proposal_reply,
    is_action_primary_request,
)


def test_action_primary_for_at_channel_send():
    question = "send a message to @social telling everyone that i am on leave tomorrow"
    drafts = detect_action_drafts(
        question,
        allowed_slack_channels=["C0B56PL2Z63"],
        slack_channel_names={"social": "C0B56PL2Z63"},
    )
    assert is_action_primary_request(question, drafts) is True


def test_action_primary_for_slack_send():
    question = (
        "Send a Slack message to C01234567 saying 'Can you confirm the rollout time?'"
    )
    drafts = detect_action_drafts(question, allowed_slack_channels=["C01234567"])
    assert is_action_primary_request(question, drafts) is True


def test_not_action_primary_when_asking_who():
    question = "Who is assigned to SCRUM-12 and send a slack update"
    drafts = detect_action_drafts(
        question,
        allowed_slack_channels=["C01234567"],
    )
    assert is_action_primary_request(question, drafts) is False


def test_format_action_proposal_reply_lists_preview():
    question = "Send a Slack message to C01234567 saying 'hello team'"
    drafts = detect_action_drafts(question, allowed_slack_channels=["C01234567"])
    reply = format_action_proposal_reply(drafts)
    assert "approval" in reply.lower()
    assert "hello team" in reply
