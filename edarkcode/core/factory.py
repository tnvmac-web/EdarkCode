"""Assembles a ready-to-run Agent from settings."""
from __future__ import annotations

from pathlib import Path

from .agent import Agent, ToolApprover
from .config import Settings
from .llm import LLMClient


def build_registry(workspace: Path):
    """Create a ToolRegistry with all built-in tools bound to a workspace."""
    from ..tools.base import ToolRegistry
    from ..tools.files import EditFileTool, ListDirTool, ReadFileTool, SearchTool, WriteFileTool
    from ..tools.shell import ShellTool

    registry = ToolRegistry()
    ws = str(workspace)
    for tool_cls in (ListDirTool, ReadFileTool, WriteFileTool, EditFileTool, SearchTool, ShellTool):
        registry.register(tool_cls(workspace=ws))
    return registry


def build_agent(
    settings: Settings,
    approver: ToolApprover | None = None,
    with_memory: bool = True,
) -> Agent:
    """Wire up an Agent with tools, memory and lessons per settings."""
    registry = build_registry(settings.workspace)

    memory = None
    lessons = None
    if with_memory and settings.memory.enabled:
        from ..memory.store import LessonStore, MemoryStore

        memory = MemoryStore(
            settings.memory.path,
            max_entries=settings.memory.max_entries,
            recall_limit=settings.memory.recall_limit,
        )
        if settings.self_improvement.enabled:
            lessons = LessonStore(
                settings.self_improvement.path,
                max_entries=settings.self_improvement.max_lessons,
            )

    llm = LLMClient(settings.llm)
    return Agent(
        settings=settings,
        registry=registry,
        llm=llm,
        approver=approver,
        memory=memory,
        lessons=lessons,
    )
