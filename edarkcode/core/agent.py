"""The agent loop: research -> plan -> execute -> reflect."""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from .config import Settings
from .llm import LLMClient, LLMError
from .prompts import PLANNER_PROMPT, REFLECTOR_PROMPT, SYSTEM_PROMPT, build_context
from .types import (
    AgentPhase,
    AgentState,
    Message,
    Role,
    StreamEvent,
    ToolResult,
    ToolStatus,
)

ToolApprover = Callable[[str, dict[str, Any]], Awaitable[bool]]


class Agent:
    """Runs a goal to completion, emitting StreamEvents for any UI."""

    def __init__(
        self,
        settings: Settings,
        registry: Any,
        llm: LLMClient | None = None,
        approver: ToolApprover | None = None,
        memory: Any = None,
        lessons: Any = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.llm = llm or LLMClient(settings.llm)
        self.approver = approver
        self.memory = memory
        self.lessons = lessons
        self.state = AgentState()
        self.messages: list[Message] = []

    # -- helpers -----------------------------------------------------------
    def _event(self, etype: str, data: Any) -> StreamEvent:
        return StreamEvent(type=etype, data=data)

    def _system(self) -> str:
        if self.settings.agent.system_prompt:
            return self.settings.agent.system_prompt
        return SYSTEM_PROMPT.format(
            workspace=str(self.settings.workspace),
            tools=", ".join(self.registry.names()),
        )

    def _account(self, usage: dict[str, int]) -> None:
        self.state.prompt_tokens += usage.get("prompt_tokens", 0)
        self.state.completion_tokens += usage.get("completion_tokens", 0)

    # -- public API --------------------------------------------------------
    async def run(self, goal: str) -> AsyncIterator[StreamEvent]:
        self.state = AgentState(phase=AgentPhase.RESEARCH)
        yield self._event("phase", {"phase": "research", "label": "Recalling context"})

        memories = self.memory.recall(goal) if self.memory else []
        lessons = self.lessons.relevant(goal) if self.lessons else []
        if memories or lessons:
            yield self._event(
                "message",
                {
                    "role": "system",
                    "content": f"Recalled {len(memories)} memories and {len(lessons)} lessons relevant to this goal.",
                },
            )

        self.messages = [
            Message(
                Role.USER,
                build_context(
                    goal,
                    str(self.settings.workspace),
                    self.registry.names(),
                    memories,
                    lessons,
                ),
            )
        ]

        if self.settings.agent.enable_planning:
            self.state.phase = AgentPhase.PLANNING
            yield self._event("phase", {"phase": "planning", "label": "Planning"})
            self.state.plan = await self._make_plan(goal)
            yield self._event("plan", {"steps": self.state.plan})

        self.state.phase = AgentPhase.EXECUTING
        yield self._event("phase", {"phase": "executing", "label": "Executing"})

        final_text = ""
        async for event in self._execution_loop():
            if event.type == "message" and isinstance(event.data, dict) and event.data.get("final"):
                final_text = event.data.get("content", "")
            yield event

        if self.state.phase is AgentPhase.COMPLETE and self.settings.agent.enable_reflection:
            self.state.phase = AgentPhase.REFLECTING
            yield self._event("phase", {"phase": "reflecting", "label": "Reflecting"})
            await self._reflect(goal, final_text)

        if self.memory:
            self.memory.remember(
                f"Task: {goal} -> {final_text[:300] or self.state.phase.value}",
                tags=["task"],
            )

        # On error the terminal event is the "error" event emitted earlier;
        # do not follow a failure with a "complete" event.
        if self.state.phase is AgentPhase.ERROR:
            return

        yield self._event(
            "complete",
            {
                "phase": self.state.phase.value,
                "iterations": self.state.iteration,
                "tool_calls": self.state.total_tool_calls,
                "prompt_tokens": self.state.prompt_tokens,
                "completion_tokens": self.state.completion_tokens,
                "result": final_text,
            },
        )

    # -- internals ---------------------------------------------------------
    async def _make_plan(self, goal: str) -> list[str]:
        try:
            resp = await self.llm.complete(
                [Message(Role.USER, PLANNER_PROMPT.format(goal=goal))],
                system="You are a precise planning assistant. Output JSON only.",
            )
            self._account(resp.usage)
            text = resp.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            steps = json.loads(text)
            if isinstance(steps, list):
                return [str(s) for s in steps][:7]
        except (LLMError, json.JSONDecodeError, IndexError, ValueError):
            pass
        return []

    async def _execution_loop(self) -> AsyncIterator[StreamEvent]:
        max_iter = self.settings.agent.max_iterations
        for iteration in range(1, max_iter + 1):
            self.state.iteration = iteration
            yield self._event("iteration", {"iteration": iteration, "max": max_iter})

            try:
                response = await self.llm.complete(
                    self.messages,
                    tools=self.registry.schemas(),
                    system=self._system(),
                )
            except LLMError as exc:
                self.state.phase = AgentPhase.ERROR
                yield self._event("error", {"message": str(exc)})
                return

            self._account(response.usage)
            self.messages.append(
                Message(Role.ASSISTANT, response.content, tool_calls=response.tool_calls)
            )

            if response.content:
                yield self._event(
                    "message",
                    {
                        "role": "assistant",
                        "content": response.content,
                        "final": not response.tool_calls,
                    },
                )

            if not response.tool_calls:
                self.state.phase = AgentPhase.COMPLETE
                return

            for call in response.tool_calls:
                async for event in self._handle_call(call):
                    yield event

            if self.state.consecutive_errors >= self.settings.agent.max_consecutive_errors:
                self.state.phase = AgentPhase.ERROR
                yield self._event(
                    "error",
                    {
                        "message": (
                            f"Stopping: {self.state.consecutive_errors} consecutive tool errors. "
                            "The agent could not make progress."
                        )
                    },
                )
                return

        self.state.phase = AgentPhase.ERROR
        yield self._event(
            "error",
            {"message": f"Reached the iteration limit ({max_iter}) without finishing."},
        )

    async def _handle_call(self, call: dict[str, Any]) -> AsyncIterator[StreamEvent]:
        fn = call.get("function", {})
        name = fn.get("name", "")
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except (json.JSONDecodeError, TypeError):
            args = {}
        call_id = call.get("id") or f"call_{int(time.time() * 1000)}"

        self.state.total_tool_calls += 1
        yield self._event("tool_call", {"id": call_id, "name": name, "arguments": args})

        approved = True
        if self.approver and not self.settings.agent.auto_approve_tools:
            approved = await self.approver(name, args)

        if not approved:
            result = ToolResult(
                tool_name=name,
                status=ToolStatus.DENIED,
                error="User denied this tool call.",
            )
            self.state.consecutive_errors += 1
        else:
            started = time.perf_counter()
            result = await self.registry.dispatch(name, args)
            result.duration_ms = (time.perf_counter() - started) * 1000
            if result.ok:
                self.state.consecutive_errors = 0
            else:
                self.state.consecutive_errors += 1

        self.messages.append(
            Message(Role.TOOL, result.as_text(), tool_call_id=call_id, name=name)
        )
        yield self._event(
            "tool_result",
            {
                "id": call_id,
                "name": name,
                "status": result.status.value,
                "output": result.output,
                "error": result.error,
                "duration_ms": round(result.duration_ms, 1),
            },
        )

    async def _reflect(self, goal: str, outcome: str) -> None:
        if not self.lessons:
            return
        try:
            resp = await self.llm.complete(
                [
                    Message(
                        Role.USER,
                        REFLECTOR_PROMPT.format(goal=goal, outcome=outcome[:1000] or "(no summary)"),
                    )
                ],
                system="You extract reusable engineering lessons. Output JSON only.",
            )
            self._account(resp.usage)
            text = resp.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            lesson = data.get("lesson") if isinstance(data, dict) else None
            if lesson:
                self.lessons.record(str(lesson), tags=data.get("tags") or [])
        except (LLMError, json.JSONDecodeError, ValueError, AttributeError):
            return
