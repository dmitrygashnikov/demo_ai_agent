"""In-memory repository over the curated TASKS seed.

Tasks live in code (curated demo base); this thin repository provides lookup by
id / skill / difficulty and exposes the test cases used by the executor.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.execution.base import TestCase
from app.seed.content.curated import TASKS


# Exercise-type taxonomy (Problem 4): describes the *kind of cognitive exercise*
# (orthogonal to ``kind`` which is difficulty/role: practice|similar|real_case).
# Adding real variety in essence — not just wording — across served tasks.
#
#   implement_return    — write a function returning a value (the original, only
#                          type until now); checked by the existing run-against-
#                          tests harness.
#   predict_output      — given code, predict the printed/returned result; the
#                          student types the expected value (no function), which
#                          is compared to ``expected_answer``.
#   trace_value         — trace a variable's value after a loop/condition runs;
#                          same typed-answer check as ``predict_output``.
#   find_the_bug        — given a buggy function, fix the bug; student submits the
#                          fixed function → existing harness.
#   fill_in_the_blank   — complete a partial function (blanks marked ``___``);
#                          student submits the completed function → existing
#                          harness.
#   refactor            — rewrite working-but-ugly code keeping behaviour; run
#                          against the SAME tests → existing harness.
#   conditions_branching/ loops_accumulate / io_transform — themed
#                          implement-a-function variants → existing harness.
#
# Types that the student answers by writing code (run against tests):
CODE_EXERCISE_TYPES = frozenset(
    {
        "implement_return",
        "find_the_bug",
        "fill_in_the_blank",
        "refactor",
        "conditions_branching",
        "loops_accumulate",
        "io_transform",
    }
)
# Types where the student types an EXPECTED VALUE (not code), compared to
# ``expected_answer`` — no function call, no sandbox at check time.
ANSWER_EXERCISE_TYPES = frozenset({"predict_output", "trace_value"})

EXERCISE_TYPES = CODE_EXERCISE_TYPES | ANSWER_EXERCISE_TYPES

DEFAULT_EXERCISE_TYPE = "implement_return"


def normalize_exercise_type(value: Any) -> str:
    """Map an arbitrary value to a known exercise type (fail-open).

    Unknown / missing / empty types degrade to ``implement_return`` so the rest
    of the pipeline (harness, prompt rendering, answer check) keeps working —
    the graph never breaks on an unfamiliar type.
    """
    s = str(value or "").strip()
    return s if s in EXERCISE_TYPES else DEFAULT_EXERCISE_TYPE


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
    # Problem 4: the *kind of cognitive exercise*. Defaults to the only legacy
    # type (``implement_return``) so every pre-existing task / generated row is
    # backward-compatible without migration of its semantics.
    exercise_type: str = DEFAULT_EXERCISE_TYPE
    # Supporting fields used only by certain exercise types (None/empty for the
    # classic ``implement_return``):
    #   given_code      — code shown to the student (predict_output/trace_value/
    #                      find_the_bug/refactor). Read-only context.
    #   template        — a partial function with ``___`` blanks (fill_in_the_blank).
    #   expected_answer — the canonical typed answer for predict_output/trace_value
    #                     (string-compared, whitespace-normalised, to the student's
    #                     submitted answer).
    given_code: str = ""
    template: str = ""
    expected_answer: str = ""

    def all_test_cases(self) -> list[TestCase]:
        cases = self.visible_tests + self.hidden_tests
        return [TestCase(args=c["args"], expected=c["expected"]) for c in cases]

    def visible_test_cases(self) -> list[TestCase]:
        return [TestCase(args=c["args"], expected=c["expected"]) for c in self.visible_tests]

    def is_answer_type(self) -> bool:
        """True when the student answers with a typed value, not code."""
        return normalize_exercise_type(self.exercise_type) in ANSWER_EXERCISE_TYPES


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
        exercise_type=normalize_exercise_type(d.get("exercise_type")),
        given_code=str(d.get("given_code") or ""),
        template=str(d.get("template") or ""),
        expected_answer=str(d.get("expected_answer") or ""),
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
