"""Dynamic (generated) task store — persistence + in-process cache (req. 3, §6.3).

The curated repository is in-memory over a static ``TASKS`` list. Live-generated,
sandbox-verified tasks (see ``app.tasks.generator``) must also be:

  * **Addressable by ``get_task(task_id)``** for the next Run & Check, even if a
    different worker / a restart handles the submission.
  * **Subject to the same uniqueness cooldown** — generated ids flow through the
    existing ``task_serve_history`` + ``filter_unique_tasks`` + ``record_serve``
    machinery unchanged (those operate on any object with an ``.id``).

Two-tier design:
  * a process-level dict cache for hot lookups (cheap repeat resolution), and
  * the ``generated_tasks`` Postgres table for durability (source of truth).

All DB access is best-effort/fail-open: persistence failures are logged and the
in-process cache still lets the just-served task be resolved within the worker,
so a generation never crashes a turn.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.db.models import GeneratedTask
from app.db.session import get_session
from app.tasks.repository import Task

logger = logging.getLogger(__name__)

# Process-level cache: task_id -> Task. Bounded loosely; generated tasks are
# small and a single process serves a modest number per run.
_CACHE: dict[str, Task] = {}


def new_generated_id() -> str:
    """Mint a fresh, collision-proof generated task id (``gen_<uuid>``)."""
    return f"gen_{uuid.uuid4().hex}"


def _record_to_task(rec: GeneratedTask) -> Task:
    return Task(
        id=rec.id,
        language=rec.language,
        concept=rec.concept or "",
        skill_id=rec.skill_id,
        difficulty=int(rec.difficulty),
        kind=rec.kind or "practice",
        entry_point=rec.entry_point,
        prompt=rec.prompt,
        reference_solution=rec.reference_solution,
        visible_tests=list(rec.visible_tests or []),
        hidden_tests=list(rec.hidden_tests or []),
    )


def save_generated_task(
    task: Task,
    *,
    topic: str | None = None,
    created_by: str | None = None,
) -> None:
    """Persist a verified generated ``Task`` (DB + in-process cache).

    Fail-open: a DB error is logged and swallowed; the in-process cache still
    holds the task so the immediately-following Run & Check can resolve it.
    """
    _CACHE[task.id] = task
    try:
        with get_session() as session:
            existing = session.get(GeneratedTask, task.id)
            if existing is None:
                session.add(
                    GeneratedTask(
                        id=task.id,
                        language=task.language,
                        concept=task.concept,
                        skill_id=task.skill_id,
                        difficulty=task.difficulty,
                        kind=task.kind,
                        entry_point=task.entry_point,
                        prompt=task.prompt,
                        reference_solution=task.reference_solution,
                        visible_tests=list(task.visible_tests),
                        hidden_tests=list(task.hidden_tests),
                        topic=topic,
                        created_by=created_by,
                    )
                )
    except Exception as exc:  # noqa: BLE001 — fail-open persistence
        logger.warning("Failed to persist generated task %s: %s", task.id, exc)


def get_generated_task(task_id: str) -> Task | None:
    """Resolve a generated task by id: in-process cache first, then Postgres."""
    cached = _CACHE.get(task_id)
    if cached is not None:
        return cached
    try:
        with get_session() as session:
            rec = session.get(GeneratedTask, task_id)
            if rec is None:
                return None
            task = _record_to_task(rec)
    except Exception as exc:  # noqa: BLE001 — fail-open lookup
        logger.warning("Failed to load generated task %s: %s", task_id, exc)
        return None
    _CACHE[task_id] = task
    return task


def generated_tasks_for_skill(
    skill_id: str,
    *,
    language: str | None = None,
    topic: str | None = None,
    limit: int = 50,
) -> list[Task]:
    """Return previously-generated tasks for a skill (for cooldown-aware reuse).

    Lets ``task_selector`` consider already-verified generated tasks (which
    flow through the same uniqueness filter) instead of always minting anew.
    Fail-open: returns an empty list on any DB error.
    """
    try:
        with get_session() as session:
            stmt = select(GeneratedTask).where(GeneratedTask.skill_id == skill_id)
            if language:
                stmt = stmt.where(GeneratedTask.language == language)
            if topic:
                stmt = stmt.where(GeneratedTask.topic == topic)
            rows = session.execute(stmt.limit(limit)).scalars().all()
            tasks = [_record_to_task(r) for r in rows]
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("Failed to list generated tasks for %s: %s", skill_id, exc)
        return []
    for t in tasks:
        _CACHE.setdefault(t.id, t)
    return tasks
