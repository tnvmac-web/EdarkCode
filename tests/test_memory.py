"""Tests for memory and lesson stores."""
from __future__ import annotations

from edarkcode.memory.store import LessonStore, MemoryStore


def test_remember_and_recall(tmp_path):
    store = MemoryStore(tmp_path / "m.jsonl")
    store.remember("The project uses pytest for testing", tags=["testing"])
    store.remember("Deployment happens via docker compose", tags=["deploy"])
    hits = store.recall("how do I run the tests")
    assert any("pytest" in h for h in hits)


def test_recall_returns_nothing_for_unrelated(tmp_path):
    store = MemoryStore(tmp_path / "m.jsonl")
    store.remember("The sky is blue today")
    assert store.recall("quantum chromodynamics") == []


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "m.jsonl"
    MemoryStore(path).remember("persisted fact about widgets")
    reopened = MemoryStore(path)
    assert any("widgets" in e.text for e in reopened.entries())


def test_lesson_dedup(tmp_path):
    store = LessonStore(tmp_path / "l.jsonl")
    store.record("Tests live in tests/ and run with pytest -q")
    store.record("Tests live in tests/ and run with pytest -q")
    assert len(store) == 1


def test_lesson_relevance(tmp_path):
    store = LessonStore(tmp_path / "l.jsonl")
    store.record("Database migrations run with alembic upgrade head", tags=["db"])
    store.record("Frontend is built with vite", tags=["frontend"])
    hits = store.relevant("how do I migrate the database")
    assert any("alembic" in h for h in hits)


def test_corrupt_lines_are_skipped(tmp_path):
    path = tmp_path / "m.jsonl"
    path.write_text('{"text": "good one", "tags": [], "created": 1, "hits": 0}\nnot json\n', encoding="utf-8")
    store = MemoryStore(path)
    assert len(store) == 1
