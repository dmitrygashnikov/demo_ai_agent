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
from app.tasks.repository import normalize_exercise_type, tasks_for_skill
from app.tasks.uniqueness import filter_unique_tasks, record_serve

logger = logging.getLogger(__name__)


def _exercise_type_of(task: object) -> str:
    """Normalised exercise_type of a task (fail-open → implement_return)."""
    return normalize_exercise_type(getattr(task, "exercise_type", None))


def _code_lang(language: str) -> str:
    if language in ("javascript", "js", "node"):
        return "javascript"
    return "python"


def _rotate_for_variety(pool: list, last_type: str | None) -> list:
    """Bias the selectable pool AWAY from the last-served exercise type.

    Problem 4: so consecutive exercises differ in ESSENCE, not just wording. If
    the pool contains tasks of a DIFFERENT type than ``last_type``, return only
    those (a different kind of exercise). If every candidate is the same type as
    last time (no variety available), return the pool unchanged so we never
    dead-end — variety is a preference, not a hard constraint.
    """
    if not pool:
        return pool
    last = normalize_exercise_type(last_type) if last_type else None
    if not last:
        return pool
    differing = [t for t in pool if _exercise_type_of(t) != last]
    return differing or pool


def _render_task_prompt(task: object) -> str:
    """Render the student-facing task prompt, conditional on exercise_type.

    ``implement_return`` (and other code-producing types) keep the classic
    "Define a function named `X`" instruction. ``predict_output`` / ``trace_value``
    must NOT ask the student to submit a function — they ask for a typed answer
    and show the code to read. ``find_the_bug`` / ``refactor`` show the given
    code; ``fill_in_the_blank`` shows the template with ``___`` blanks.
    """
    etype = _exercise_type_of(task)
    language = getattr(task, "language", "")
    difficulty = getattr(task, "difficulty", "")
    body = getattr(task, "prompt", "")
    given_code = getattr(task, "given_code", "") or ""
    template = getattr(task, "template", "") or ""
    entry_point = getattr(task, "entry_point", "") or ""
    fence = _code_lang(language)

    header = f"**Task ({language}, difficulty {difficulty})**\n\n{body}"

    if etype in ("predict_output", "trace_value"):
        parts = [header]
        if given_code:
            parts.append(f"```{fence}\n{given_code}\n```")
        parts.append(
            "Type your answer (the expected value/output) directly — you don't "
            "need to write any code for this one."
        )
        return "\n\n".join(parts)

    if etype == "fill_in_the_blank":
        parts = [header]
        if template:
            parts.append(
                "Complete the blanks (`___`) and submit the full function:\n\n"
                f"```{fence}\n{template}\n```"
            )
        if entry_point:
            parts.append(
                f"Submit your completed `{entry_point}` and I'll run it against "
                "the tests."
            )
        return "\n\n".join(parts)

    if etype in ("find_the_bug", "refactor"):
        parts = [header]
        if given_code:
            label = (
                "Here's the buggy code — fix it and submit the corrected version:"
                if etype == "find_the_bug"
                else "Here's the code to rewrite — keep the same behaviour:"
            )
            parts.append(f"{label}\n\n```{fence}\n{given_code}\n```")
        if entry_point:
            parts.append(
                f"Submit your `{entry_point}` and I'll run it against the tests."
            )
        return "\n\n".join(parts)

    # Default / implement-a-function family (implement_return, conditions_branching,
    # loops_accumulate, io_transform, and any unknown type → implement_return).
    return (
        f"{header}\n\n"
        f"Define a function named `{entry_point}`. "
        f"Submit your code and I'll run it against the tests."
    )


