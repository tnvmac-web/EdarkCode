"""Tests for built-in tools, including the workspace sandbox."""
from __future__ import annotations

import pytest

from edarkcode.core.types import ToolStatus
from edarkcode.tools.files import EditFileTool, ListDirTool, ReadFileTool, SearchTool, WriteFileTool
from edarkcode.tools.shell import ShellTool


@pytest.fixture
def ws(tmp_path):
    return str(tmp_path)


async def test_write_then_read(ws):
    w = WriteFileTool(workspace=ws)
    r = ReadFileTool(workspace=ws)
    res = await w.run(path="a/b.txt", content="line1\nline2\n")
    assert res.status is ToolStatus.SUCCESS
    out = await r.run(path="a/b.txt")
    assert "line1" in out.output and "line2" in out.output


async def test_read_missing_file(ws):
    r = ReadFileTool(workspace=ws)
    res = await r.run(path="missing.txt")
    assert res.status is ToolStatus.ERROR


async def test_read_line_range(ws):
    w = WriteFileTool(workspace=ws)
    await w.run(path="n.txt", content="\n".join(f"L{i}" for i in range(1, 11)))
    r = ReadFileTool(workspace=ws)
    res = await r.run(path="n.txt", start_line=3, end_line=5)
    assert "L3" in res.output and "L5" in res.output and "L6" not in res.output


async def test_edit_requires_unique_match(ws):
    w = WriteFileTool(workspace=ws)
    await w.run(path="d.txt", content="same\nsame\n")
    e = EditFileTool(workspace=ws)
    res = await e.run(path="d.txt", old_string="same", new_string="diff")
    assert res.status is ToolStatus.ERROR
    assert "appears 2 times" in res.error


async def test_edit_success(ws):
    w = WriteFileTool(workspace=ws)
    await w.run(path="d.txt", content="hello world\n")
    e = EditFileTool(workspace=ws)
    res = await e.run(path="d.txt", old_string="world", new_string="there")
    assert res.status is ToolStatus.SUCCESS
    assert (await ReadFileTool(workspace=ws).run(path="d.txt")).output.find("there") != -1


async def test_sandbox_blocks_escape(ws):
    r = ReadFileTool(workspace=ws)
    res = await r.run(path="../../etc/passwd")
    assert res.status is ToolStatus.ERROR
    assert "escapes the workspace" in res.error


async def test_sandbox_blocks_absolute_escape(ws):
    w = WriteFileTool(workspace=ws)
    res = await w.run(path="/tmp/evil_edarkcode.txt", content="x")
    assert res.status is ToolStatus.ERROR


async def test_list_dir(ws):
    w = WriteFileTool(workspace=ws)
    await w.run(path="sub/x.txt", content="1")
    await w.run(path="top.txt", content="1")
    res = await ListDirTool(workspace=ws).run(path=".", depth=2)
    assert "top.txt" in res.output and "sub" in res.output


async def test_search_content_and_files(ws):
    w = WriteFileTool(workspace=ws)
    await w.run(path="code.py", content="def needle():\n    pass\n")
    s = SearchTool(workspace=ws)
    content = await s.run(pattern="needle", mode="content")
    assert "code.py" in content.output
    files = await s.run(pattern="*.py", mode="files")
    assert "code.py" in files.output


async def test_shell_runs_and_reports_exit(ws):
    sh = ShellTool(workspace=ws)
    ok = await sh.run(command="echo hello")
    assert ok.status is ToolStatus.SUCCESS and "hello" in ok.output
    bad = await sh.run(command="exit 3")
    assert bad.status is ToolStatus.ERROR


async def test_shell_blocks_destructive(ws):
    sh = ShellTool(workspace=ws)
    res = await sh.run(command="rm -rf /")
    assert res.status is ToolStatus.ERROR
    assert "Refused" in res.error
