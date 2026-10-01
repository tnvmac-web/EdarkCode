"""Tests for the agent loop."""
from __future__ import annotations

from edarkcode.core.agent import Agent
from edarkcode.core.factory import build_registry
from edarkcode.core.types import AgentPhase, LLMResponse

from .conftest import FakeLLM, tool_call


async def _collect(agent: Agent, goal: str):
    return [event async for event in agent.run(goal)]


def _agent(settings, responses) -> Agent:
    return Agent(
        settings=settings,
        registry=build_registry(settings.workspace),
        llm=FakeLLM(responses),
    )


async def test_plain_answer_completes(settings):
    agent = _agent(settings, [LLMResponse(content="All done.")])
    events = await _collect(agent, "say hello")
    assert events[-1].type == "complete"
    assert events[-1].data["result"] == "All done."
    assert agent.state.phase is AgentPhase.COMPLETE


async def test_tool_call_is_executed(settings):
    (settings.workspace / "hello.txt").write_text("hi there", encoding="utf-8")
    responses = [
        LLMResponse(content="Reading.", tool_calls=[tool_call("read_file", {"path": "hello.txt"})]),
        LLMResponse(content="The file says hi there."),
    ]
    agent = _agent(settings, responses)
    events = await _collect(agent, "read hello.txt")

    calls = [e for e in events if e.type == "tool_call"]
    results = [e for e in events if e.type == "tool_result"]
    assert len(calls) == 1 and calls[0].data["name"] == "read_file"
    assert len(results) == 1 and results[0].data["status"] == "success"
    assert "hi there" in results[0].data["output"]
    assert agent.state.total_tool_calls == 1


async def test_tool_can_create_file(settings):
    responses = [
        LLMResponse(tool_calls=[tool_call("write_file", {"path": "made.py", "content": "print(1)\n"})]),
        LLMResponse(content="Created made.py"),
    ]
    agent = _agent(settings, responses)
    await _collect(agent, "create a file")
    assert (settings.workspace / "made.py").read_text(encoding="utf-8") == "print(1)\n"


async def test_tool_error_is_reported_not_fatal(settings):
    responses = [
        LLMResponse(tool_calls=[tool_call("read_file", {"path": "nope.txt"})]),
        LLMResponse(content="That file does not exist."),
    ]
    agent = _agent(settings, responses)
    events = await _collect(agent, "read nope.txt")
    results = [e for e in events if e.type == "tool_result"]
    assert results[0].data["status"] == "error"
    assert events[-1].type == "complete"


async def test_consecutive_errors_stop_the_agent(settings):
    settings.agent.max_consecutive_errors = 2
    responses = [
        LLMResponse(tool_calls=[tool_call("run_shell", {"command": "exit 1"}, "c1")]),
        LLMResponse(tool_calls=[tool_call("run_shell", {"command": "exit 1"}, "c2")]),
        LLMResponse(content="should not reach"),
    ]
    agent = _agent(settings, responses)
    events = await _collect(agent, "keep failing")
    assert events[-1].type == "error"
    assert agent.state.phase is AgentPhase.ERROR


async def test_iteration_limit_is_enforced(settings):
    settings.agent.max_iterations = 2
    settings.agent.max_consecutive_errors = 99
    responses = [
        LLMResponse(tool_calls=[tool_call("list_dir", {}, "c1")]),
        LLMResponse(tool_calls=[tool_call("list_dir", {}, "c2")]),
        LLMResponse(tool_calls=[tool_call("list_dir", {}, "c3")]),
    ]
    agent = _agent(settings, responses)
    events = await _collect(agent, "loop forever")
    assert events[-1].type == "error"
    assert "iteration limit" in events[-1].data["message"]


async def test_denied_tool_is_reported(settings):
    async def deny(name, args):
        return False

    settings.agent.auto_approve_tools = False
    agent = Agent(
        settings=settings,
        registry=build_registry(settings.workspace),
        llm=FakeLLM(
            [
                LLMResponse(tool_calls=[tool_call("write_file", {"path": "x.txt", "content": "no"})]),
                LLMResponse(content="User declined."),
            ]
        ),
        approver=deny,
    )
    events = await _collect(agent, "write a file")
    results = [e for e in events if e.type == "tool_result"]
    assert results[0].data["status"] == "denied"
    assert not (settings.workspace / "x.txt").exists()


async def test_unknown_tool_is_an_error(settings):
    responses = [
        LLMResponse(tool_calls=[tool_call("nonexistent_tool", {})]),
        LLMResponse(content="ok"),
    ]
    agent = _agent(settings, responses)
    events = await _collect(agent, "use a bad tool")
    results = [e for e in events if e.type == "tool_result"]
    assert results[0].data["status"] == "error"
    assert "Unknown tool" in results[0].data["error"]
