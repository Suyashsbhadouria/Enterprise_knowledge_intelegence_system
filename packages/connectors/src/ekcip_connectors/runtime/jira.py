import base64
from typing import Any

import httpx

from ekcip_connectors.ports import ConnectorCapability, ConnectorHealth, ConnectorPort
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


def _adf_to_text(node: Any) -> str:
    """Extract plain text from Jira Atlassian Document Format."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return " ".join(part for part in (_adf_to_text(item) for item in node) if part)
    if not isinstance(node, dict):
        return str(node)
    text = node.get("text", "")
    if text:
        return str(text)
    parts: list[str] = []
    for child in node.get("content", []) or []:
        extracted = _adf_to_text(child)
        if extracted:
            parts.append(extracted)
    return " ".join(parts)


def _field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _adf_to_text(value)
    return str(value)


class JiraConnector(ConnectorPort):
    """Jira Cloud REST client (read + dev seed writes)."""

    name = "jira"
    capabilities = (
        ConnectorCapability.READ,
        ConnectorCapability.SEARCH,
        ConnectorCapability.WRITE,
    )

    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._api_token = api_token
        token_bytes = f"{email}:{api_token}".encode()
        self._auth_header = "Basic " + base64.b64encode(token_bytes).decode("ascii")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def health(self) -> ConnectorHealth:
        try:
            await self.ping()
            return ConnectorHealth(name=self.name, ready=True, mode="rest-api-v3")
        except Exception as exc:
            return ConnectorHealth(
                name=self.name,
                ready=False,
                mode="rest-api-v3",
                detail=str(exc)[:300],
            )

    async def ping(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/rest/api/3/myself",
                headers=self._headers(),
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Jira ping failed: HTTP {response.status_code}")
        data = response.json()
        return {
            "account_id": data.get("accountId"),
            "display_name": data.get("displayName"),
            "base_url": self._base_url,
        }

    async def search_issues(
        self,
        jql: str,
        *,
        max_results: int = 50,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search via Jira Cloud enhanced JQL API (replaces removed POST /search)."""
        field_list = fields or [
            "summary",
            "description",
            "status",
            "assignee",
            "updated",
            "project",
            "comment",
        ]
        issues: list[dict[str, Any]] = []
        next_page_token: str | None = None

        async with httpx.AsyncClient(timeout=60.0) as client:
            while len(issues) < max_results:
                page_size = min(50, max_results - len(issues))
                payload: dict[str, Any] = {
                    "jql": jql,
                    "maxResults": page_size,
                    "fields": field_list,
                }
                if next_page_token:
                    payload["nextPageToken"] = next_page_token

                response = await client.post(
                    f"{self._base_url}/rest/api/3/search/jql",
                    headers=self._headers(),
                    json=payload,
                )
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"Jira search failed: HTTP {response.status_code} {response.text[:400]}"
                    )
                data = response.json()
                batch = list(data.get("issues", []))
                issues.extend(batch)
                next_page_token = data.get("nextPageToken")
                if not batch or not next_page_token:
                    break

        return issues[:max_results]

    async def list_projects(self, *, max_results: int = 50) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/rest/api/3/project/search",
                headers=self._headers(),
                params={"maxResults": max_results, "orderBy": "key"},
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Jira list_projects failed: HTTP {response.status_code}")
        data = response.json()
        return list(data.get("values", []))

    async def get_default_issue_type(self, project_key: str) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/rest/api/3/issue/createmeta",
                headers=self._headers(),
                params={
                    "projectKeys": project_key,
                    "expand": "projects.issuetypes",
                },
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Jira createmeta failed: HTTP {response.status_code}")
        data = response.json()
        projects = data.get("projects", [])
        if not projects:
            raise RuntimeError(f"No create metadata for project {project_key}")
        issue_types = projects[0].get("issuetypes", [])
        if not issue_types:
            raise RuntimeError(f"No issue types for project {project_key}")
        for preferred in ("Task", "Story", "Bug"):
            for issue_type in issue_types:
                if issue_type.get("name") == preferred:
                    return str(issue_type["id"])
        return str(issue_types[0]["id"])

    async def create_issue(
        self,
        *,
        project_key: str,
        summary: str,
        description: str,
        issue_type_id: str | None = None,
    ) -> dict[str, Any]:
        type_id = issue_type_id or await self.get_default_issue_type(project_key)
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}],
                        }
                    ],
                },
                "issuetype": {"id": type_id},
            }
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/rest/api/3/issue",
                headers=self._headers(),
                json=payload,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Jira create_issue failed: HTTP {response.status_code} {response.text[:400]}"
            )
        return response.json()

    async def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/rest/api/3/issue/{issue_key}/comment",
                headers=self._headers(),
                json=payload,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Jira add_comment failed: HTTP {response.status_code} {response.text[:400]}"
            )
        data = response.json()
        return {
            "issue_key": issue_key,
            "comment_id": data.get("id"),
            "self": data.get("self"),
        }

    async def list_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/rest/api/3/issue/{issue_key}/transitions",
                headers=self._headers(),
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Jira list_transitions failed: HTTP {response.status_code} {response.text[:400]}"
            )
        data = response.json()
        return list(data.get("transitions", []))

    async def transition_issue(self, issue_key: str, status_name: str) -> dict[str, Any]:
        normalized = status_name.strip().lower()
        transitions = await self.list_transitions(issue_key)
        match = next(
            (
                transition
                for transition in transitions
                if str((transition.get("to") or {}).get("name", "")).strip().lower() == normalized
                or str(transition.get("name", "")).strip().lower() == normalized
            ),
            None,
        )
        if match is None:
            available = [
                str((transition.get("to") or {}).get("name") or transition.get("name"))
                for transition in transitions
            ]
            raise RuntimeError(
                f"No Jira transition to '{status_name}' for {issue_key}. "
                f"Available: {', '.join(available) or 'none'}"
            )
        transition_id = str(match["id"])
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/rest/api/3/issue/{issue_key}/transitions",
                headers=self._headers(),
                json={"transition": {"id": transition_id}},
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Jira transition_issue failed: HTTP {response.status_code} {response.text[:400]}"
            )
        return {
            "issue_key": issue_key,
            "status_name": status_name,
            "transition_id": transition_id,
        }

    async def get_issue(self, issue_key: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/rest/api/3/issue/{issue_key}",
                headers=self._headers(),
                params={"fields": "summary,description,status,assignee,updated,project,comment"},
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Jira get_issue failed: HTTP {response.status_code}")
        return response.json()

    def issue_document(self, issue: dict[str, Any]) -> dict[str, Any]:
        """Normalize a Jira issue into indexable document fields."""
        fields = issue.get("fields", {})
        key = issue.get("key", "")
        status = (fields.get("status") or {}).get("name", "")
        assignee_obj = fields.get("assignee") or {}
        assignee = assignee_obj.get("displayName") or assignee_obj.get("emailAddress") or "Unassigned"
        assignee_account_id = assignee_obj.get("accountId")
        assignee_email = assignee_obj.get("emailAddress")
        project = (fields.get("project") or {}).get("key", "")
        project_name = (fields.get("project") or {}).get("name", project)
        summary = fields.get("summary") or ""
        description = _field_text(fields.get("description"))
        comments_block = fields.get("comment") or {}
        comment_lines: list[str] = []
        for comment in comments_block.get("comments", []) or []:
            author = (comment.get("author") or {}).get("displayName", "unknown")
            body = _field_text(comment.get("body"))
            if body:
                comment_lines.append(f"{author}: {body}")
        comments_text = "\n".join(comment_lines)
        url = f"{self._base_url}/browse/{key}" if key else self._base_url
        body_parts = [
            f"Issue: {key}",
            f"Project: {project}",
            f"Status: {status}",
            f"Assignee: {assignee}",
            f"Summary: {summary}",
        ]
        if description:
            body_parts.append(f"Description:\n{description}")
        if comments_text:
            body_parts.append(f"Comments:\n{comments_text}")
        return {
            "source": "jira",
            "source_id": key,
            "title": summary or key,
            "content": "\n".join(body_parts),
            "url": url,
            "metadata": {
                "project": project,
                "project_name": project_name,
                "status": status,
                "assignee": assignee,
                "assignee_account_id": assignee_account_id,
                "assignee_email": assignee_email,
                "updated": fields.get("updated"),
            },
        }
