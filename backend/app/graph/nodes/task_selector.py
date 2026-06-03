"""Task Selector node — picks a task for current skill with uniqueness filter.

Applies the cooldown filter (req. 5): a task is not re-served within
``COOLDOWN_SOLVES`` of the student's solves. Records the serve in history.

When internet tasks are enabled (req. 3), selection can additionally draw from
**live-generated, sandbox-verified** tasks (``app.tasks.generator``). This is
strictly gated and fail-open: if generation is disabled or fails, the curated
path is used exactly as before. Generated ids flow through the SAME uniqueness
machinery (``filter_unique_tasks`` / ``record_serve``) so the cooldown is
preserved.
"""
from __future__ import annotations

import logging
import random

from app.config import settings
from app.db.progress_repo import get_solve_count
from app.db.skill_graph import next_skill
from app.graph.state import TutorState
from app.tasks.repository import tasks_for_skill
from app.tasks.uniqueness import filter_unique_tasks, record_serve

logger = logging.getLogger(__name__)


def _maybe_generate(
    *,
    language: str,
    skill_id: str,
    difficulty: int,
    topic: str | None,
    kind: str | None,
    user_id: str,
    fresh_curated: list,
) -> object | None:
    """Try to mint a generated task when appropriate. Fail-open → ``None``.

    Decision (per plan §6.2): attempt generation when ``INTERNET_TASKS_ENABLED``
    AND a search endpoint is configured, and EITHER a ``topic`` is set (the
    student wants themed practice) OR the curated cooldown left nothing fresh.
    """
    if not settings.INTERNET_TASKS_ENABLED or not settings.search_enabled:
        return None

    has_topic = bool((topic or "").strip())
    curated_exhausted = not fresh_curated
    if not (has_topic or curated_exhausted):
        return None

    try:
        from app.tasks.generator import generate_task

        concept = ""
        # Derive concept from a curated sibling when available; else fall back to
        # the skill_id tail (e.g. "py_loops" -> "loops").
        if fresh_curated:
            concept = getattr(fresh_curated[0], "concept", "") or ""
        if not concept:
            concept = skill_id.split("_", 1)[-1] if "_" in skill_id else skill_id

        return generate_task(
            language=language,
            skill_id=skill_id,
            concept=concept,
            difficulty=difficulty,
            topic=(topic or None),
            kind=kind or "practice",
            created_by=user_id or None,
        )
    except Exception as exc:  # noqa: BLE001 — generation never blocks selection
        logger.warning("Generated-task path failed (%s); using curated", exc)
        return None


