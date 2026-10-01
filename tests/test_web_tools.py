"""Tests for the web tools. Network calls are stubbed; parsing is tested directly."""
from __future__ import annotations

import httpx

from edarkcode.core.types import ToolStatus
from edarkcode.tools import web as web_module
from edarkcode.tools.web import WebFetchTool, WebSearchTool, _strip_html, _unwrap_ddg


# -- parsing helpers -------------------------------------------------------
def test_strip_html_removes_tags_and_scripts():
    html = (
        "<html><head><script>var x=1;</script><style>.a{}</style></head>"
        "<body><p>Hello <b>world</b></p></body></html>"
    )
    text = _strip_html(html)
    assert "Hello" in text and "world" in text
    assert "var x" not in text and ".a{}" not in text


def test_strip_html_unescapes_entities():
    assert "a & b" in _strip_html("<p>a &amp; b</p>")


def test_unwrap_ddg_redirect():
    wrapped = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=abc"
    assert _unwrap_ddg(wrapped) == "https://example.com/page"


def test_unwrap_ddg_leaves_plain_urls():
    assert _unwrap_ddg("https://example.com/x") == "https://example.com/x"


# -- fetch -----------------------------------------------------------------
class _Resp:
    def __init__(self, text="", status=200, content_type="text/html", url="https://example.com"):
        self.text = text
        self.status_code = status
        self.headers = {"content-type": content_type}
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)  # type: ignore[arg-type]

    def json(self):
        import json as _json

        return _json.loads(self.text)


async def test_fetch_rejects_non_http():
    res = await WebFetchTool().run(url="ftp://example.com")
    assert res.status is ToolStatus.ERROR
    assert "http(s)" in res.error


async def test_fetch_converts_html(monkeypatch):
    async def fake_get(self, url, headers=None):
        return _Resp("<html><body><h1>Title</h1><p>Body text</p></body></html>")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    res = await WebFetchTool().run(url="https://example.com")
    assert res.status is ToolStatus.SUCCESS
    assert "Title" in res.output and "Body text" in res.output


async def test_fetch_reports_http_error(monkeypatch):
    async def fake_get(self, url, headers=None):
        return _Resp("nope", status=404)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    res = await WebFetchTool().run(url="https://example.com/missing")
    assert res.status is ToolStatus.ERROR
    assert "404" in res.error


async def test_fetch_truncates(monkeypatch):
    async def fake_get(self, url, headers=None):
        return _Resp("<p>" + ("x" * 5000) + "</p>")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    res = await WebFetchTool().run(url="https://example.com", max_chars=1000)
    assert "truncated" in res.output
    assert len(res.output) < 1400


# -- search ----------------------------------------------------------------
async def test_search_parses_duckduckgo(monkeypatch):
    page = (
        '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpython.org">Python</a>'
        '<a class="result__snippet">The official Python site</a>'
        '<a class="result__a" href="https://docs.python.org/3/">Docs</a>'
        '<a class="result__snippet">Python 3 documentation</a>'
    )

    async def fake_post(self, url, data=None, headers=None):
        return _Resp(page)

    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    res = await WebSearchTool().run(query="python", max_results=2)
    assert res.status is ToolStatus.SUCCESS
    assert "Python" in res.output
    assert "https://python.org" in res.output  # redirect unwrapped


async def test_search_no_results(monkeypatch):
    async def fake_post(self, url, data=None, headers=None):
        return _Resp("<html><body>nothing here</body></html>")

    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    res = await WebSearchTool().run(query="zzzzqqq")
    assert res.status is ToolStatus.SUCCESS
    assert "No results" in res.output


async def test_search_reports_network_failure(monkeypatch):
    async def boom(self, url, data=None, headers=None):
        raise httpx.ConnectError("no network")

    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    res = await WebSearchTool().run(query="anything")
    assert res.status is ToolStatus.ERROR
    assert "failed" in res.error.lower()


async def test_search_uses_brave_when_key_set(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    captured = {}

    async def fake_get(self, url, params=None, headers=None):
        captured["url"] = url
        captured["headers"] = headers
        return _Resp(
            '{"web": {"results": [{"title": "T", "url": "https://x.test", "description": "D"}]}}',
            content_type="application/json",
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    res = await WebSearchTool().run(query="q")
    assert res.status is ToolStatus.SUCCESS
    assert "brave" in captured["url"]
    assert captured["headers"]["X-Subscription-Token"] == "test-key"
    assert "https://x.test" in res.output


async def test_search_uses_tavily_when_only_tavily_key(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tk")
    captured = {}

    async def fake_post(self, url, json=None, headers=None):
        captured["url"] = url
        return _Resp('{"results": [{"title": "T", "url": "https://y.test", "content": "C"}]}')

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    res = await WebSearchTool().run(query="q")
    assert "tavily" in captured["url"]
    assert "https://y.test" in res.output


def test_tool_schemas_are_valid():
    for tool in (WebFetchTool(), WebSearchTool()):
        schema = tool.schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == tool.name
        assert "properties" in schema["function"]["parameters"]


def test_module_exposes_user_agent():
    assert "edarkcode" in web_module.USER_AGENT
