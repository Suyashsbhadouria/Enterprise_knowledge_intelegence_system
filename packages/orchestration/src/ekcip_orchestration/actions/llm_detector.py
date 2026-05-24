"""LLM-based action intent detection embedded in the assistant reply."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from ekcip_orchestration.actions.detector import detect_action_drafts
from ekcip_orchestration.actions.types import ActionType, ProposedActionDraft
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

_EKCIP_ACTIONS_BLOCK = re.compile(
    r"```ekcip_actions\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)

ActionIntent = Literal["action", "question", "both", "none"]

_ACTION_PAYLOAD_MODELS: dict[ActionType, type] = {}


def _payload_models() -> dict[ActionType, type]:
    if _ACTION_PAYLOAD_MODELS:
        return _ACTION_PAYLOAD_MODELS
    from ekcip_orchestration.actions.types import (
        AddJiraCommentPayload,
        CreateReminderPayload,
        ScheduleSlackMessagePayload,
        SendSlackMessagePayload,
        UpdateIssueStatusPayload,
    )

    models = {
        ActionType.SEND_SLACK_MESSAGE: SendSlackMessagePayload,
        ActionType.SCHEDULE_SLACK_MESSAGE: ScheduleSlackMessagePayload,
        ActionType.ADD_JIRA_COMMENT: AddJiraCommentPayload,
        ActionType.UPDATE_ISSUE_STATUS: UpdateIssueStatusPayload,
        ActionType.CREATE_REMINDER: CreateReminderPayload,
    }
    _ACTION_PAYLOAD_MODELS.update(models)
    return _ACTION_PAYLOAD_MODELS


@dataclass(frozen=True)
class LlmActionParseResult:
    intent: ActionIntent
    visible_reply: str
    drafts: tuple[ProposedActionDraft, ...]


def build_action_system_prompt(
    *,
    actions_enabled: bool,
    slack_channel_names: dict[str, str],
    allowed_slack_channels: list[str],
) -> str:
    if not actions_enabled:
        return ""

    channel_lines: list[str] = []
    for name, channel_id in sorted(slack_channel_names.items(), key=lambda item: item[0].lower()):
        channel_lines.append(f"  - #{name} (@{name}) -> {channel_id}")
    for channel_id in allowed_slack_channels:
        if channel_id not in slack_channel_names.values():
            channel_lines.append(f"  - {channel_id}")

    channels_section = (
        "\n".join(channel_lines) if channel_lines else "  (no Slack channels resolved — use @name from user message)"
    )

    return f"""
## Coordination actions (Phase 4)

When the user asks you to **perform** something (send Slack, comment on Jira, update status, schedule, remind):
- Do **not** claim the action already happened.
- Explain briefly what you will propose and that they must **approve** before anything runs.
- Append **exactly one** fenced block at the end of your reply (after your user-facing text):

```ekcip_actions
{{"intent":"action|question|both","actions":[...]}}
```

Rules for the JSON block:
- `intent`: `action` if the user mainly wants a write operation; `question` if they only want information; `both` if they want both.
- `actions`: array of objects, each with:
  - `action_type`: one of `send_slack_message`, `schedule_slack_message`, `add_jira_comment`, `update_issue_status`, `create_reminder`
  - `payload`: fields required for that type (e.g. `channel_id` + `text` for Slack send; `issue_key` + `body` for Jira comment)
  - `preview`: short human-readable summary for the approval card
  - `rationale`: optional one-line reason
