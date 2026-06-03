"""Code Validator node — runs the student's submitted code against tests.

Objective evaluation via the sandbox (visible + hidden tests), not LLM opinion.
Increments the student's solve count (drives the uniqueness cooldown) and records
the attempt. Routes to success (Progress Updater) or failure (Error Classifier).
"""
from __future__ import annotations

import logging

from app.db.progress_repo import increment_solve_count, record_attempt
from app.execution.base import check_typed_answer
from app.execution.factory import get_executor
from app.graph.nodes._error_utils import detect_input_issue, extract_student_error
from app.graph.state import TutorState
from app.tasks.repository import get_task

logger = logging.getLogger(__name__)


def code_validator(state: TutorState) -> dict:
    code = state.get("submitted_code") or ""
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    task_id = state.get("current_task_id")

    task = get_task(task_id) if task_id else None
    if task is None:
        return {
            "agent_response": (
                "I received your code, but there's no active task to check it "
                "against. Set a goal or ask for a task first."
            ),
            "next_action": "respond",
        }

    # Problem 4: ``predict_output`` / ``trace_value`` ask the student to TYPE an
    # expected value (not write a function). There is no entry_point to call, so
    # we check the typed answer against ``expected_answer`` via a pure,
    # deterministic comparison shaped like a sandbox run (it emits the same
    # ``FAIL:`` / ``__TESTS__`` convention). All code-producing types
    # (implement_return, find_the_bug, fill_in_the_blank, refactor, …) keep using
    # the existing run-against-tests harness unchanged. Unknown types degrade to
    # implement_return via ``Task.is_answer_type`` / normalize_exercise_type.
    is_answer_type = False
    try:
        is_answer_type = task.is_answer_type()
    except Exception:  # noqa: BLE001 — fail-open: treat as a normal code task
        is_answer_type = False

    if is_answer_type:
        result = check_typed_answer(code, getattr(task, "expected_answer", ""))
    else:
        executor = get_executor()
        result = executor.run(
            task.language, code, task.entry_point, task.all_test_cases()
        )

    # Each submission counts as a "solve" for cooldown purposes.
    solve_count = increment_solve_count(user_id) if user_id else 0

    exec_dict = {
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "passed_tests": result.passed_tests,
        "total_tests": result.total_tests,
        "duration_ms": result.duration_ms,
        "timed_out": result.timed_out,
    }

    if user_id:
        record_attempt(
            user_id=user_id,
            session_id=session_id,
            skill_id=task.skill_id,
            task_id=task.id,
            submitted_code=code,
            test_results=exec_dict,
            error_type=None,
            success=result.success,
        )

    logger.info(
        "Validated task=%s success=%s (%d/%d) solve_count=%d",
        task.id, result.success, result.passed_tests, result.total_tests, solve_count,
    )

    out: dict = {
        "execution_result": exec_dict,
        "current_skill": task.skill_id,
        "solve_count": solve_count,
        # ``last_passed`` drives the Run & Check de-duplication (req. 1, Group C):
        # on PASS the just-solved task is not re-stated; on FAIL the failure path
        # adds remediation links/excerpt.
        "last_passed": result.success,
        "next_action": "passed" if result.success else "failed",
    }

    if not result.success:
        # Fail-path remediation fix (Problems 1 & 2): surface the *real* student
        # error so the classifier / explanation generator are grounded in the
        # student's actual submission rather than generic web snippets. All of
        # these helpers are pure + never raise (fail-open).
        student_error = extract_student_error(exec_dict)
        # Non-code / empty / SyntaxError guard (Problem 1, Group B): when the
        # submission isn't valid code we point at the offending line/characters
        # rather than pretending it was a normal failed attempt. This guard
        # applies ONLY to code-producing exercises — for predict_output /
        # trace_value the student submits a TYPED VALUE (e.g. "8 5"), which is
        # legitimately "not code", so we must not flag it as a syntax error.
        input_diagnosis = None if is_answer_type else detect_input_issue(code, task.language)
        out["student_error"] = student_error
        out["failed_cases"] = (student_error.get("errors") or []) + (
            student_error.get("fails") or []
        )
        out["error_symbol"] = student_error.get("symbol")
        out["input_diagnosis"] = input_diagnosis
    else:
        # Clear any stale failure analysis from a previous turn on success.
        out["student_error"] = None
        out["failed_cases"] = []
        out["input_diagnosis"] = None
        out["error_symbol"] = None
        out["error_explanation"] = ""

    return out
