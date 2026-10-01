"""Web tools: fetch a URL and search the web.

Search uses DuckDuckGo's HTML endpoint by default, so it works with no API key.
If BRAVE_API_KEY or TAVILY_API_KEY is set, those are used instead for cleaner
results.
"""
from __future__ import annotations

import html
import os
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from ..core.types import ToolResult, ToolStatus
from .base import Tool

MAX_FETCH_BYTES = 2_000_000
MAX_OUTPUT_CHARS = 20_000
USER_AGENT = "Mozilla/5.0 (compatible; edarkcode/0.1; +https://github.com/tnvmac-web/EdarkCode)"

_SCRIPT_STYLE = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]*\n[ \t]*\n\s*\n+")
_DDG_RESULT = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'.*?(?:<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>)?',
    re.DOTALL | re.IGNORECASE,
)


def _strip_html(raw: str) -> str:
    text = _SCRIPT_STYLE.sub(" ", raw)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\n", text, flags=re.IGNORECASE)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return _WS.sub("\n\n", text).strip()


def _clean(text: str) -> str:
    return html.unescape(_TAG.sub("", text or "")).strip()


def _unwrap_ddg(url: str) -> str:
    """DuckDuckGo wraps results in /l/?uddg=<encoded>. Unwrap when present."""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return unquote(target[0])
    return url


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch a URL and return its readable text content (HTML is converted to text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Absolute http(s) URL to fetch."},
            "max_chars": {"type": "integer", "description": "Truncate output to this many characters."},
        },
        "required": ["url"],
    }

    async def run(self, url: str, max_chars: int = MAX_OUTPUT_CHARS, **_: Any) -> ToolResult:
        if not url.lower().startswith(("http://", "https://")):
            return ToolResult(self.name, ToolStatus.ERROR, error="Only http(s) URLs are supported.")
        limit = max(500, min(int(max_chars or MAX_OUTPUT_CHARS), MAX_OUTPUT_CHARS))
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=f"Request failed: {e}")

        if resp.status_code >= 400:
            return ToolResult(
                self.name,
                ToolStatus.ERROR,
                error=f"HTTP {resp.status_code} for {url}",
            )
        content_type = resp.headers.get("content-type", "")
        raw = resp.text[:MAX_FETCH_BYTES]
        text = _strip_html(raw) if ("html" in content_type or "<html" in raw[:2000].lower()) else raw.strip()
        if not text:
            return ToolResult(self.name, ToolStatus.ERROR, error="Page contained no readable text.")
        truncated = text[:limit]
        suffix = "\n... (truncated)" if len(text) > limit else ""
        return ToolResult(self.name, ToolStatus.SUCCESS, output=f"# {url}\n\n{truncated}{suffix}")


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web and return titles, URLs and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "max_results": {"type": "integer", "description": "Number of results (1-10). Default 5."},
        },
        "required": ["query"],
    }

    async def run(self, query: str, max_results: int = 5, **_: Any) -> ToolResult:
        count = max(1, min(int(max_results or 5), 10))
        brave = os.environ.get("BRAVE_API_KEY")
        tavily = os.environ.get("TAVILY_API_KEY")
        try:
            if brave:
                results = await self._brave(query, count, brave)
            elif tavily:
                results = await self._tavily(query, count, tavily)
            else:
                results = await self._duckduckgo(query, count)
        except httpx.HTTPError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=f"Search request failed: {e}")

        if not results:
            return ToolResult(
                self.name,
                ToolStatus.SUCCESS,
                output=f"No results for '{query}'.",
            )
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['url']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet']}")
        return ToolResult(self.name, ToolStatus.SUCCESS, output="\n".join(lines))

    # -- backends ----------------------------------------------------------
    async def _brave(self, query: str, count: int, key: str) -> list[dict[str, str]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": count},
                headers={"Accept": "application/json", "X-Subscription-Token": key},
            )
            resp.raise_for_status()
            data = resp.json()
        out = []
        for item in (data.get("web", {}) or {}).get("results", [])[:count]:
            out.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": _strip_html(item.get("description", ""))[:300],
                }
            )
        return out

    async def _tavily(self, query: str, count: int, key: str) -> list[dict[str, str]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": key, "query": query, "max_results": count},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": (item.get("content", "") or "")[:300],
            }
            for item in data.get("results", [])[:count]
        ]

    async def _duckduckgo(self, query: str, count: int) -> list[dict[str, str]]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            page = resp.text

        results: list[dict[str, str]] = []
        for match in _DDG_RESULT.finditer(page):
            url = _unwrap_ddg(match.group("url"))
            title = _clean(match.group("title"))
            if not url or not title:
                continue
            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": _clean(match.group("snippet") or "")[:300],
                }
            )
            if len(results) >= count:
                break

        if not results:
            # Fall back to a looser pattern if DuckDuckGo changed its markup.
            for href, title in re.findall(
                r'href="(https?://[^"]+)"[^>]*>(.{0,160}?)</a>', page, re.DOTALL
            ):
                clean_title = _clean(title)
                if len(clean_title) < 8 or "duckduckgo" in href:
                    continue
                results.append({"title": clean_title, "url": href, "snippet": ""})
                if len(results) >= count:
                    break
        return results
