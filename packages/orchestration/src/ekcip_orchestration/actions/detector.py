"""Heuristic detection of coordination actions from user messages (Phase 4)."""

import re
from datetime import datetime, timedelta, timezone

from ekcip_graph.intent import ISSUE_KEY_PATTERN
from ekcip_orchestration.actions.types import ActionType, ProposedActionDraft

_SLACK_CHANNEL_PATTERN = re.compile(r"\b(C[A-Z0-9]{8,})\b")
_SLACK_SEND = re.compile(
    r"\b(send|post|notify|message|slack)\b.*\b(slack|channel|team)\b|\b(slack)\b.*\b(send|post|message)\b",
    re.IGNORECASE,
)
_SLACK_SCHEDULE = re.compile(
    r"\b(schedule|later|delay)\b.*\b(slack|message)\b|\b(slack)\b.*\b(schedule|later)\b",
    re.IGNORECASE,
)
_JIRA_COMMENT = re.compile(
    r"\b(comment|note|reply)\b.*\b(on|to|for)\b",
    re.IGNORECASE,
)
_JIRA_STATUS = re.compile(
    r"\b(update|change|set|move|transition)\b.*\b(status)\b",
    re.IGNORECASE,
)
_REMINDER = re.compile(r"\b(remind|reminder|ping)\b", re.IGNORECASE)
_QUOTED_TEXT = re.compile(r'["\']([^"\']{3,2000})["\']')
_SAYING_TEXT = re.compile(r"\b(?:saying|message|text)[:\s]+(.+?)(?:\.|$)", re.IGNORECASE)
_STATUS_NAME = re.compile(
    r"\b(?:to|as)\s+[\"']?([A-Za-z][\w\s\-]{1,40})[\"']?",
    re.IGNORECASE,
)
_MINUTES_LATER = re.compile(r"\bin\s+(\d+)\s+minutes?\b", re.IGNORECASE)
_HOURS_LATER = re.compile(r"\bin\s+(\d+)\s+hours?\b", re.IGNORECASE)


def _extract_message_text(question: str, answer: str) -> str:
    for pattern in (_QUOTED_TEXT, _SAYING_TEXT):
        match = pattern.search(question)
        if match:
            return match.group(1).strip()
    if answer:
        summary = answer.split("\n\n")[0].strip()
        if len(summary) > 40:
            return summary[:1500]
    return question.strip()[:500]


def _resolve_channel(question: str, allowed_channels: list[str]) -> str | None:
    found = _SLACK_CHANNEL_PATTERN.findall(question.upper())
    for channel_id in found:
        if channel_id in allowed_channels:
            return channel_id
    return allowed_channels[0] if allowed_channels else None


def _parse_schedule_time(question: str) -> int | None:
    now = datetime.now(timezone.utc)
    minute_match = _MINUTES_LATER.search(question)
    if minute_match:
        delta = timedelta(minutes=int(minute_match.group(1)))
        return int((now + delta).timestamp())
    hour_match = _HOURS_LATER.search(question)
    if hour_match:
        delta = timedelta(hours=int(hour_match.group(1)))
        return int((now + delta).timestamp())
    return int((now + timedelta(hours=1)).timestamp())


def detect_action_drafts(
    question: str,
    *,
    answer: str = "",
    allowed_slack_channels: list[str] | None = None,
    actions_enabled: bool = True,
) -> list[ProposedActionDraft]:
    if not actions_enabled:
        return []

    allowed = list(allowed_slack_channels or [])
    issue_keys = list(dict.fromkeys(ISSUE_KEY_PATTERN.findall(question)))
    drafts: list[ProposedActionDraft] = []
    message_text = _extract_message_text(question, answer)

    if _SLACK_SEND.search(question) and allowed:
        channel_id = _resolve_channel(question, allowed)
        if channel_id and message_text:
            drafts.append(
                ProposedActionDraft(
                    action_type=ActionType.SEND_SLACK_MESSAGE,
                    payload={
                        "channel_id": channel_id,
                        "text": message_text,
                    },
                    preview=f"Post to Slack channel {channel_id}: {message_text[:240]}",
                    rationale="User asked to send a Slack message.",
                )
            )

    if _SLACK_SCHEDULE.search(question) and allowed:
        channel_id = _resolve_channel(question, allowed)
        post_at = _parse_schedule_time(question)
        if channel_id and message_text and post_at:
            when = datetime.fromtimestamp(post_at, tz=timezone.utc).isoformat()
            drafts.append(
                ProposedActionDraft(
                    action_type=ActionType.SCHEDULE_SLACK_MESSAGE,
                    payload={
                        "channel_id": channel_id,
                        "text": message_text,
                        "post_at": post_at,
                    },
                    preview=f"Schedule Slack message in {channel_id} at {when}: {message_text[:200]}",
                    rationale="User asked to schedule a Slack message.",
                )
            )

    if _JIRA_COMMENT.search(question) and issue_keys:
        issue_key = issue_keys[0]
        body = message_text or f"Follow-up from EKCIP coordination: {question[:400]}"
        drafts.append(
            ProposedActionDraft(
                action_type=ActionType.ADD_JIRA_COMMENT,
                payload={"issue_key": issue_key, "body": body},
                preview=f"Comment on {issue_key}: {body[:240]}",
                rationale="User asked to add a Jira comment.",
            )
        )

    if _JIRA_STATUS.search(question) and issue_keys:
        issue_key = issue_keys[0]
        status_match = _STATUS_NAME.search(question)
        status_name = status_match.group(1).strip() if status_match else "In Progress"
        drafts.append(
            ProposedActionDraft(
                action_type=ActionType.UPDATE_ISSUE_STATUS,
                payload={"issue_key": issue_key, "status_name": status_name},
                preview=f"Transition {issue_key} to status '{status_name}'",
                rationale="User asked to update Jira issue status.",
            )
        )

    if _REMINDER.search(question):
        remind_at = _parse_schedule_time(question)
        channel_id = _resolve_channel(question, allowed) if allowed else None
        drafts.append(
            ProposedActionDraft(
                action_type=ActionType.CREATE_REMINDER,
                payload={
                    "message": message_text,
                    "remind_at": remind_at,
                    "channel_id": channel_id,
                },
                preview=f"Reminder at {datetime.fromtimestamp(remind_at, tz=timezone.utc).isoformat()}: {message_text[:200]}",
                rationale="User asked for a reminder.",
            )
        )

    return drafts
