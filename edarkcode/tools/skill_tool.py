"""The `skill` tool: lets the agent load a skill's full instructions on demand."""
from __future__ import annotations

from typing import Any

from ..core.types import ToolResult, ToolStatus
from .base import Tool


class SkillTool(Tool):
    name = "skill"
    description = (
        "Load the full instructions for a named skill, or search skills by keyword. "
        "Call with {'name': '<skill>'} to load one, or {'query': '<terms>'} to search."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Exact skill name to load."},
            "query": {"type": "string", "description": "Keyword search across skills."},
        },
        "required": [],
    }

    def __init__(self, workspace: str = ".", registry: Any | None = None) -> None:
        super().__init__(workspace=workspace)
        self.registry = registry

    async def run(self, name: str | None = None, query: str | None = None, **_: Any) -> ToolResult:
        if self.registry is None:
            return ToolResult(self.name, ToolStatus.ERROR, error="No skill registry is configured.")

        if name:
            skill = self.registry.get(name)
            if skill is None:
                available = ", ".join(self.registry.names()) or "(none)"
                return ToolResult(
                    self.name,
                    ToolStatus.ERROR,
                    error=f"Unknown skill '{name}'. Available: {available}",
                )
            header = f"# Skill: {skill.name}\n{skill.description}\n"
            if skill.tags:
                header += f"Tags: {', '.join(skill.tags)}\n"
            return ToolResult(self.name, ToolStatus.SUCCESS, output=f"{header}\n{skill.body}")

        if query:
            hits = self.registry.search(query)
            if not hits:
                return ToolResult(self.name, ToolStatus.SUCCESS, output=f"No skills matched '{query}'.")
            return ToolResult(
                self.name,
                ToolStatus.SUCCESS,
                output="\n".join(f"- {s.name}: {s.description}" for s in hits),
            )

        catalog = self.registry.catalog()
        return ToolResult(self.name, ToolStatus.SUCCESS, output=catalog or "(no skills installed)")