- For Slack, use `channel_id` from the list below, or resolve `@channelname` to the matching id.
- For `send_slack_message`, `text` must be the exact message to post (written on the user's behalf).

Available Slack channels:
{channels_section}

If no write action is needed, omit the ```ekcip_actions block entirely and set intent implicitly to question.
"""


def _resolve_slack_channel_id(
    raw: str,
    *,
    slack_channel_names: dict[str, str],
    allowed_slack_channels: list[str],
) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if value.upper().startswith("C") and len(value) >= 9:
        return value.upper()
    name = value.lstrip("@#").lower()
    channel_id = slack_channel_names.get(name)
    if channel_id:
        return channel_id
    allowed = set(allowed_slack_channels)
    upper = value.upper()
    if upper in allowed:
        return upper
    return None


def _normalize_action_payload(
    action_type: ActionType,
    payload: dict[str, Any],
    *,
    slack_channel_names: dict[str, str],
    allowed_slack_channels: list[str],
) -> dict[str, Any] | None:
    data = dict(payload)
    if action_type in {ActionType.SEND_SLACK_MESSAGE, ActionType.SCHEDULE_SLACK_MESSAGE, ActionType.CREATE_REMINDER}:
        channel_raw = str(data.get("channel_id") or data.get("channel") or data.get("channel_name") or "")
        channel_id = _resolve_slack_channel_id(
            channel_raw,
            slack_channel_names=slack_channel_names,
            allowed_slack_channels=allowed_slack_channels,
        )
        if channel_id:
            data["channel_id"] = channel_id
        elif action_type != ActionType.CREATE_REMINDER:
            return None

    model = _payload_models().get(action_type)
    if model is None:
        return None
    try:
        validated = model.model_validate(data)
        return validated.model_dump()
    except Exception as exc:
        logger.warning("llm_action_payload_invalid", action_type=action_type.value, error=str(exc)[:200])
        return None


def _drafts_from_llm_actions(
    actions: list[dict[str, Any]],
    *,
    slack_channel_names: dict[str, str],
    allowed_slack_channels: list[str],
) -> list[ProposedActionDraft]:
    drafts: list[ProposedActionDraft] = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        try:
            action_type = ActionType(str(item.get("action_type") or ""))
        except ValueError:
            continue
        raw_payload = item.get("payload")
        if not isinstance(raw_payload, dict):
            continue
        payload = _normalize_action_payload(
            action_type,
            raw_payload,
            slack_channel_names=slack_channel_names,
            allowed_slack_channels=allowed_slack_channels,
        )
        if not payload:
            continue
        preview = str(item.get("preview") or "").strip()
        if not preview:
            preview = f"{action_type.value}: {payload}"
        rationale = item.get("rationale")
        drafts.append(
            ProposedActionDraft(
                action_type=action_type,
                payload=payload,
                preview=preview[:500],
                rationale=str(rationale)[:500] if rationale else None,
            )
        )
    return drafts


def parse_llm_action_response(
    raw_content: str,
    *,
    slack_channel_names: dict[str, str],
    allowed_slack_channels: list[str],
    original_question: str,
    actions_enabled: bool = True,
) -> LlmActionParseResult:
    """Strip ekcip_actions block and convert to proposed action drafts."""
    visible = raw_content.strip()
    intent: ActionIntent = "none"
    drafts: list[ProposedActionDraft] = []

    match = _EKCIP_ACTIONS_BLOCK.search(raw_content)
    if match and actions_enabled:
        visible = (raw_content[: match.start()] + raw_content[match.end() :]).strip()
        try:
            parsed = json.loads(match.group(1).strip())
        except json.JSONDecodeError as exc:
            logger.warning("llm_action_json_parse_failed", error=str(exc)[:200])
            parsed = {}
        if isinstance(parsed, dict):
            raw_intent = str(parsed.get("intent") or "none").lower()
            if raw_intent in {"action", "question", "both"}:
                intent = raw_intent  # type: ignore[assignment]
            actions = parsed.get("actions")
            if isinstance(actions, list):
                drafts = _drafts_from_llm_actions(
                    actions,
                    slack_channel_names=slack_channel_names,
                    allowed_slack_channels=allowed_slack_channels,
                )

    if actions_enabled and not drafts:
        drafts = detect_action_drafts(
            original_question,
            allowed_slack_channels=allowed_slack_channels,
            slack_channel_names=slack_channel_names,
        )
        if drafts and intent == "none":
            intent = "action"

    if intent == "none":
        intent = "question"

    return LlmActionParseResult(
        intent=intent,
        visible_reply=visible,
        drafts=tuple(drafts),
    )


def merge_action_drafts(*groups: list[ProposedActionDraft]) -> list[ProposedActionDraft]:
    seen: set[tuple[str, str]] = set()
    merged: list[ProposedActionDraft] = []
    for group in groups:
        for draft in group:
            key = (draft.action_type.value, json.dumps(draft.payload, sort_keys=True, default=str))
            if key in seen:
                continue
            seen.add(key)
            merged.append(draft)
    return merged
