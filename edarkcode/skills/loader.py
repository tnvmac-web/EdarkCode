"""Skills: reusable, discoverable instruction sets the agent loads on demand.

A skill is a directory containing SKILL.md:

    ---
    name: pdf
    description: Use when working with PDF files. Extract, merge, fill forms.
    tags: [documents]
    ---
    # PDF workflows
    ...instructions...

The agent sees only each skill's name and description up front; the full body is
loaded through the `skill` tool when it is actually relevant. This keeps the
system prompt small no matter how many skills exist.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_FRONTMATTER = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path
    tags: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return f"{self.name}: {self.description}"


class SkillRegistry:
    """Discovers SKILL.md files under one or more roots."""

    def __init__(self, roots: Iterable[Path]) -> None:
        self.roots = [Path(r) for r in roots]
        self._skills: dict[str, Skill] = {}
        self.reload()

    # -- discovery ---------------------------------------------------------
    def reload(self) -> None:
        self._skills = {}
        for root in self.roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("SKILL.md")):
                skill = self._parse(path)
                if skill is None:
                    continue
                # Earlier roots win, so workspace skills override global ones.
                self._skills.setdefault(skill.name, skill)

    @staticmethod
    def _parse(path: Path) -> Skill | None:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        meta: dict = {}
        body = raw
        match = _FRONTMATTER.match(raw)
        if match:
            try:
                loaded = yaml.safe_load(match.group(1)) or {}
                if isinstance(loaded, dict):
                    meta = loaded
            except yaml.YAMLError:
                meta = {}
            body = raw[match.end() :]
        name = str(meta.get("name") or path.parent.name).strip()
        description = str(meta.get("description") or "").strip()
        if not description:
            # Fall back to the first non-heading line so the skill is still usable.
            for line in body.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    description = stripped[:200]
                    break
        tags = meta.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        return Skill(
            name=name,
            description=description,
            body=body.strip(),
            path=path,
            tags=[str(t) for t in tags],
        )

    # -- access ------------------------------------------------------------
    def names(self) -> list[str]:
        return sorted(self._skills)

    def get(self, name: str) -> Skill | None:
        if name in self._skills:
            return self._skills[name]
        lowered = name.lower()
        for key, skill in self._skills.items():
            if key.lower() == lowered:
                return skill
        return None

    def all(self) -> list[Skill]:
        return [self._skills[n] for n in self.names()]

    def catalog(self) -> str:
        """Compact name+description listing for the system prompt."""
        skills = self.all()
        if not skills:
            return ""
        return "\n".join(f"- {s.name}: {s.description}" for s in skills)

    def search(self, query: str) -> list[Skill]:
        """Rank skills by keyword overlap with name/description/tags."""
        terms = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2}
        if not terms:
            return []
        scored: list[tuple[int, Skill]] = []
        for skill in self.all():
            haystack = f"{skill.name} {skill.description} {' '.join(skill.tags)}".lower()
            score = sum(1 for t in terms if t in haystack)
            if score:
                scored.append((score, skill))
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        return [s for _, s in scored]

    def __len__(self) -> int:
        return len(self._skills)


def default_roots(workspace: Path, data_dir: Path) -> list[Path]:
    """Workspace skills win over global ones, which win over bundled built-ins."""
    builtin = Path(__file__).resolve().parent / "builtin"
    return [
        Path(workspace) / ".edarkcode" / "skills",
        Path(data_dir) / "skills",
        builtin,
    ]
