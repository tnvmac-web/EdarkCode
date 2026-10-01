"""Shared fixtures. A fake LLM lets us test the agent loop with no network."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from edarkcode.core.config import Settings
from edarkcode.core.types import LLMResponse, LLMStreamChunk, Message


class FakeLLM:
    """Scripted LLM: returns queued responses in order."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[list[Message]] = []

    async def complete(self, messages, tools=None, system=None) -> LLMResponse:
        self.calls.append(list(messages))
        if not self.responses:
            return LLMResponse(content="done", finish_reason="stop")
        return self.responses.pop(0)

    async def stream(self, messages, tools=None, system=None) -> AsyncIterator[LLMStreamChunk]:
        resp = await self.complete(messages, tools, system)
        yield LLMStreamChunk(content=resp.content, tool_calls=resp.tool_calls, finish_reason=resp.finish_reason)

    async def aclose(self) -> None:
        return None


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> dict[str, Any]:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings()
    s.workspace = tmp_path
    s.agent.enable_planning = False
    s.agent.enable_reflection = False
    s.memory.enabled = False
    s.self_improvement.enabled = False
    s.llm.api_key = "test-key"
    return s
