"""Assembles a ready-to-run Agent from settings."""
from __future__ import annotations

from pathlib import Path

from .agent import Agent, ToolApprover
from .config import Settings
from .llm import LLMClient


def build_registry(workspace: Path, skills=None):
    """Create a ToolRegistry with all built-in tools bound to a workspace."""
    from ..skills.loader import SkillRegistry, default_roots
    from ..tools.base import ToolRegistry
    from ..tools.files import EditFileTool, ListDirTool, ReadFileTool, SearchTool, WriteFileTool
    from ..tools.planning import GlobTool, MultiEditTool, TodoTool
    from ..tools.shell import ShellTool
    from ..tools.skill_tool import SkillTool
    from ..tools.web import WebFetchTool, WebSearchTool

    if skills is None:
        skills = SkillRegistry(default_roots(Path(workspace), Settings().data_dir))

    registry = ToolRegistry()
    ws = str(workspace)
    for tool_cls in (
        ListDirTool,
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        MultiEditTool,
        SearchTool,
        GlobTool,
        ShellTool,
        WebFetchTool,
        WebSearchTool,
        TodoTool,
    ):
        registry.register(tool_cls(workspace=ws))
    registry.register(SkillTool(workspace=ws, registry=skills))
    return registry


def build_skills(settings: Settings):
    from ..skills.loader import SkillRegistry, default_roots

    return SkillRegistry(default_roots(Path(settings.workspace), settings.data_dir))


def build_agent(
    settings: Settings,
    approver: ToolApprover | None = None,
    with_memory: bool = True,
    skills=None,
) -> Agent:
    """Wire up an Agent with tools, skills, memory and lessons per settings."""
    if skills is None:
        skills = build_skills(settings)
    registry = build_registry(settings.workspace, skills=skills)

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
        skills=skills,
    )
