"""LLM provider abstraction — OpenAI-compatible endpoints and Anthropic."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .config import LLMConfig
from .types import LLMResponse, LLMStreamChunk, Message, Role


class LLMError(Exception):
    """Raised when an LLM request fails after retries."""


# Provider presets: base_url + how to authenticate.
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai": {"base_url": "https://api.openai.com/v1", "auth": "bearer"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "auth": "bearer"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "auth": "bearer"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "auth": "bearer"},
    "ollama": {"base_url": "http://localhost:11434/v1", "auth": "none"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "auth": "x-api-key"},
}


def _messages_to_anthropic(messages: list[Message], system: str | None) -> tuple[str | None, list[dict[str, Any]]]:
    """Translate internal messages to Anthropic's format (system is top-level)."""
    out: list[dict[str, Any]] = []
    sys_parts: list[str] = []
    if system:
        sys_parts.append(system)
    for m in messages:
        if m.role is Role.SYSTEM:
            sys_parts.append(m.content)
            continue
        if m.role is Role.TOOL:
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id or "",
                            "content": m.content,
                        }
                    ],
                }
            )
            continue
        if m.role is Role.ASSISTANT and m.tool_calls:
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                blocks.append({"type": "tool_use", "id": tc.get("id", ""), "name": fn.get("name", ""), "input": args})
            out.append({"role": "assistant", "content": blocks})
            continue
        out.append({"role": m.role.value, "content": m.content})
    return ("\n\n".join(sys_parts) if sys_parts else None), out


class LLMClient:
    """Async client for chat-completion style APIs.

    Supports any OpenAI-compatible endpoint plus Anthropic's messages API.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        preset = PROVIDER_PRESETS.get(config.provider, PROVIDER_PRESETS["openai"])
        self.base_url = (config.base_url or preset["base_url"]).rstrip("/")
        self.auth_style = preset["auth"]
        self._client = httpx.AsyncClient(timeout=config.timeout)

    # -- lifecycle ---------------------------------------------------------
    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # -- headers -----------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.auth_style == "none":
            return h
        key = self.config.api_key
        if not key:
            raise LLMError(
                f"No API key configured for provider '{self.config.provider}'. "
                "Set EDARKCODE_LLM__API_KEY or run `edarkcode config set llm.api_key`."
            )
        if self.auth_style == "bearer":
            h["Authorization"] = f"Bearer {key}"
        elif self.auth_style == "x-api-key":
            h["x-api-key"] = key
            h["anthropic-version"] = "2023-06-01"
        return h

    def _is_anthropic(self) -> bool:
        return self.config.provider == "anthropic"

    # -- request building --------------------------------------------------
    def _build_payload(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        system: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if self._is_anthropic():
            sys_text, anth_messages = _messages_to_anthropic(messages, system)
            payload: dict[str, Any] = {
                "model": self.config.model,
                "messages": anth_messages,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
            }
            if sys_text:
                payload["system"] = sys_text
            if tools:
                payload["tools"] = [
                    {
                        "name": t["function"]["name"],
                        "description": t["function"].get("description", ""),
                        "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}}),
                    }
                    for t in tools
                ]
            if stream:
                payload["stream"] = True
            return f"{self.base_url}/messages", payload

        payload = {
            "model": self.config.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
        }
        if system:
            payload["messages"] = [{"role": "system", "content": system}] + payload["messages"]
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if stream:
            payload["stream"] = True
        return f"{self.base_url}/chat/completions", payload

    # -- non-streaming -----------------------------------------------------
    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> LLMResponse:
        url, payload = self._build_payload(messages, tools, stream=False, system=system)
        last_err: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                resp = await self._client.post(url, headers=self._headers(), json=payload)
                if resp.status_code >= 400:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                data = resp.json()
                return self._parse_response(data)
            except (httpx.HTTPError, LLMError, json.JSONDecodeError) as e:
                last_err = e
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2**attempt))
        raise LLMError(f"LLM request failed after {self.config.max_retries} attempts: {last_err}")

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        if self._is_anthropic():
            content = ""
            tool_calls: list[dict[str, Any]] = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")
                elif block.get("type") == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        }
                    )
            usage = data.get("usage", {})
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=data.get("stop_reason", "stop"),
                usage={
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                },
                model=data.get("model", self.config.model),
            )

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        usage = data.get("usage", {})
        return LLMResponse(
            content=msg.get("content") or "",
            tool_calls=msg.get("tool_calls") or [],
            finish_reason=choice.get("finish_reason", "stop"),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
            model=data.get("model", self.config.model),
        )

    # -- streaming ---------------------------------------------------------
    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        url, payload = self._build_payload(messages, tools, stream=True, system=system)
        async with self._client.stream("POST", url, headers=self._headers(), json=payload) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise LLMError(f"HTTP {resp.status_code}: {body.decode(errors='replace')[:500]}")
            if self._is_anthropic():
                async for chunk in self._stream_anthropic(resp):
                    yield chunk
            else:
                async for chunk in self._stream_openai(resp):
                    yield chunk

    async def _stream_openai(self, resp: httpx.Response) -> AsyncIterator[LLMStreamChunk]:
        # Accumulate tool-call deltas by index.
        tool_acc: dict[int, dict[str, Any]] = {}
        async for line in resp.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choice = (data.get("choices") or [{}])[0]
            delta = choice.get("delta", {})
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = tool_acc.setdefault(
                    idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                )
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
            yield LLMStreamChunk(
                content=delta.get("content") or "",
                finish_reason=choice.get("finish_reason"),
                usage=data.get("usage"),
            )
        if tool_acc:
            yield LLMStreamChunk(tool_calls=[tool_acc[i] for i in sorted(tool_acc)])

    async def _stream_anthropic(self, resp: httpx.Response) -> AsyncIterator[LLMStreamChunk]:
        current: dict[str, Any] | None = None
        args_buf = ""
        async for line in resp.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            try:
                data = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            etype = data.get("type")
            if etype == "content_block_start":
                block = data.get("content_block", {})
                if block.get("type") == "tool_use":
                    current = {"id": block.get("id", ""), "name": block.get("name", "")}
                    args_buf = ""
            elif etype == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    yield LLMStreamChunk(content=delta.get("text", ""))
                elif delta.get("type") == "input_json_delta":
                    args_buf += delta.get("partial_json", "")
            elif etype == "content_block_stop" and current is not None:
                yield LLMStreamChunk(
                    tool_calls=[
                        {
                            "id": current["id"],
                            "type": "function",
                            "function": {"name": current["name"], "arguments": args_buf or "{}"},
                        }
                    ]
                )
                current = None
            elif etype == "message_stop":
                break
