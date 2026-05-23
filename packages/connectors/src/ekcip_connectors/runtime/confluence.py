import base64
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

import httpx

from ekcip_connectors.ports import ConnectorCapability, ConnectorHealth, ConnectorPort
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1>",
    flags=re.DOTALL | re.IGNORECASE,
)


def normalize_confluence_base_url(base_url: str) -> str:
    """Accept site root or /wiki URL; return wiki root without trailing slash."""
    url = base_url.strip().rstrip("/")
    if not url.endswith("/wiki"):
        if ".atlassian.net" in url:
            return f"{url}/wiki"
    return url


def html_to_text(html: str) -> str:
    if not html:
        return ""
    stripped = _SCRIPT_STYLE_RE.sub(" ", html)
    stripped = _HTML_TAG_RE.sub(" ", stripped)
    text = unescape(stripped)
    return " ".join(text.split())


class ConfluenceConnector(ConnectorPort):
    """Confluence Cloud REST client (read-only, Phase 2)."""

    name = "confluence"
    capabilities = (
        ConnectorCapability.READ,
        ConnectorCapability.SEARCH,
    )

    def __init__(self, wiki_base_url: str, email: str, api_token: str) -> None:
        self._wiki_base = normalize_confluence_base_url(wiki_base_url)
        self._email = email
        self._api_token = api_token
        token_bytes = f"{email}:{api_token}".encode()
        self._auth_header = "Basic " + base64.b64encode(token_bytes).decode("ascii")

    @property
    def api_root(self) -> str:
        return f"{self._wiki_base}/rest/api"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._auth_header,
            "Accept": "application/json",
        }

    def page_url(self, page: dict[str, Any]) -> str:
        links = page.get("_links") or {}
        webui = links.get("webui")
        if webui:
            if webui.startswith("http"):
                return webui
            return urljoin(f"{self._wiki_base}/", webui.lstrip("/"))
        page_id = page.get("id", "")
        return f"{self._wiki_base}/pages/viewpage.action?pageId={page_id}"

    async def health(self) -> ConnectorHealth:
        try:
            await self.ping()
            return ConnectorHealth(name=self.name, ready=True, mode="confluence-rest-v1")
        except Exception as exc:
            return ConnectorHealth(
                name=self.name,
                ready=False,
                mode="confluence-rest-v1",
                detail=str(exc)[:300],
            )

    async def ping(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.api_root}/user/current",
                headers=self._headers(),
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Confluence ping failed: HTTP {response.status_code}")
        data = response.json()
        return {
            "account_id": data.get("accountId"),
            "display_name": data.get("displayName"),
            "wiki_base": self._wiki_base,
        }

    async def list_spaces(self, *, max_results: int = 50) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.api_root}/space",
                headers=self._headers(),
                params={"limit": max_results, "expand": "description.plain"},
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Confluence list_spaces failed: HTTP {response.status_code}")
        data = response.json()
        return list(data.get("results", []))

    async def search_pages(
        self,
        cql: str,
        *,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        start = 0
        page_size = min(25, max_results)

        async with httpx.AsyncClient(timeout=60.0) as client:
            while len(pages) < max_results:
                limit = min(page_size, max_results - len(pages))
                response = await client.get(
                    f"{self.api_root}/content/search",
                    headers=self._headers(),
                    params={
                        "cql": cql,
                        "limit": limit,
                        "start": start,
                        "expand": "space,history.lastUpdated,body.view",
                    },
                )
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"Confluence search failed: HTTP {response.status_code} "
                        f"{response.text[:400]}"
                    )
                data = response.json()
                batch = list(data.get("results", []))
                pages.extend(batch)
                size = int(data.get("size", len(batch)))
                if not batch or size < limit:
                    break
                start += size

        return pages[:max_results]

    async def get_page(self, page_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.api_root}/content/{page_id}",
                headers=self._headers(),
                params={"expand": "space,history.lastUpdated,body.view,version"},
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Confluence get_page failed: HTTP {response.status_code}")
        return response.json()

    def page_document(self, page: dict[str, Any]) -> dict[str, Any]:
        page_id = str(page.get("id", ""))
        title = page.get("title") or page_id
        space = page.get("space") or {}
        space_key = space.get("key", "")
        space_name = space.get("name", "")
        history = page.get("history") or {}
        last_updated = (history.get("lastUpdated") or {})
        updated_at = last_updated.get("when")
        updated_by = (last_updated.get("by") or {}).get("displayName", "")
        body_view = ((page.get("body") or {}).get("view") or {}).get("value", "")
        body_text = html_to_text(body_view)
        excerpt = page.get("excerpt", "")
        if not body_text and excerpt:
            body_text = html_to_text(excerpt)

        body_parts = [
            f"Page: {title}",
            f"Page ID: {page_id}",
            f"Space: {space_key} ({space_name})".strip(),
        ]
        if updated_by or updated_at:
            body_parts.append(f"Last updated: {updated_by} @ {updated_at}")
        if body_text:
            body_parts.append(f"Content:\n{body_text}")

        return {
            "source": "confluence",
            "source_id": page_id,
            "title": title,
            "content": "\n".join(body_parts),
            "url": self.page_url(page),
            "metadata": {
                "space_key": space_key,
                "space_name": space_name,
                "updated_at": updated_at,
                "updated_by": updated_by,
            },
        }


def build_confluence_connector(settings: Settings) -> ConfluenceConnector | None:
    base = settings.confluence_wiki_base_url
    if not base or not settings.jira_email or not settings.jira_api_token:
        return None
    return ConfluenceConnector(
        normalize_confluence_base_url(base),
        settings.jira_email,
        settings.jira_api_token,
    )
