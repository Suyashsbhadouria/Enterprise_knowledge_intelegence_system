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

    async def list_recent_commits(
        self,
        repo: str,
        *,
        since_iso: str,
        max_results: int,
    ) -> list[dict[str, Any]]:
        owner, name = repo.split("/", 1)
        commits: list[dict[str, Any]] = []
        page = 1
        async with httpx.AsyncClient(timeout=60.0) as client:
            while len(commits) < max_results:
                response = await client.get(
                    f"{_API_ROOT}/repos/{owner}/{name}/commits",
                    headers=self._headers(),
                    params={
                        "since": since_iso,
                        "per_page": min(100, max_results - len(commits)),
                        "page": page,
                    },
                )
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"GitHub list commits failed for {repo}: HTTP {response.status_code} "
                        f"{response.text[:300]}"
                    )
                batch = list(response.json())
                if not batch:
                    break
                commits.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
        return commits[:max_results]

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

    def commit_document(self, repo: str, commit: dict[str, Any]) -> dict[str, Any]:
        sha = str(commit.get("sha") or "")
        if not sha:
            raise ValueError("Commit missing sha")
        short_sha = sha[:7]
        source_id = f"{repo}@{short_sha}"
        commit_obj = commit.get("commit") or {}
        message = str(commit_obj.get("message") or "").strip()
        title_line = message.splitlines()[0] if message else short_sha
        author_obj = commit_obj.get("author") or {}
        committer_obj = commit_obj.get("committer") or {}
        gh_author = (commit.get("author") or {}).get("login")
        author_name = str(author_obj.get("name") or gh_author or "unknown")
        authored_at = str(author_obj.get("date") or "")
        pushed_at = str(committer_obj.get("date") or authored_at)
        url = str(commit.get("html_url") or "")
        parts = [
            f"GitHub commit: {source_id}",
            f"Repository: {repo}",
            f"Full SHA: {sha}",
            f"Author: {author_name}" + (f" (@{gh_author})" if gh_author else ""),
            f"Authored at: {authored_at or 'unknown'}",
            f"Pushed to GitHub at: {pushed_at or 'unknown'}",
            f"Message:\n{message[:8000]}",
        ]
        return {
            "source": "github",
            "source_id": source_id,
            "title": title_line,
            "content": "\n".join(parts),
            "url": url,
            "metadata": {
                "repo": repo,
                "sha": sha,
                "short_sha": short_sha,
                "author": gh_author or author_name,
                "author_name": author_name,
                "authored_at": authored_at,
                "pushed_at": pushed_at,
                "kind": "commit",
            },
        }


def build_github_connector(settings: Settings) -> GitHubConnector | None:
    if not settings.github_token:
        return None
    return GitHubConnector(settings.github_token)
