"""Reflection: turns a finished task into a reusable lesson."""
from __future__ import annotations

from ..core.llm import LLMClient, LLMError
from ..core.prompts import REFLECTOR_PROMPT
from ..core.types import Message, Role
from ..memory.store import LessonStore


class Reflector:
    """Asks the model for one general lesson and stores it if worthwhile."""

    def __init__(self, llm: LLMClient, lessons: LessonStore) -> None:
        self.llm = llm
        self.lessons = lessons

    async def reflect(self, goal: str, outcome: str) -> str | None:
        try:
            resp = await self.llm.complete(
                [Message(Role.USER, REFLECTOR_PROMPT.format(goal=goal, outcome=outcome[:1500]))],
                system="You extract reusable engineering lessons. Output JSON only.",
            )
        except LLMError:
            return None
        import json

        text = resp.content.strip()
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) > 1:
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        lesson = data.get("lesson")
        if not lesson:
            return None
        lesson = str(lesson).strip()
        self.lessons.record(lesson, tags=list(data.get("tags") or []))
        return lesson
