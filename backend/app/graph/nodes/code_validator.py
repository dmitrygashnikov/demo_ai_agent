"""Code Validator node — runs the student's submitted code against tests.

Objective evaluation via the sandbox (visible + hidden tests), not LLM opinion.
Increments the student's solve count (drives the uniqueness cooldown) and records
the attempt. Routes to success (Progress Updater) or failure (Error Classifier).
"""
from __future__ import annotations

import logging

from app.db.progress_repo import increment_solve_count, record_attempt
from app.execution.factory import get_executor
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

    executor = get_executor()
    result = executor.run(task.language, code, task.entry_point, task.all_test_cases())

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

    return {
        "execution_result": exec_dict,
        "current_skill": task.skill_id,
        "solve_count": solve_count,
        # ``last_passed`` drives the Run & Check de-duplication (req. 1, Group C):
        # on PASS the just-solved task is not re-stated; on FAIL the failure path
        # adds remediation links/excerpt.
        "last_passed": result.success,
        "next_action": "passed" if result.success else "failed",
    }
