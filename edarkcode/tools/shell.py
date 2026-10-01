"""Shell execution tool."""
from __future__ import annotations

import asyncio
from typing import Any

from ..core.types import ToolResult, ToolStatus
from .base import Tool

MAX_OUTPUT_CHARS = 30_000
DENY_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    ":(){:|:&};:",
    "mkfs",
    "dd if=/dev/zero of=/dev/sd",
    "shutdown",
    "reboot",
    "> /dev/sda",
]


class ShellTool(Tool):
    name = "run_shell"
    description = "Run a shell command in the workspace and return stdout/stderr and the exit code."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute."},
            "timeout": {"type": "integer", "description": "Timeout in seconds. Default 120."},
        },
        "required": ["command"],
    }

    async def run(self, command: str, timeout: int = 120, **_: Any) -> ToolResult:
        lowered = command.lower()
        for pat in DENY_PATTERNS:
            if pat in lowered:
                return ToolResult(
                    self.name,
                    ToolStatus.ERROR,
                    error=f"Refused: command matches a destructive pattern ('{pat}').",
                )
        timeout = max(1, min(int(timeout), 900))
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as e:
            return ToolResult(self.name, ToolStatus.ERROR, error=f"Failed to start command: {e}")

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(self.name, ToolStatus.ERROR, error=f"Command timed out after {timeout}s.")

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        combined = ""
        if stdout:
            combined += stdout
        if stderr:
            combined += ("\n" if combined else "") + f"[stderr]\n{stderr}"
        if len(combined) > MAX_OUTPUT_CHARS:
            combined = combined[:MAX_OUTPUT_CHARS] + "\n... (truncated)"

        code = proc.returncode or 0
        status = ToolStatus.SUCCESS if code == 0 else ToolStatus.ERROR
        if status is ToolStatus.SUCCESS:
            return ToolResult(self.name, status, output=f"exit 0\n{combined}".rstrip())
        return ToolResult(
            self.name,
            status,
            output=combined,
            error=f"Command exited with code {code}.",
        )
