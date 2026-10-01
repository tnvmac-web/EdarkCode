"""Tests for the LLM client's request building and response parsing (no network)."""
from __future__ import annotations

import json

import pytest

from edarkcode.core.config import LLMConfig
from edarkcode.core.llm import LLMClient, LLMError
from edarkcode.core.types import Message, Role


def test_openai_payload_shape():
    client = LLMClient(LLMConfig(provider="openai", model="gpt-4o", api_key="k"))
    url, payload = client._build_payload([Message(Role.USER, "hi")], None, stream=False)
    assert url.endswith("/chat/completions")
    assert payload["model"] == "gpt-4o"
    assert payload["messages"][0] == {"role": "user", "content": "hi"}


def test_tools_are_included():
    client = LLMClient(LLMConfig(provider="openai", api_key="k"))
    tools = [{"type": "function", "function": {"name": "t", "description": "d", "parameters": {}}}]
    _, payload = client._build_payload([Message(Role.USER, "hi")], tools, stream=False)
    assert payload["tools"] == tools
    assert payload["tool_choice"] == "auto"


def test_anthropic_translation():
    client = LLMClient(LLMConfig(provider="anthropic", model="claude-3-5-sonnet", api_key="k"))
    messages = [
        Message(Role.SYSTEM, "be nice"),
        Message(Role.USER, "hello"),
        Message(Role.ASSISTANT, "ok", tool_calls=[{"id": "t1", "function": {"name": "f", "arguments": '{"a":1}'}}]),
        Message(Role.TOOL, "result", tool_call_id="t1"),
    ]
    url, payload = client._build_payload(messages, None, stream=False)
    assert url.endswith("/messages")
    assert payload["system"] == "be nice"
    assert payload["messages"][0]["role"] == "user"
    assistant = payload["messages"][1]
    assert assistant["content"][1]["type"] == "tool_use"
    assert assistant["content"][1]["input"] == {"a": 1}


def test_parse_openai_response():
    client = LLMClient(LLMConfig(provider="openai", api_key="k"))
    data = {
        "choices": [{"message": {"content": "hey", "tool_calls": []}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        "model": "gpt-4o",
    }
    resp = client._parse_response(data)
    assert resp.content == "hey"
    assert resp.usage["prompt_tokens"] == 5


def test_parse_anthropic_response():
    client = LLMClient(LLMConfig(provider="anthropic", api_key="k"))
    data = {
        "content": [
            {"type": "text", "text": "hi "},
            {"type": "tool_use", "id": "tu1", "name": "read_file", "input": {"path": "a"}},
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 3, "output_tokens": 7},
        "model": "claude",
    }
    resp = client._parse_response(data)
    assert resp.content == "hi "
    assert resp.tool_calls[0]["function"]["name"] == "read_file"
    assert json.loads(resp.tool_calls[0]["function"]["arguments"]) == {"path": "a"}
    assert resp.usage["completion_tokens"] == 7


def test_missing_api_key_raises():
    client = LLMClient(LLMConfig(provider="openai", api_key=None))
    with pytest.raises(LLMError, match="No API key"):
        client._headers()


def test_ollama_needs_no_key():
    client = LLMClient(LLMConfig(provider="ollama", api_key=None))
    assert client._headers()["Content-Type"] == "application/json"
