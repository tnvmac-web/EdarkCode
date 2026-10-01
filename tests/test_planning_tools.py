"""Tests for glob, multi_edit and todo."""
from __future__ import annotations

import pytest

from edarkcode.core.types import ToolStatus
from edarkcode.tools.files import WriteFileTool
from edarkcode.tools.planning import GlobTool, MultiEditTool, TodoTool


@pytest.fixture
def ws(tmp_path):
    return str(tmp_path)


async def test_glob_finds_files(ws):
    w = WriteFileTool(workspace=ws)
    await w.run(path="pkg/a.py", content="a")
    await w.run(path="pkg/b.py", content="b")
    await w.run(path="pkg/c.txt", content="c")
    res = await GlobTool(workspace=ws).run(pattern="**/*.py")
    assert res.status is ToolStatus.SUCCESS
    assert "a.py" in res.output and "b.py" in res.output
    assert "c.txt" not in res.output


async def test_glob_respects_max_results(ws):
    w = WriteFileTool(workspace=ws)
    for i in range(10):
        await w.run(path=f"f{i}.txt", content="x")
    res = await GlobTool(workspace=ws).run(pattern="*.txt", max_results=3)
    assert len(res.output.splitlines()) == 3


async def test_glob_no_matches(ws):
    res = await GlobTool(workspace=ws).run(pattern="**/*.rs")
    assert res.status is ToolStatus.SUCCESS
    assert "no files matched" in res.output


async def test_multi_edit_applies_all(ws):
    w = WriteFileTool(workspace=ws)
    await w.run(path="c.py", content="import os\nx = 1\ny = 2\n")
    res = await MultiEditTool(workspace=ws).run(
        path="c.py",
        edits=[
            {"old_string": "x = 1", "new_string": "x = 10"},
            {"old_string": "y = 2", "new_string": "y = 20"},
        ],
    )
    assert res.status is ToolStatus.SUCCESS
    from edarkcode.tools.files import ReadFileTool

    text = (await ReadFileTool(workspace=ws).run(path="c.py")).output
    assert "x = 10" in text and "y = 20" in text


async def test_multi_edit_is_atomic_on_failure(ws):
    """If any edit fails, the file must be left completely unchanged."""
    w = WriteFileTool(workspace=ws)
    original = "x = 1\ny = 2\n"
    await w.run(path="c.py", content=original)
    res = await MultiEditTool(workspace=ws).run(
        path="c.py",
        edits=[
            {"old_string": "x = 1", "new_string": "x = 10"},
            {"old_string": "does-not-exist", "new_string": "z"},
        ],
    )
    assert res.status is ToolStatus.ERROR
    assert "No changes were written" in res.error
    from edarkcode.tools.files import ReadFileTool

    text = (await ReadFileTool(workspace=ws).run(path="c.py")).output
    assert "x = 1" in text and "x = 10" not in text


async def test_multi_edit_rejects_ambiguous(ws):
    w = WriteFileTool(workspace=ws)
    await w.run(path="c.py", content="dup\ndup\n")
    res = await MultiEditTool(workspace=ws).run(
        path="c.py", edits=[{"old_string": "dup", "new_string": "x"}]
    )
    assert res.status is ToolStatus.ERROR
    assert "appears 2 times" in res.error


async def test_multi_edit_empty_list(ws):
    w = WriteFileTool(workspace=ws)
    await w.run(path="c.py", content="x = 1\n")
    res = await MultiEditTool(workspace=ws).run(path="c.py", edits=[])
    assert res.status is ToolStatus.ERROR


async def test_multi_edit_sandbox(ws):
    res = await MultiEditTool(workspace=ws).run(
        path="../../etc/passwd", edits=[{"old_string": "a", "new_string": "b"}]
    )
    assert res.status is ToolStatus.ERROR


async def test_todo_set_and_list(ws):
    tool = TodoTool(workspace=ws)
    res = await tool.run(
        action="set",
        items=[
            {"text": "read the code", "status": "done"},
            {"text": "write the fix", "status": "in_progress"},
            {"text": "run tests"},
        ],
    )
    assert res.status is ToolStatus.SUCCESS
    assert "[x] read the code" in res.output
    assert "[~] write the fix" in res.output
    assert "[ ] run tests" in res.output

    listing = await tool.run(action="list")
    assert "[x] read the code" in listing.output


async def test_todo_defaults_to_list(ws):
    res = await TodoTool(workspace=ws).run()
    assert res.status is ToolStatus.SUCCESS
    assert "empty" in res.output


async def test_todo_rejects_bad_items(ws):
    res = await TodoTool(workspace=ws).run(action="set", items="not a list")
    assert res.status is ToolStatus.ERROR


async def test_todo_ignores_invalid_status(ws):
    tool = TodoTool(workspace=ws)
    res = await tool.run(action="set", items=[{"text": "a", "status": "bogus"}])
    assert "[ ] a" in res.output
