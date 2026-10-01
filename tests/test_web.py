"""Tests for the web API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from edarkcode.core.config import Settings
from edarkcode.web.app import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings()
    settings.workspace = tmp_path
    settings.memory.path = tmp_path / "memory.jsonl"
    settings.self_improvement.path = tmp_path / "lessons.jsonl"
    settings.llm.api_key = "test-key"
    return TestClient(create_app(settings))


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["api_key_configured"] is True


def test_tools_listing(client):
    r = client.get("/api/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert {"read_file", "write_file", "edit_file", "list_dir", "search", "run_shell"} <= names


def test_memory_endpoint_empty(client):
    r = client.get("/api/memory")
    assert r.status_code == 200
    assert r.json() == {"memories": [], "lessons": []}


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "edarkcode" in r.text


def test_websocket_run_streams_events(client, monkeypatch):
    """Drive the WS endpoint with a stubbed agent so no network is needed."""
    from edarkcode.core.types import StreamEvent

    class StubAgent:
        def __init__(self, *a, **k):
            self.llm = self

        async def run(self, goal):
            yield StreamEvent("phase", {"phase": "executing", "label": "executing"})
            yield StreamEvent("message", {"role": "assistant", "content": f"echo: {goal}", "final": True})
            summary = {
                "iterations": 1,
                "tool_calls": 0,
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "result": f"echo: {goal}",
            }
            yield StreamEvent("complete", summary)

        async def aclose(self):
            return None

    monkeypatch.setattr("edarkcode.web.app.build_agent", lambda *a, **k: StubAgent())

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "run", "goal": "hello"})
        types = []
        for _ in range(3):
            msg = ws.receive_json()
            types.append(msg["type"])
        assert types == ["phase", "message", "complete"]


def test_websocket_rejects_bad_type(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "nonsense"})
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_websocket_handles_invalid_json(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text("not json")
        msg = ws.receive_json()
        assert msg["type"] == "error"
