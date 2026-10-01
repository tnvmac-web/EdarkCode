"""Tests for the skills system and the skill tool."""
from __future__ import annotations

from pathlib import Path

from edarkcode.core.types import ToolStatus
from edarkcode.skills.loader import SkillRegistry, default_roots
from edarkcode.tools.skill_tool import SkillTool

SKILL_TEMPLATE = """---
name: {name}
description: {desc}
tags: [{tags}]
---

# {name}
Body content for {name}.
"""


def make_skill(root: Path, name: str, desc: str = "does a thing", tags: str = "a, b") -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(SKILL_TEMPLATE.format(name=name, desc=desc, tags=tags), encoding="utf-8")


def test_discovers_skills(tmp_path):
    make_skill(tmp_path, "alpha")
    make_skill(tmp_path, "beta")
    reg = SkillRegistry([tmp_path])
    assert reg.names() == ["alpha", "beta"]
    assert len(reg) == 2


def test_frontmatter_is_parsed(tmp_path):
    make_skill(tmp_path, "alpha", desc="Extract text from PDFs", tags="docs, pdf")
    skill = SkillRegistry([tmp_path]).get("alpha")
    assert skill is not None
    assert skill.description == "Extract text from PDFs"
    assert skill.tags == ["docs", "pdf"]
    assert "Body content for alpha." in skill.body


def test_missing_description_falls_back_to_first_line(tmp_path):
    d = tmp_path / "nodesc"
    d.mkdir()
    (d / "SKILL.md").write_text("# Heading\n\nActual guidance here.\n", encoding="utf-8")
    skill = SkillRegistry([tmp_path]).get("nodesc")
    assert skill is not None
    assert skill.description == "Actual guidance here."


def test_workspace_overrides_global(tmp_path):
    ws, globaldir = tmp_path / "ws", tmp_path / "global"
    make_skill(ws, "shared", desc="workspace version")
    make_skill(globaldir, "shared", desc="global version")
    reg = SkillRegistry([ws, globaldir])
    assert reg.get("shared").description == "workspace version"


def test_lookup_is_case_insensitive(tmp_path):
    make_skill(tmp_path, "MySkill")
    assert SkillRegistry([tmp_path]).get("myskill") is not None


def test_search_ranks_by_relevance(tmp_path):
    make_skill(tmp_path, "pdf-tools", desc="Extract and merge PDF files", tags="pdf")
    make_skill(tmp_path, "git-stuff", desc="Commit and branch with git", tags="git")
    hits = SkillRegistry([tmp_path]).search("merge pdf files")
    assert hits and hits[0].name == "pdf-tools"


def test_catalog_lists_name_and_description(tmp_path):
    make_skill(tmp_path, "alpha", desc="the alpha skill")
    catalog = SkillRegistry([tmp_path]).catalog()
    assert "alpha: the alpha skill" in catalog


def test_bundled_skills_are_discoverable():
    """The skills shipped inside the package must load with no setup."""
    roots = default_roots(Path.cwd(), Path.home() / ".edarkcode")
    reg = SkillRegistry(roots)
    for expected in ("systematic-debugging", "code-review", "testing", "web-research", "git-workflow"):
        assert reg.get(expected) is not None, f"bundled skill missing: {expected}"


async def test_skill_tool_loads_body(tmp_path):
    make_skill(tmp_path, "alpha", desc="the alpha skill")
    reg = SkillRegistry([tmp_path])
    tool = SkillTool(workspace=str(tmp_path), registry=reg)
    res = await tool.run(name="alpha")
    assert res.status is ToolStatus.SUCCESS
    assert "Body content for alpha." in res.output
    assert "the alpha skill" in res.output


async def test_skill_tool_unknown_name_lists_available(tmp_path):
    make_skill(tmp_path, "alpha")
    tool = SkillTool(workspace=str(tmp_path), registry=SkillRegistry([tmp_path]))
    res = await tool.run(name="nope")
    assert res.status is ToolStatus.ERROR
    assert "alpha" in res.error


async def test_skill_tool_search(tmp_path):
    make_skill(tmp_path, "pdf-tools", desc="Extract PDF files")
    tool = SkillTool(workspace=str(tmp_path), registry=SkillRegistry([tmp_path]))
    res = await tool.run(query="pdf")
    assert res.status is ToolStatus.SUCCESS
    assert "pdf-tools" in res.output


async def test_skill_tool_without_registry_errors(tmp_path):
    tool = SkillTool(workspace=str(tmp_path), registry=None)
    res = await tool.run(name="anything")
    assert res.status is ToolStatus.ERROR


async def test_skill_tool_lists_catalog(tmp_path):
    make_skill(tmp_path, "alpha", desc="the alpha skill")
    tool = SkillTool(workspace=str(tmp_path), registry=SkillRegistry([tmp_path]))
    res = await tool.run()
    assert res.status is ToolStatus.SUCCESS
    assert "alpha" in res.output
