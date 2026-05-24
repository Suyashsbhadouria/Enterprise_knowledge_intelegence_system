"""Publish Nexus Dynamics fixture content to live Jira, Confluence, and Slack."""

from __future__ import annotations

import asyncio
import re
from html import escape
from typing import Any

from ekcip_connectors.fixtures.enterprise_catalog import (
    ENTERPRISE_MANIFEST,
    build_confluence_documents,
    build_jira_documents,
    build_slack_message_batches,
)
from ekcip_connectors.runtime.confluence import ConfluenceConnector
from ekcip_connectors.runtime.jira import JiraConnector
from ekcip_connectors.runtime.slack import SlackConnector
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

NEXUS_SUMMARY_PREFIX = re.compile(r"^\[Nexus ([A-Z][A-Z0-9]+-\d+)\]\s*", re.IGNORECASE)
CONFLUENCE_TITLE_PREFIX = re.compile(r"^\[Nexus (\d+)\]\s*", re.IGNORECASE)
ISSUE_KEY_IN_TEXT = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def parse_csv_map(raw: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for part in (raw or "").split(","):
        piece = part.strip()
        if ":" not in piece:
            continue
        left, right = piece.split(":", 1)
        mapping[left.strip().upper()] = right.strip()
    return mapping


def resolve_jira_project_map(settings: Settings) -> dict[str, str]:
    mapping = parse_csv_map(settings.enterprise_publish_jira_project_map)
    if not mapping:
        raise ValueError(
            "Set ENTERPRISE_PUBLISH_JIRA_PROJECT_MAP, e.g. "
            "CORE:SCRUM,ACME:SCRUM,MERID:SCRUM,OPS:SCRUM (your real Jira project keys)."
        )
    return mapping


def resolve_confluence_space_map(settings: Settings) -> dict[str, str]:
    mapping = parse_csv_map(settings.enterprise_publish_confluence_space_map)
    if mapping:
        return mapping
    # Default: same keys as fixture spaces if they exist in the tenant
    return {key: key for key in ENTERPRISE_MANIFEST["confluence_spaces"]}


def resolve_slack_channel_map(settings: Settings) -> dict[str, str]:
    explicit = parse_csv_map(settings.enterprise_publish_slack_channel_map)
    if explicit:
        return explicit
    from ekcip_connectors.slack_channels import parse_channel_ids

    fixture_ids = [str(ch["id"]) for ch in ENTERPRISE_MANIFEST["slack_channels"]]
    real_ids = parse_channel_ids(settings.slack_channel_ids)
    if len(real_ids) < len(fixture_ids):
        raise ValueError(
            f"Need {len(fixture_ids)} Slack channel IDs in SLACK_CHANNEL_IDS or set "
            "ENTERPRISE_PUBLISH_SLACK_CHANNEL_MAP (fixture_id:real_id)."
        )
    return dict(zip(fixture_ids, real_ids[: len(fixture_ids)], strict=True))


def text_to_storage_html(text: str) -> str:
    paragraphs = [escape(part.strip()) for part in text.split("\n\n") if part.strip()]
    if not paragraphs:
        return "<p>(empty)</p>"
    return "".join(f"<p>{part}</p>" for part in paragraphs)


def apply_issue_key_map(text: str, key_map: dict[str, str]) -> str:
    if not key_map:
        return text

    def replacer(match: re.Match[str]) -> str:
        fixture_key = match.group(1).upper()
        return key_map.get(fixture_key, fixture_key)

    return ISSUE_KEY_IN_TEXT.sub(replacer, text)


def index_existing_nexus_issues(
    issues: list[dict[str, Any]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for issue in issues:
        fields = issue.get("fields") or {}
        summary = str(fields.get("summary") or "")
        match = NEXUS_SUMMARY_PREFIX.match(summary)
        if match and issue.get("key"):
            mapping[match.group(1).upper()] = str(issue["key"])
    return mapping


async def publish_nexus_to_live(
    *,
    jira: JiraConnector,
    confluence: ConfluenceConnector | None,
    slack: SlackConnector | None,
    settings: Settings,
    dry_run: bool = False,
) -> dict[str, Any]:
    project_map = resolve_jira_project_map(settings)
    space_map = resolve_confluence_space_map(settings)
    channel_map = resolve_slack_channel_map(settings)
    label = settings.enterprise_publish_jira_label

    existing = index_existing_nexus_issues(
        await jira.search_issues_by_label(label, max_results=200)
    )
    key_map: dict[str, str] = dict(existing)
    page_map: dict[str, str] = {}
    jira_created: list[dict[str, str]] = []
    jira_skipped: list[str] = []
    jira_errors: list[dict[str, str]] = []
    confluence_created: list[dict[str, str]] = []
    confluence_skipped: list[str] = []
    confluence_errors: list[dict[str, str]] = []
    slack_posted: list[dict[str, str]] = []
    slack_errors: list[dict[str, str]] = []

    for document in build_jira_documents():
        fixture_key = str(document["source_id"]).upper()
        fixture_project = str((document.get("metadata") or {}).get("project", "")).upper()
        target_project = project_map.get(fixture_project)
        if not target_project:
            jira_errors.append(
                {
                    "fixture_key": fixture_key,
                    "error": f"No Jira project mapping for {fixture_project}",
                }
            )
            continue
        if fixture_key in key_map:
            jira_skipped.append(fixture_key)
            continue

        summary = f"[Nexus {fixture_key}] {document['title']}"
        status = str((document.get("metadata") or {}).get("status") or "")
        description = (
            f"{document['content']}\n\n"
            f"---\nFixture key: {fixture_key} | Nexus Dynamics enterprise demo | "
            f"Label: {label}"
        )
        if dry_run:
            jira_created.append(
                {"fixture_key": fixture_key, "dry_run": "true", "project": target_project}
            )
            key_map[fixture_key] = f"DRY-{fixture_key}"
            continue

        try:
            created = await jira.create_issue(
                project_key=target_project,
                summary=summary,
                description=description,
                labels=[label],
            )
            real_key = str(created.get("key") or "")
            if not real_key:
                raise RuntimeError("Jira create_issue returned no key")
            key_map[fixture_key] = real_key
            jira_created.append({"fixture_key": fixture_key, "issue_key": real_key})
            if status and status not in {"To Do", "Open", "Backlog"}:
                try:
                    await jira.transition_issue(real_key, status)
                except Exception as exc:
                    logger.warning(
                        "nexus_publish_status_transition_failed",
                        issue_key=real_key,
                        status=status,
                        error=str(exc),
                    )
            await asyncio.sleep(0.35)
        except Exception as exc:
            jira_errors.append({"fixture_key": fixture_key, "error": str(exc)[:500]})

    if confluence is not None:
        for document in build_confluence_documents():
            fixture_page_id = str(document["source_id"])
            meta = document.get("metadata") or {}
            fixture_space = str(meta.get("space_key", "")).upper()
            target_space = space_map.get(fixture_space, fixture_space)
            title = f"[Nexus {fixture_page_id}] {document['title']}"

            if not dry_run:
                existing_page = await confluence.find_page_by_title(target_space, title)
                if existing_page:
                    real_id = str(existing_page.get("id", ""))
                    page_map[fixture_page_id] = real_id
                    confluence_skipped.append(fixture_page_id)
                    continue

            body_html = text_to_storage_html(
                apply_issue_key_map(str(document.get("content") or ""), key_map)
            )
            if dry_run:
                confluence_created.append(
                    {"fixture_page_id": fixture_page_id, "dry_run": "true", "space": target_space}
                )
                page_map[fixture_page_id] = f"DRY-{fixture_page_id}"
                continue

            try:
                page = await confluence.create_page(
                    space_key=target_space,
                    title=title,
                    body_html=body_html,
                )
                real_id = str(page.get("id", ""))
                page_map[fixture_page_id] = real_id
                confluence_created.append(
                    {"fixture_page_id": fixture_page_id, "page_id": real_id, "space": target_space}
                )
                await asyncio.sleep(0.35)
            except Exception as exc:
                confluence_errors.append(
                    {"fixture_page_id": fixture_page_id, "error": str(exc)[:500]}
                )

    if slack is not None:
        for channel_id, channel_name, message in build_slack_message_batches():
            real_channel = channel_map.get(channel_id)
            if not real_channel:
                slack_errors.append(
                    {"fixture_channel": channel_id, "error": "No Slack channel mapping"}
                )
                continue
            text = apply_issue_key_map(str(message.get("text") or ""), key_map)
            text = f"[Nexus Demo] {text}"
            if dry_run:
                slack_posted.append(
                    {"fixture_channel": channel_id, "real_channel": real_channel, "dry_run": "true"}
                )
                continue
            try:
                result = await slack.post_message(real_channel, text)
                slack_posted.append(
                    {
                        "fixture_channel": channel_id,
                        "real_channel": real_channel,
                        "ts": str(result.get("ts") or ""),
                    }
                )
                await asyncio.sleep(1.1)
            except Exception as exc:
                slack_errors.append(
                    {"fixture_channel": channel_id, "error": str(exc)[:500]}
                )

    return {
        "dry_run": dry_run,
        "jira_label": label,
        "issue_key_map": key_map,
        "confluence_page_map": page_map,
        "slack_channel_map": channel_map,
        "jira": {
            "created": jira_created,
            "skipped_existing": jira_skipped,
            "errors": jira_errors,
        },
        "confluence": {
            "created": confluence_created,
            "skipped_existing": confluence_skipped,
            "errors": confluence_errors,
        },
        "slack": {
            "posted": slack_posted,
            "errors": slack_errors,
        },
    }
