"""Filesystem tools, sandboxed to the workspace root."""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from ..core.types import ToolResult, ToolStatus
from .base import Tool

MAX_READ_BYTES = 400_000
MAX_OUTPUT_CHARS = 30_000
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build"}


class WorkspaceTool(Tool):
    """Base class that resolves and validates paths inside the workspace."""

    def _resolve(self, path: str) -> Path:
        root = Path(self.workspace).resolve()
        candidate = (root / path).resolve() if not os.path.isabs(path) else Path(path).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"Path '{path}' escapes the workspace root ({root}).")
        return candidate


class ListDirTool(WorkspaceTool):
    name = "list_dir"
    description = "List files and directories under a path in the workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path relative to workspace. Default '.'"},
            "depth": {"type": "integer", "description": "Recursion depth (1-3). Default 1"},
        },
        "required": [],
    }

    async def run(self, path: str = ".", depth: int = 1, **_: Any) -> ToolResult:
        try:
            target = self._resolve(path)
        except ValueError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=str(e))
        if not target.exists():
            return ToolResult(self.name, ToolStatus.ERROR, error=f"No such path: {path}")
        if target.is_file():
            rel = target.relative_to(Path(self.workspace).resolve())
            return ToolResult(self.name, ToolStatus.SUCCESS, output=str(rel))

        depth = max(1, min(int(depth), 3))
        lines: list[str] = []
        root = Path(self.workspace).resolve()

        def walk(d: Path, level: int) -> None:
            try:
                entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            except PermissionError:
                return
            for entry in entries:
                if entry.name in SKIP_DIRS:
                    continue
                rel = entry.relative_to(root)
                if entry.is_dir():
                    lines.append(f"{'  ' * (level - 1)}{rel}/")
                    if level < depth:
                        walk(entry, level + 1)
                else:
                    lines.append(f"{'  ' * (level - 1)}{rel}")

        walk(target, 1)
        output = "\n".join(lines[:2000]) or "(empty directory)"
        return ToolResult(self.name, ToolStatus.SUCCESS, output=output)


class ReadFileTool(WorkspaceTool):
    name = "read_file"
    description = "Read a text file from the workspace. Supports line ranges."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to workspace."},
            "start_line": {"type": "integer", "description": "First line (1-indexed). Optional."},
            "end_line": {"type": "integer", "description": "Last line, inclusive. Optional."},
        },
        "required": ["path"],
    }

    async def run(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        **_: Any,
    ) -> ToolResult:
        try:
            target = self._resolve(path)
        except ValueError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=str(e))
        if not target.exists() or not target.is_file():
            return ToolResult(self.name, ToolStatus.ERROR, error=f"No such file: {path}")
        if target.stat().st_size > MAX_READ_BYTES:
            return ToolResult(
                self.name,
                ToolStatus.ERROR,
                error=f"File too large ({target.stat().st_size} bytes). Use start_line/end_line.",
            )
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=str(e))

        lines = text.splitlines()
        if start_line or end_line:
            s = max(1, (start_line or 1)) - 1
            e = (end_line or len(lines))
            lines = lines[s:e]
            offset = s + 1
        else:
            offset = 1
        numbered = [f"{i + offset:>5}| {ln}" for i, ln in enumerate(lines)]
        output = "\n".join(numbered)
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
        return ToolResult(self.name, ToolStatus.SUCCESS, output=output)


class WriteFileTool(WorkspaceTool):
    name = "write_file"
    description = "Create or overwrite a file in the workspace with the given content."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to workspace."},
            "content": {"type": "string", "description": "Full file content to write."},
        },
        "required": ["path", "content"],
    }

    async def run(self, path: str, content: str, **_: Any) -> ToolResult:
        try:
            target = self._resolve(path)
        except ValueError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=str(e))
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            existed = target.exists()
            target.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=str(e))
        verb = "Updated" if existed else "Created"
        return ToolResult(
            self.name,
            ToolStatus.SUCCESS,
            output=f"{verb} {path} ({len(content)} bytes, {content.count(chr(10)) + 1} lines)",
        )


class EditFileTool(WorkspaceTool):
    name = "edit_file"
    description = "Replace an exact string in a file. Fails if the string is missing or ambiguous."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to workspace."},
            "old_string": {"type": "string", "description": "Exact text to find."},
            "new_string": {"type": "string", "description": "Replacement text."},
        },
        "required": ["path", "old_string", "new_string"],
    }

    async def run(self, path: str, old_string: str, new_string: str, **_: Any) -> ToolResult:
        try:
            target = self._resolve(path)
        except ValueError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=str(e))
        if not target.exists():
            return ToolResult(self.name, ToolStatus.ERROR, error=f"No such file: {path}")
        text = target.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_string)
        if count == 0:
            return ToolResult(self.name, ToolStatus.ERROR, error="old_string not found in file.")
        if count > 1:
            return ToolResult(
                self.name,
                ToolStatus.ERROR,
                error=f"old_string appears {count} times; include more context to make it unique.",
            )
        target.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
        return ToolResult(self.name, ToolStatus.SUCCESS, output=f"Edited {path}.")


class SearchTool(WorkspaceTool):
    name = "search"
    description = "Search file contents by regex, or find files by glob pattern."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex (content mode) or glob like '*.py' (files mode)."},
            "mode": {"type": "string", "enum": ["content", "files"], "description": "Default 'content'."},
            "path": {"type": "string", "description": "Subdirectory to search. Default '.'"},
            "max_results": {"type": "integer", "description": "Cap results. Default 50."},
        },
        "required": ["pattern"],
    }

    async def run(
        self,
        pattern: str,
        mode: str = "content",
        path: str = ".",
        max_results: int = 50,
        **_: Any,
    ) -> ToolResult:
        try:
            root = self._resolve(path)
        except ValueError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=str(e))
        if not root.exists():
            return ToolResult(self.name, ToolStatus.ERROR, error=f"No such path: {path}")

        max_results = max(1, min(int(max_results), 500))
        ws_root = Path(self.workspace).resolve()
        hits: list[str] = []

        if mode == "files":
            for p in root.rglob("*"):
                if any(part in SKIP_DIRS for part in p.parts):
                    continue
                if p.is_file() and fnmatch.fnmatch(p.name, pattern):
                    hits.append(str(p.relative_to(ws_root)))
                    if len(hits) >= max_results:
                        break
            return ToolResult(
                self.name,
                ToolStatus.SUCCESS,
                output="\n".join(hits) or "(no matching files)",
            )

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=f"Invalid regex: {e}")

        for p in root.rglob("*"):
            if len(hits) >= max_results:
                break
            if not p.is_file() or any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.stat().st_size > MAX_READ_BYTES:
                continue
            try:
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if regex.search(line):
                        hits.append(f"{p.relative_to(ws_root)}:{i}: {line.strip()[:200]}")
                        if len(hits) >= max_results:
                            break
            except OSError:
                continue
        return ToolResult(self.name, ToolStatus.SUCCESS, output="\n".join(hits) or "(no matches)")
