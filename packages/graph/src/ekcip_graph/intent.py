"""Lightweight intent classification for graph query routing (Phase 3)."""

import re
from dataclasses import dataclass

ISSUE_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
PROJECT_KEY_PATTERN = re.compile(
    r"\bproject\s+([A-Z][A-Z0-9]{1,9})\b",
    re.IGNORECASE,
)
BLOCKER_PATTERN = re.compile(
    r"\b(blockers?|blocked|impediment|stuck|blocking)\b",
    re.IGNORECASE,
)
ASSIGNEE_PATTERN = re.compile(
    r"\b(who\s+(?:owns|handles|is\s+working\s+on)|assignee|owner)\b",
    re.IGNORECASE,
)
SUMMARY_PATTERN = re.compile(
    r"\b(summarize|summary|overview|all\s+issues|status\s+of)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GraphIntent:
    issue_keys: tuple[str, ...]
    project_keys: tuple[str, ...]
    wants_blockers: bool
    wants_assignee: bool
    wants_project_overview: bool

    @property
    def use_graph(self) -> bool:
        return bool(
            self.issue_keys
            or self.project_keys
            or self.wants_blockers
            or self.wants_assignee
            or self.wants_project_overview
        )


def classify_graph_intent(question: str, *, issue_keys: list[str] | None = None) -> GraphIntent:
    keys = tuple(dict.fromkeys(issue_keys or ISSUE_KEY_PATTERN.findall(question)))
    project_keys = tuple(
        dict.fromkeys(
            key.upper()
            for key in PROJECT_KEY_PATTERN.findall(question)
            if key.upper() not in {k.split("-")[0] for k in keys}
        )
    )
    wants_blockers = bool(BLOCKER_PATTERN.search(question))
    wants_assignee = bool(ASSIGNEE_PATTERN.search(question))
    wants_project_overview = bool(SUMMARY_PATTERN.search(question)) or bool(project_keys)
    return GraphIntent(
        issue_keys=keys,
        project_keys=project_keys,
        wants_blockers=wants_blockers,
        wants_assignee=wants_assignee,
        wants_project_overview=wants_project_overview,
    )
