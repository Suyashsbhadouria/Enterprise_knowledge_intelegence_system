"""GitHub REST client for read-only issue/PR ingest (Phase 2)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ekcip_connectors.ports import ConnectorCapability, ConnectorHealth, ConnectorPort
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

_API_ROOT = "https://api.github.com"


class GitHubConnector(ConnectorPort):
    name = "github"
    capabilities = (
        ConnectorCapability.READ,
        ConnectorCapability.SEARCH,
    )

    def __init__(self, token: str) -> None:
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def health(self) -> ConnectorHealth:
        try:
            await self.ping()
            return ConnectorHealth(name=self.name, ready=True, mode="github-rest-v3")
        except Exception as exc:
            return ConnectorHealth(
                name=self.name,
                ready=False,
                mode="github-rest-v3",
                detail=str(exc)[:300],
            )

    async def ping(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{_API_ROOT}/user",
                headers=self._headers(),
            )
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub ping failed: HTTP {response.status_code}")
        data = response.json()
        return {"login": data.get("login"), "type": data.get("type")}

    @staticmethod
    def since_iso(days: int) -> str:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(days, 1))
        return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    async def list_recent_items(
        self,
        repo: str,
        *,
        since_iso: str,
        max_results: int,
    ) -> list[dict[str, Any]]:
        owner, name = repo.split("/", 1)
        items: list[dict[str, Any]] = []
        page = 1
        async with httpx.AsyncClient(timeout=60.0) as client:
            while len(items) < max_results:
                response = await client.get(
                    f"{_API_ROOT}/repos/{owner}/{name}/issues",
                    headers=self._headers(),
                    params={
                        "state": "all",
                        "since": since_iso,
                        "per_page": min(100, max_results - len(items)),
                        "page": page,
                        "sort": "updated",
                        "direction": "desc",
                    },
                )
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"GitHub list issues failed for {repo}: HTTP {response.status_code} "
                        f"{response.text[:300]}"
                    )
                batch = list(response.json())
                if not batch:
                    break
                items.extend(batch)
                if len(batch) < 100:
                    break
                page += 1

        return items[:max_results]

    def item_document(self, repo: str, item: dict[str, Any]) -> dict[str, Any]:
        number = int(item.get("number") or 0)
        is_pr = "pull_request" in (item or {})
        source_id = f"{repo}!{number}" if is_pr else f"{repo}#{number}"
        state = str(item.get("state") or "")
        title = str(item.get("title") or source_id)
        body = str(item.get("body") or "").strip()
        user = (item.get("user") or {}).get("login") or "unknown"
        labels = [label.get("name", "") for label in item.get("labels", []) or []]
        labels_text = ", ".join(label for label in labels if label)
        url = str(item.get("html_url") or "")
        updated = str(item.get("updated_at") or "")
        kind = "pull_request" if is_pr else "issue"
        parts = [
            f"GitHub {kind}: {source_id}",
            f"Repository: {repo}",
            f"State: {state}",
            f"Author: {user}",
            f"Title: {title}",
        ]
        if labels_text:
            parts.append(f"Labels: {labels_text}")
        if body:
            parts.append(f"Body:\n{body[:8000]}")
        return {
            "source": "github",
            "source_id": source_id,
            "title": title,
            "content": "\n".join(parts),
            "url": url,
            "metadata": {
                "repo": repo,
                "number": number,
                "state": state,
                "author": user,
                "kind": kind,
                "labels": labels,
                "updated_at": updated,
            },
        }


def build_github_connector(settings: Settings) -> GitHubConnector | None:
    if not settings.github_token:
        return None
    return GitHubConnector(settings.github_token)
