"""Synthetic enterprise fixtures for local/demo seeding (no live APIs required)."""

from ekcip_connectors.fixtures.enterprise_catalog import (
    ENTERPRISE_MANIFEST,
    build_confluence_documents,
    build_jira_documents,
    build_meeting_transcript_files,
    build_slack_message_batches,
    build_test_queries,
)

__all__ = [
    "ENTERPRISE_MANIFEST",
    "build_confluence_documents",
    "build_jira_documents",
    "build_meeting_transcript_files",
    "build_slack_message_batches",
    "build_test_queries",
]