def _maybe_generate(
    *,
    language: str,
    skill_id: str,
    difficulty: int,
    topic: str | None,
    kind: str | None,
    user_id: str,
    fresh_curated: list,
    exercise_type: str | None = None,
) -> object | None:
    """Try to mint a generated task when appropriate. Fail-open → ``None``.

    Decision (per plan §6.2): attempt generation when ``INTERNET_TASKS_ENABLED``
    AND a search endpoint is configured, and EITHER a ``topic`` is set (the
    student wants themed practice) OR the curated cooldown left nothing fresh.

    ``exercise_type`` (Problem 4) is the target exercise type for variety; passed
    through to the generator so a minted task rotates type too. ``None`` lets the
    generator default to ``implement_return``.
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
            exercise_type=exercise_type,
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
    # Section-change turn (req. 6/7): the student clicked a sidebar section. We
    # treat this as a deliberate fresh serve — DISCARD the previously-served
    # task (it is already excluded from the pool below + overwritten by the new
    # id), emit ONLY the theme-set acknowledgement followed by the new themed
    # task, and suppress any success/remediation prefixes (there was no code
    # submission this turn). ``cancelled_task_id`` records what was dropped.
    section_change = bool(state.get("section_change"))
    section_title = state.get("section_title", "") or (state.get("topic", "") or "")
    cancelled_task_id = current_task_id if section_change else None
    last_passed = state.get("last_passed")
    success_prefix = "" if section_change else (
        state.get("agent_response", "") if last_passed else ""
    )
    # Fail-path remediation fix (Problem 3): on a FAILURE we arrived here through
    # remediation_planner, which already built the analysis (simplified trace →
    # Explanation + links → correct example) into ``agent_response``. We must NOT
    # overwrite it with the bare new task. Capture it as a prefix (symmetric to
    # ``success_prefix``) and append the new similar task AFTER it so the single
    # message reads: trace → Explanation+links → 🔁 similar task.
    remediation_prefix = "" if section_change else (
        state.get("agent_response", "") if last_passed is False else ""
    )
    # Group D: the adaptivity engine flags a success that should EXPLICITLY offer
    # the next task. When set, we render a clear "Next task" heading before the
    # freshly-selected (different) exercise so the progression reads as a
    # deliberate offer — distinct from the remediation "similar task" nudge.
    offer_next_task = bool(state.get("offer_next_task"))
    # Problem 4: the exercise_type served last turn (checkpointed). Used to bias
    # selection toward a DIFFERENT type so consecutive exercises vary in essence.
    last_exercise_type = state.get("last_exercise_type")

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
    # Problem 4 — variety: pick a TARGET exercise_type that differs from the one
    # served last turn, drawn from what the curated pool actually offers. Passed
    # to the generator so a freshly-minted task also rotates type; used to bias
    # the curated choice below.
    variety_pool = _rotate_for_variety(fresh_curated, last_exercise_type)
    target_exercise_type = (
        _exercise_type_of(variety_pool[0]) if variety_pool else None
    )
    generated = _maybe_generate(
        language=language,
        skill_id=skill_id,
        difficulty=difficulty,
        topic=topic,
        kind=kind,
        user_id=user_id,
        fresh_curated=fresh_curated,
        exercise_type=target_exercise_type,
    )

    task = None
    task_source = "curated"
    if generated is not None:
        task = generated
        task_source = "generated"
    else:
        # Prefer a type different from last time (variety); fall back through the
        # usual pools so we never dead-end when no variety is available.
        selectable = (
            _rotate_for_variety(fresh_curated, last_exercise_type)
            or fresh_curated
            or allowed
            or pool
            or candidates
        )
        if selectable:
            task = random.choice(selectable)

    # Section-change turn (req. 6/7): the theme-set acknowledgement that precedes
    # the new themed task. Produced server-side here so it is identical across
    # REST/WS (today it was only emitted client-side — the bug behind #7).
    theme_line = (
        f'🎨 Theme set to "{section_title}". New tasks will be themed accordingly.'
        if section_change
        else ""
    )

    if task is None:
        # No next task available (e.g. trajectory exhausted). Degrade gracefully
        # and ensure the success path does not claim to offer a next task
        # (Group D): clear ``offer_next_task``. If we arrived here on a SUCCESS,
        # keep the success confirmation and append an encouragement instead of
        # echoing the solved task.
        if section_change:
            # Section change with no fresh task queued: still confirm the theme
            # switch (so the chat reflects the selection) even if we cannot mint
            # a task right now.
            fallback_msg = (
                f"{theme_line}\n\n"
                "I don't have a ready-made exercise for this section yet — try "
                "asking me about the topic or set a learning goal and I'll pull "
                "up themed practice."
            ).strip()
        elif remediation_prefix:
            # Preserve the remediation analysis even when no similar task is
            # available (Problem 3): never drop the trace/Explanation/example.
            fallback_msg = (
                f"{remediation_prefix}\n\n"
                "When you're ready, fix your solution and submit again — I don't "
                "have a fresh similar exercise queued right now."
            )
        elif success_prefix:
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
            "cancelled_task_id": cancelled_task_id,
            "agent_response": fallback_msg,
            "next_action": "respond",
        }

    if user_id:
        record_serve(user_id, task.id, solve_count)

    # Problem 4: render conditionally on exercise_type — predict/trace ask for a
    # typed answer (not a function), fill-in-the-blank shows the template, etc.
    prompt = _render_task_prompt(task)
    served_exercise_type = _exercise_type_of(task)
    # Section change (req. 6/7): the single turn reads theme-set line → new
    # themed task. No success/remediation prefixes apply (no code submission).
    if section_change:
        prompt = f"{theme_line}\n\n{prompt}"
    # FAILURE path (Problem 3): append the new similar task AFTER the remediation
    # analysis so the single message reads trace → Explanation+links → similar
    # task. We must NOT overwrite the remediation prefix.
    elif remediation_prefix:
        prompt = f"{remediation_prefix}\n\n🔁 **Try a similar task:**\n\n{prompt}"
    # PASS de-duplication (req. 1, Group C): keep the success confirmation that
    # adaptivity produced instead of overwriting it with a bare task restatement.
    # The served task is a NEW exercise (solved id excluded above), so the
    # just-solved task is never echoed back verbatim.
    elif success_prefix:
        # Group D: when the success explicitly offers the next task, insert a
        # clear "Next task" heading between the confirmation and the (different)
        # exercise. This makes the progression an explicit offer while still
        # NOT restating the just-solved task (de-dup preserved — solved id was
        # excluded from the pool above).
        if offer_next_task:
            prompt = f"{success_prefix}\n\n➡️ **Next task** — here's your next exercise:\n\n{prompt}"
        else:
            prompt = f"{success_prefix}\n\n{prompt}"
    if section_change and cancelled_task_id:
        logger.info(
            "Section change: cancelled previous task=%s; serving new themed task=%s",
            cancelled_task_id,
            task.id,
        )
    logger.info(
        "Selected task=%s for skill=%s kind=%s type=%s (prev_type=%s) source=%s offer_next=%s section_change=%s",
        task.id,
        skill_id,
        task.kind,
        served_exercise_type,
        last_exercise_type,
        task_source,
        offer_next_task,
        section_change,
    )
    return {
        "current_task_id": task.id,
        "task_source": task_source,
        # A section change is purely a theme switch + fresh task; it never
        # carries forward a success "offer next" flag.
        "offer_next_task": False if section_change else offer_next_task,
        # Record the served type so the NEXT turn rotates away from it (Problem 4).
        "last_exercise_type": served_exercise_type,
        # The id of the previously-served task that was cancelled by this section
        # change (None on ordinary turns). Surfaced via the runner payload.
        "cancelled_task_id": cancelled_task_id,
        "agent_response": prompt,
        "next_action": "respond",
    }
