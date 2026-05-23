"""Maps connector plane sources to Cursor MCP server IDs for agent-side operations."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

ConnectorSource = Literal[
    "jira",
    "confluence",
    "github",
    "slack",
    "meetings",
    "documents",
    "postgres_neon",
]


class McpToolHint(BaseModel):
    """Documentation for agents: which MCP server backs a connector in Cursor."""

    server_id: str
    auth_tool: str | None = "mcp_auth"
    example_tools: list[str] = Field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True)
class McpConnectorEntry:
    source: ConnectorSource
    display_name: str
    mcp_server_id: str
    runtime_env_keys: tuple[str, ...]
    tool_hints: McpToolHint


class McpConnectorRegistry(BaseModel):
    """Registry used by API /health/connectors and agent playbooks."""

    entries: list[McpConnectorEntry]

    def get(self, source: ConnectorSource) -> McpConnectorEntry | None:
        return next((e for e in self.entries if e.source == source), None)

    def list_for_api(self) -> list[dict]:
        return [
            {
                "source": e.source,
                "display_name": e.display_name,
                "mcp_server_id": e.mcp_server_id,
                "runtime_env_keys": list(e.runtime_env_keys),
                "mcp": e.tool_hints.model_dump(),
                "phase": _phase_for_source(e.source),
            }
            for e in self.entries
        ]


def _phase_for_source(source: ConnectorSource) -> int:
    mapping: dict[ConnectorSource, int] = {
        "jira": 1,
        "confluence": 2,
        "github": 2,
        "slack": 4,
        "meetings": 5,
        "documents": 2,
        "postgres_neon": 0,
    }
    return mapping.get(source, 99)


@lru_cache
def get_mcp_registry(
    *,
    atlassian_server: str = "plugin-atlassian-atlassian",
    github_server: str = "user-github",
    slack_server: str = "plugin-slack-slack",
    neon_server: str = "plugin-neon-postgres-neon",
) -> McpConnectorRegistry:
    return McpConnectorRegistry(
        entries=[
            McpConnectorEntry(
                source="jira",
                display_name="Jira",
                mcp_server_id=atlassian_server,
                runtime_env_keys=("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"),
                tool_hints=McpToolHint(
                    server_id=atlassian_server,
                    example_tools=["search_issues", "get_issue"],
                    notes="Authenticate via mcp_auth if STATUS.md requires it.",
                ),
            ),
            McpConnectorEntry(
                source="confluence",
                display_name="Confluence",
                mcp_server_id=atlassian_server,
                runtime_env_keys=("CONFLUENCE_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"),
                tool_hints=McpToolHint(
                    server_id=atlassian_server,
                    example_tools=["search_content", "get_page"],
                    notes="Shares Atlassian MCP server with Jira.",
                ),
            ),
            McpConnectorEntry(
                source="github",
                display_name="GitHub",
                mcp_server_id=github_server,
                runtime_env_keys=("GITHUB_TOKEN",),
                tool_hints=McpToolHint(
                    server_id=github_server,
                    example_tools=["search_repositories", "get_pull_request", "list_issues"],
                ),
            ),
            McpConnectorEntry(
                source="slack",
                display_name="Slack",
                mcp_server_id=slack_server,
                runtime_env_keys=("SLACK_BOT_TOKEN",),
                tool_hints=McpToolHint(
                    server_id=slack_server,
                    auth_tool="mcp_auth",
                    example_tools=["conversations_history", "chat_postMessage"],
                    notes="Phase 4 write actions; read ingest in Phase 2.",
                ),
            ),
            McpConnectorEntry(
                source="meetings",
                display_name="Meetings / Transcripts",
                mcp_server_id="",
                runtime_env_keys=(),
                tool_hints=McpToolHint(
                    server_id="",
                    notes="Phase 5: file upload or calendar/transcript APIs.",
                ),
            ),
            McpConnectorEntry(
                source="documents",
                display_name="Document Store",
                mcp_server_id="",
                runtime_env_keys=(),
                tool_hints=McpToolHint(
                    server_id="",
                    notes="Phase 2+: S3/SharePoint/Drive adapters.",
                ),
            ),
            McpConnectorEntry(
                source="postgres_neon",
                display_name="Neon Postgres (MCP)",
                mcp_server_id=neon_server,
                runtime_env_keys=("DATABASE_URL",),
                tool_hints=McpToolHint(
                    server_id=neon_server,
                    auth_tool="mcp_auth",
                    notes="Optional cloud Postgres via Neon MCP; local dev uses docker postgres.",
                ),
            ),
        ]
    )
