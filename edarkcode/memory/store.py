"""Memory: durable notes and lessons that survive across sessions."""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]+", text.lower()) if len(t) > 2}


@dataclass
class Entry:
    text: str
    tags: list[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    hits: int = 0


class _JsonlStore:
    """Append-only JSONL store with in-memory index and lexical recall."""

    def __init__(self, path: Path, max_entries: int) -> None:
        self.path = Path(path)
        self.max_entries = max_entries
        self._entries: list[Entry] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                self._entries.append(
                    Entry(
                        text=data["text"],
                        tags=list(data.get("tags") or []),
                        created=float(data.get("created", time.time())),
                        hits=int(data.get("hits", 0)),
                    )
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue

    def _append(self, entry: Entry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._compact()

    def _compact(self) -> None:
        self._entries = self._entries[-self.max_entries :]
        self.path.write_text(
            "\n".join(json.dumps(asdict(e)) for e in self._entries) + "\n",
            encoding="utf-8",
        )

    def _score(self, query_tokens: set[str], entry: Entry) -> float:
        if not query_tokens:
            return 0.0
        entry_tokens = _tokens(entry.text) | {t.lower() for t in entry.tags}
        if not entry_tokens:
            return 0.0
        overlap = len(query_tokens & entry_tokens)
        if overlap == 0:
            return 0.0
        # Jaccard-ish, with a mild recency bonus.
        base = overlap / len(query_tokens | entry_tokens)
        age_days = (time.time() - entry.created) / 86400
        recency = 1.0 / (1.0 + age_days / 30.0)
        return base * (0.8 + 0.2 * recency)

    def search(self, query: str, limit: int = 5, min_score: float = 0.05) -> list[Entry]:
        q = _tokens(query)
        scored = [(self._score(q, e), e) for e in self._entries]
        scored = [(s, e) for s, e in scored if s >= min_score]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        out = [e for _, e in scored[:limit]]
        for e in out:
            e.hits += 1
        return out

    def all(self) -> list[Entry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


class MemoryStore:
    """Episodic memory: what happened in past sessions."""

    def __init__(self, path: Path, max_entries: int = 5000, recall_limit: int = 5) -> None:
        self._store = _JsonlStore(Path(path), max_entries)
        self.recall_limit = recall_limit

    def remember(self, text: str, tags: list[str] | None = None) -> None:
        if not text.strip():
            return
        self._store._append(Entry(text=text.strip(), tags=tags or []))

    def recall(self, query: str, limit: int | None = None) -> list[str]:
        hits = self._store.search(query, limit=limit or self.recall_limit)
        return [e.text for e in hits]

    def entries(self) -> list[Entry]:
        return self._store.all()

    def __len__(self) -> int:
        return len(self._store)


class LessonStore:
    """Procedural memory: reusable lessons distilled from finished tasks."""

    def __init__(self, path: Path, max_entries: int = 1000) -> None:
        self._store = _JsonlStore(Path(path), max_entries)

    def record(self, lesson: str, tags: list[str] | None = None) -> None:
        if not lesson.strip():
            return
        # Skip near-duplicates.
        existing = _tokens(lesson)
        for e in self._store.all():
            other = _tokens(e.text)
            if existing and other and len(existing & other) / len(existing | other) > 0.8:
                return
        self._store._append(Entry(text=lesson.strip(), tags=tags or []))

    def relevant(self, query: str, limit: int = 3) -> list[str]:
        hits = self._store.search(query, limit=limit)
        return [e.text for e in hits]

    def lessons(self) -> list[Entry]:
        return self._store.all()

    def __len__(self) -> int:
        return len(self._store)
