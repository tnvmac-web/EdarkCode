"""Tool abstraction and registry."""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from ..core.types import ToolResult, ToolStatus


class Tool:
    """A callable capability the agent can invoke."""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, workspace: str = ".") -> None:
        self.workspace = workspace

    async def run(self, **kwargs: Any) -> ToolResult:  # pragma: no cover - overridden
        raise NotImplementedError

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Holds tools and dispatches calls by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError(f"Tool {type(tool).__name__} has no name")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_name=name,
                status=ToolStatus.ERROR,
                error=f"Unknown tool '{name}'. Available: {', '.join(self.names())}",
            )
        try:
            sig = inspect.signature(tool.run)
            accepted = {k: v for k, v in arguments.items() if k in sig.parameters}
        except (TypeError, ValueError):
            accepted = arguments
        return await tool.run(**accepted)


def tool_function(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator marker for documenting tool entrypoints (used by docs/tests)."""
    fn.__is_tool__ = True  # type: ignore[attr-defined]
    return fn
