"""Shared types for edarkcode."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"


class AgentPhase(str, Enum):
    IDLE = "idle"
    RESEARCH = "research"
    PLANNING = "planning"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class Message:
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d


@dataclass
class ToolResult:
    tool_name: str
    status: ToolStatus
    output: str = ""
    error: str | None = None
    duration_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status is ToolStatus.SUCCESS

    def as_text(self) -> str:
        if self.status is ToolStatus.SUCCESS:
            return self.output or "(no output)"
        return f"ERROR: {self.error or 'tool failed'}"


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""


@dataclass
class LLMStreamChunk:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


@dataclass
class StreamEvent:
    """Emitted by the agent for any UI to render."""

    type: str  # message | tool_call | tool_result | phase | plan | error | complete
    data: Any
    timestamp: datetime = field(default_factory=_now)


@dataclass
class AgentState:
    phase: AgentPhase = AgentPhase.IDLE
    iteration: int = 0
    plan: list[str] = field(default_factory=list)
    consecutive_errors: int = 0
    total_tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
