"""Planning tools: glob, multi-edit and a visible todo list."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.types import ToolResult, ToolStatus
from .base import Tool
from .files import SKIP_DIRS, WorkspaceTool


class GlobTool(WorkspaceTool):
    name = "glob"
    description = "Find files by glob pattern, e.g. '**/*.py'. Faster and clearer than search for filenames."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '**/*.py' or 'src/**/*.ts'."},
            "max_results": {"type": "integer", "description": "Cap results. Default 200."},
        },
        "required": ["pattern"],
    }

    async def run(self, pattern: str, max_results: int = 200, **_: Any) -> ToolResult:
        root = Path(self.workspace).resolve()
        cap = max(1, min(int(max_results or 200), 2000))
        hits: list[str] = []
        for path in root.glob(pattern):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file():
                hits.append(str(path.relative_to(root)))
                if len(hits) >= cap:
                    break
        hits.sort()
        return ToolResult(self.name, ToolStatus.SUCCESS, output="\n".join(hits) or "(no files matched)")


class MultiEditTool(WorkspaceTool):
    name = "multi_edit"
    description = (
        "Apply several exact-string edits to one file in a single call. "
        "Each edit needs old_string/new_string; all must match exactly once, or nothing is written."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to workspace."},
            "edits": {
                "type": "array",
                "description": "List of {old_string, new_string} objects.",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                    },
                    "required": ["old_string", "new_string"],
                },
            },
        },
        "required": ["path", "edits"],
    }

    async def run(self, path: str, edits: list[dict[str, str]], **_: Any) -> ToolResult:
        try:
            target = self._resolve(path)
        except ValueError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=str(e))
        if not target.exists():
            return ToolResult(self.name, ToolStatus.ERROR, error=f"No such file: {path}")
        if not isinstance(edits, list) or not edits:
            return ToolResult(self.name, ToolStatus.ERROR, error="`edits` must be a non-empty list.")

        original = target.read_text(encoding="utf-8", errors="replace")
        text = original
        # Validate every edit against the evolving text before writing anything,
        # so a bad edit cannot leave the file half-modified.
        for i, edit in enumerate(edits, 1):
            old = edit.get("old_string", "")
            new = edit.get("new_string", "")
            if not old:
                return ToolResult(self.name, ToolStatus.ERROR, error=f"Edit {i}: old_string is empty.")
            count = text.count(old)
            if count == 0:
                return ToolResult(
                    self.name,
                    ToolStatus.ERROR,
                    error=f"Edit {i}: old_string not found. No changes were written.",
                )
            if count > 1:
                return ToolResult(
                    self.name,
                    ToolStatus.ERROR,
                    error=f"Edit {i}: old_string appears {count} times; add more context. No changes were written.",
                )
            text = text.replace(old, new, 1)

        target.write_text(text, encoding="utf-8")
        return ToolResult(
            self.name,
            ToolStatus.SUCCESS,
            output=f"Applied {len(edits)} edit(s) to {path}.",
        )


class TodoTool(Tool):
    name = "todo"
    description = (
        "Maintain a visible task list for multi-step work. "
        "action='set' with a list of items replaces the list; action='list' shows it."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["set", "list"], "description": "Default 'list'."},
            "items": {
                "type": "array",
                "description": "For action='set': list of {text, status} where status is pending|in_progress|done.",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "done"]},
                    },
                    "required": ["text"],
                },
            },
        },
        "required": [],
    }

    def __init__(self, workspace: str = ".") -> None:
        super().__init__(workspace=workspace)
        self.items: list[dict[str, str]] = []

    def _render(self) -> str:
        if not self.items:
            return "(todo list is empty)"
        icon = {"done": "[x]", "in_progress": "[~]", "pending": "[ ]"}
        return "\n".join(f"{icon.get(i.get('status', 'pending'), '[ ]')} {i['text']}" for i in self.items)

    async def run(self, action: str = "list", items: list[dict[str, str]] | None = None, **_: Any) -> ToolResult:
        if action == "set":
            if not isinstance(items, list):
                return ToolResult(self.name, ToolStatus.ERROR, error="action='set' requires `items`.")
            cleaned: list[dict[str, str]] = []
            for item in items:
                if not isinstance(item, dict) or not item.get("text"):
                    continue
                status = str(item.get("status") or "pending")
                if status not in ("pending", "in_progress", "done"):
                    status = "pending"
                cleaned.append({"text": str(item["text"]), "status": status})
            self.items = cleaned
            return ToolResult(self.name, ToolStatus.SUCCESS, output=f"Todo list set:\n{self._render()}")
        return ToolResult(self.name, ToolStatus.SUCCESS, output=self._render())
