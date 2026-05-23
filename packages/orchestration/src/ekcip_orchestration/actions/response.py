"""Assistant messaging when Phase 4 proposes coordination actions."""

import re

from ekcip_orchestration.actions.types import ActionType, ProposedActionDraft

_KNOWLEDGE_QUERY = re.compile(
    r"\b(who|what|which|summarize|summary|status|blocker|assigned|owner|handling|working on)\b",
    re.IGNORECASE,
)


def is_action_primary_request(question: str, drafts: list[ProposedActionDraft]) -> bool:
    """True when the user mainly wants an approved write, not a research answer."""
    if not drafts:
        return False
    if _KNOWLEDGE_QUERY.search(question):
        return False
    action_types = {draft.action_type for draft in drafts}
    write_types = {
        ActionType.SEND_SLACK_MESSAGE,
        ActionType.SCHEDULE_SLACK_MESSAGE,
        ActionType.ADD_JIRA_COMMENT,
        ActionType.UPDATE_ISSUE_STATUS,
        ActionType.CREATE_REMINDER,
    }
    return action_types.issubset(write_types)


def format_action_proposal_reply(drafts: list[ProposedActionDraft]) -> str:
    lines = [
        "I prepared the following action(s) for your approval. "
        "Nothing is sent to Slack or Jira until you approve and execute.",
        "",
    ]
    for index, draft in enumerate(drafts, start=1):
        lines.append(f"{index}. **{draft.action_type.value}** — {draft.preview}")
    lines.extend(
        [
            "",
            "Next step: `POST /v1/actions/{action_id}/approve` with `{\"execute\": true}` "
            "to run, or `{\"execute\": false}` to approve only.",
            "List actions: `GET /v1/actions/conversations/{conversation_id}/actions`.",
        ]
    )
    return "\n".join(lines)
