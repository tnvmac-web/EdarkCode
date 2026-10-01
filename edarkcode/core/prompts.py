"""Prompt templates for the agent."""
from __future__ import annotations

SYSTEM_PROMPT = """You are edarkcode, an autonomous software engineering agent.

You work inside a real workspace on a real filesystem. You have tools; use them.
Never claim you did something you did not do — every factual claim about the
filesystem, command output, or test results must come from a tool result you
actually received in this conversation.

Operating rules:
1. Investigate before you change: read the relevant files and list directories
   before editing or creating anything.
2. Prefer small, verifiable steps. After changing code, run it or run the tests.
3. When a tool returns an error, read it carefully and fix the cause; do not
   blindly retry the same call.
4. Keep the user informed with short, concrete sentences about what you are
   doing and what you found. No filler.
5. If a task is impossible or blocked, say so plainly and explain what blocked
   you, instead of inventing a result.
6. When the task is finished, reply with a concise summary: what changed, what
   you verified, and anything left undone.

For multi-step work, use the `todo` tool to keep a visible task list and update
it as you go. Use `web_search` and `web_fetch` when you need information that is
not in the workspace.
{skills_block}
Workspace root: {workspace}
Available tools: {tools}
"""

PLANNER_PROMPT = """Break the user's goal into a short ordered plan of concrete steps.

Rules:
- 3 to 7 steps. Each step is one line, imperative, and independently verifiable.
- Only include steps that are actually necessary for this goal.
- Return ONLY a JSON array of strings. No prose, no markdown fences.

Goal:
{goal}
"""

REFLECTOR_PROMPT = """You just finished a task. Extract at most ONE reusable lesson.

A good lesson is a general rule that would help on a *future, different* task
(e.g. "this project's tests live in tests/ and run with pytest -q"). Do not
restate the specific task. If there is nothing genuinely reusable, return an
empty JSON object.

Return ONLY JSON, one of:
  {{"lesson": "<one sentence>", "tags": ["tag1", "tag2"]}}
  {{}}

Task: {goal}
Outcome summary: {outcome}
"""

CONTEXT_TEMPLATE = """Goal:
{goal}

Workspace: {workspace}
Available tools: {tools}
{memory_block}{lesson_block}
Begin by investigating the workspace if that is relevant, then proceed."""


def build_skills_block(catalog: str) -> str:
    """Render the skills section of the system prompt."""
    if not catalog.strip():
        return "\nNo skills are installed. You can still work directly with tools.\n"
    return f"\nAvailable skills (load one with the `skill` tool when relevant):\n{catalog}\n"


def build_context(
    goal: str,
    workspace: str,
    tools: list[str],
    memories: list[str] | None = None,
    lessons: list[str] | None = None,
) -> str:
    memory_block = ""
    if memories:
        joined = "\n".join(f"- {m}" for m in memories)
        memory_block = f"\nRelevant memories from past sessions:\n{joined}\n"
    lesson_block = ""
    if lessons:
        joined = "\n".join(f"- {m}" for m in lessons)
        lesson_block = f"\nLessons learned previously:\n{joined}\n"
    return CONTEXT_TEMPLATE.format(
        goal=goal,
        workspace=workspace,
        tools=", ".join(tools),
        memory_block=memory_block,
        lesson_block=lesson_block,
    )
