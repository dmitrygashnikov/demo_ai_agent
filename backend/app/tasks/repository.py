"""In-memory repository over the curated TASKS seed.

Tasks live in code (curated demo base); this thin repository provides lookup by
id / skill / difficulty and exposes the test cases used by the executor.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.execution.base import TestCase
from app.seed.content.curated import TASKS


@dataclass
class Task:
    id: str
    language: str
    concept: str
    skill_id: str
    difficulty: int
    kind: str
    entry_point: str
    prompt: str
    reference_solution: str
    visible_tests: list[dict]
    hidden_tests: list[dict]

    def all_test_cases(self) -> list[TestCase]:
        cases = self.visible_tests + self.hidden_tests
        return [TestCase(args=c["args"], expected=c["expected"]) for c in cases]

    def visible_test_cases(self) -> list[TestCase]:
        return [TestCase(args=c["args"], expected=c["expected"]) for c in self.visible_tests]


def _make_task(d: dict[str, Any]) -> Task:
    return Task(
        id=str(d["id"]),
        language=str(d["language"]),
        concept=str(d["concept"]),
        skill_id=str(d["skill_id"]),
        difficulty=int(d["difficulty"]),
        kind=str(d["kind"]),
        entry_point=str(d["entry_point"]),
        prompt=str(d["prompt"]),
        reference_solution=str(d["reference_solution"]),
        visible_tests=list(d["visible_tests"]),
        hidden_tests=list(d["hidden_tests"]),
    )


_TASKS: dict[str, Task] = {t["id"]: _make_task(t) for t in TASKS}


def get_task(task_id: str) -> Task | None:
    """Resolve a task id: static curated tasks first, then the dynamic store.

    Generated tasks (``gen_<uuid>``) live in ``app.tasks.dynamic_store`` (a
    process cache backed by Postgres). The dynamic lookup is fail-open: any
    error there returns ``None`` so a missing generated task degrades to "no
    active task" rather than crashing a Run & Check. Imported lazily to avoid a
    circular import (dynamic_store imports ``Task`` from this module).
    """
    task = _TASKS.get(task_id)
    if task is not None:
        return task
    try:
        from app.tasks.dynamic_store import get_generated_task

        return get_generated_task(task_id)
    except Exception:  # noqa: BLE001 — fail-open resolution
        return None


def tasks_for_skill(
    skill_id: str,
    kind: str | None = None,
    max_difficulty: int | None = None,
) -> list[Task]:
    result = [t for t in _TASKS.values() if t.skill_id == skill_id]
    if kind:
        result = [t for t in result if t.kind == kind]
    if max_difficulty is not None:
        result = [t for t in result if t.difficulty <= max_difficulty]
    return result


def all_tasks() -> list[Task]:
    return list(_TASKS.values())