def task_selector(state: TutorState) -> dict:
    skill_id = state.get("current_skill", "")
    user_id = state.get("user_id", "")
    difficulty = state.get("difficulty_level", 2)
    skill_state = state.get("skill_state", "practicing")
    topic = state.get("topic", "")
    language = state.get("language", "python")
    current_task_id = state.get("current_task_id")
    # Run & Check de-duplication (req. 1, Group C): on the SUCCESS path the
    # adaptivity engine has already produced a success confirmation in
    # ``agent_response``; we must NOT clobber it with a bare task restatement of
    # the just-solved exercise. We preserve that confirmation and present the
    # freshly-selected task (a DIFFERENT id — the solved id is excluded from the
    # pool below) as the next exercise instead of echoing the solved one. The
    # explicit "next task" offer wording is Group D.
    last_passed = state.get("last_passed")
    success_prefix = state.get("agent_response", "") if last_passed else ""
    # Group D: the adaptivity engine flags a success that should EXPLICITLY offer
    # the next task. When set, we render a clear "Next task" heading before the
    # freshly-selected (different) exercise so the progression reads as a
    # deliberate offer — distinct from the remediation "similar task" nudge.
    offer_next_task = bool(state.get("offer_next_task"))

    # Choose task kind based on adaptive state.
    if skill_state == "advanced":
        kind = "real_case"
    elif skill_state == "remediation":
        kind = "similar"
    else:
        kind = None  # any practice/similar

    # Allow tasks up to the current adaptive difficulty (with a little headroom),
    # capped at the maximum band of 5. Using max(difficulty, 5) previously made
    # the ceiling always 5, defeating the adaptive ramp.
    max_diff = min(difficulty + 1, 5)
    candidates = tasks_for_skill(skill_id, kind=kind, max_difficulty=max_diff)
    if not candidates:
        candidates = tasks_for_skill(skill_id)

    # Robustness: if the current skill has no candidates, walk forward along the
    # skill-graph trajectory to the next skill that DOES have tasks, so we serve
    # something useful instead of dead-ending. Bounded to avoid infinite loops.
    if not candidates:
        probe = next_skill(skill_id)
        seen = {skill_id}
        while probe is not None and probe.id not in seen:
            seen.add(probe.id)
            adjacent = tasks_for_skill(probe.id)
            if adjacent:
                logger.info(
                    "Skill=%s had no tasks; using adjacent skill=%s", skill_id, probe.id
                )
                skill_id = probe.id
                candidates = adjacent
                break
            probe = next_skill(probe.id)

    solve_count = get_solve_count(user_id) if user_id else 0

    # Exclude the just-solved task id where possible so we never restate it.
    pool = [t for t in candidates if t.id != current_task_id] or candidates

    allowed = filter_unique_tasks(user_id, pool, solve_count) if pool else []

    # ------------------------------------------------------------------
    # Internet-sourced tasks (req. 3) — strictly gated + fail-open. We try to
    # mint a generated task when a topic is set OR curated content is exhausted
    # by the cooldown. A successful generated task flows through the SAME serve
    # history / cooldown as curated ones.
    # ------------------------------------------------------------------
    fresh_curated = [t for t in allowed if t.id != current_task_id]
    generated = _maybe_generate(
        language=language,
        skill_id=skill_id,
        difficulty=difficulty,
        topic=topic,
        kind=kind,
        user_id=user_id,
        fresh_curated=fresh_curated,
    )

    task = None
    task_source = "curated"
    if generated is not None:
        task = generated
        task_source = "generated"
    else:
        selectable = fresh_curated or allowed or pool or candidates
        if selectable:
            task = random.choice(selectable)

    if task is None:
        # No next task available (e.g. trajectory exhausted). Degrade gracefully
        # and ensure the success path does not claim to offer a next task
        # (Group D): clear ``offer_next_task``. If we arrived here on a SUCCESS,
        # keep the success confirmation and append an encouragement instead of
        # echoing the solved task.
        if success_prefix:
            fallback_msg = (
                f"{success_prefix}\n\n"
                "🎉 Nicely done! I don't have a fresh exercise queued for this "
                "skill right now — try setting a new learning goal or ask me about "
                "a concept to keep going."
            )
        else:
            fallback_msg = (
                "I don't have a ready-made exercise for this exact skill yet. "
                "Try setting a learning goal (e.g. \"I want to learn Python loops\") "
                "or ask me a question about a concept, and I'll pull up practice for "
                "a skill that has tasks available."
            )
        return {
            "current_task_id": None,
            "task_source": "curated",
            "offer_next_task": False,
            "agent_response": fallback_msg,
            "next_action": "respond",
        }

    if user_id:
        record_serve(user_id, task.id, solve_count)

    prompt = (
        f"**Task ({task.language}, difficulty {task.difficulty})**\n\n{task.prompt}\n\n"
        f"Define a function named `{task.entry_point}`. "
        f"Submit your code and I'll run it against the tests."
    )
    # PASS de-duplication (req. 1, Group C): keep the success confirmation that
    # adaptivity produced instead of overwriting it with a bare task restatement.
    # The served task is a NEW exercise (solved id excluded above), so the
    # just-solved task is never echoed back verbatim.
    if success_prefix:
        # Group D: when the success explicitly offers the next task, insert a
        # clear "Next task" heading between the confirmation and the (different)
        # exercise. This makes the progression an explicit offer while still
        # NOT restating the just-solved task (de-dup preserved — solved id was
        # excluded from the pool above).
        if offer_next_task:
            prompt = f"{success_prefix}\n\n➡️ **Next task** — here's your next exercise:\n\n{prompt}"
        else:
            prompt = f"{success_prefix}\n\n{prompt}"
    logger.info(
        "Selected task=%s for skill=%s kind=%s source=%s offer_next=%s",
        task.id,
        skill_id,
        task.kind,
        task_source,
        offer_next_task,
    )
    return {
        "current_task_id": task.id,
        "task_source": task_source,
        "offer_next_task": offer_next_task,
        "agent_response": prompt,
        "next_action": "respond",
    }
