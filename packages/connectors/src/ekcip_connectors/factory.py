from ekcip_connectors.ports import ConnectorPort
from ekcip_connectors.runtime.confluence import build_confluence_connector
from ekcip_connectors.runtime.github import build_github_connector
from ekcip_connectors.runtime.jira import JiraConnector
from ekcip_connectors.runtime.slack import build_slack_connector
from ekcip_connectors.runtime.stub import StubConnector
from ekcip_shared.config import Settings


def build_runtime_connectors(settings: Settings) -> list[ConnectorPort]:
    connectors: list[ConnectorPort] = []
    if settings.jira_configured:
        connectors.append(
            JiraConnector(
                settings.jira_base_url or "",
                settings.jira_email or "",
                settings.jira_api_token or "",
            )
        )
    else:
        connectors.append(StubConnector("jira", ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")))

    confluence = build_confluence_connector(settings)
    if confluence is not None:
        connectors.append(confluence)
    else:
        connectors.append(
            StubConnector("confluence", ("CONFLUENCE_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"))
        )

    github = build_github_connector(settings)
    if github is not None:
        connectors.append(github)
    else:
        connectors.append(StubConnector("github", ("GITHUB_TOKEN", "GITHUB_REPOS")))

    slack = build_slack_connector(settings)
    if slack is not None:
        connectors.append(slack)
    else:
        connectors.append(StubConnector("slack", ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_IDS")))

    return connectors
