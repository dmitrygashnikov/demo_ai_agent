"""Remediation Planner node — code-grounded failure analysis + video review.

On a failed attempt, builds the student-facing failure analysis in the exact
required sub-order (Problem 3):

  (a) **Simplified trace** — the de-jargoned *real* error (built from the
      extracted student error, not just pass/fail counts).
  (b) **Explanation** block with embedded links — the code-grounded explanation
      of the student's actual mistake (Problems 1 & 2), followed inline by the
      remediation links (videos/articles), plus a clearly-labeled
      **"Example of a correct solution"** drawn from the task's
      ``reference_solution``.

It deliberately does NOT append a "similar task" trailer — the new (similar)
task is appended *after* this block by ``task_selector`` so the single message
reads (a) → (b) → (c) new task.

Everything is fail-open: when the LLM/search were unavailable upstream the
explanation degrades to a deterministic, still code-grounded summary.
"""
from __future__ import annotations

import logging

from app.db.progress_repo import get_or_create_progress, update_progress
from app.db.skill_graph import concept_of
from app.graph.nodes._error_utils import extract_student_error
from app.graph.state import TutorState
from app.rag import link_store
from app.rag.retriever import retrieve_video_for_error
from app.tasks.repository import get_task

logger = logging.getLogger(__name__)

# Limit how much of the reference solution we show (keep it a tidy example).
_MAX_REFERENCE_LINES = 30

# Minimum verified links every error explanation must surface (req. 3 / spec §4.6).
_MIN_LINKS = 4


def _simplified_trace(student_error: dict, exec_result: dict, error_type: str) -> str:
    """Build the (a) simplified-trace block from the real error signal."""
    summary = (student_error or {}).get("summary", "").strip()
    passed = exec_result.get("passed_tests", 0)
    total = exec_result.get("total_tests", 0)

    header = (
        f"❌ Your code does not solve the task — passed {passed}/{total} tests "
        f"(diagnosed issue: **{error_type.replace('_', ' ')}**)."
    )
    if summary:
        return f"{header}\n\n**What went wrong:**\n{summary}"
    return header


def _reference_example(task) -> str:
    """A clearly-labeled correct-solution example from the task, or ``""``."""
    if task is None:
        return ""
    ref = (getattr(task, "reference_solution", "") or "").strip()
    if not ref:
        return ""
    lines = ref.splitlines()
    if len(lines) > _MAX_REFERENCE_LINES:
        lines = lines[:_MAX_REFERENCE_LINES] + ["# ..."]
    fenced = "\n".join(lines)
    lang = getattr(task, "language", "") or ""
    return f"\n**✅ Example of a correct solution:**\n```{lang}\n{fenced}\n```"


def remediation_planner(state: TutorState) -> dict:
    language = state.get("language", "python")
    skill_id = state.get("current_skill", "")
    concept = concept_of(skill_id) or ""
    error_type = state.get("last_error_type", "logic")
    user_id = state.get("user_id", "")
    exec_result = state.get("execution_result", {}) or {}
    task_id = state.get("current_task_id")
    task = get_task(task_id) if task_id else None

    student_error = state.get("student_error") or extract_student_error(exec_result)

    # Code-grounded explanation produced upstream (web_search_node / classifier).
    explanation = (state.get("error_explanation", "") or "").strip()
    if not explanation:
        explanation = (state.get("remediation_excerpt", "") or "").strip()

    # Web-search remediation links produced upstream (fail-open: may be empty).
    # ``web_search_node`` already assembled a >=4-verified set from the link
    # store. As a defensive floor (spec §4.6 — EVERY error explanation has >=4
    # verified links) we top up here via the same getter if the upstream set is
    # short (e.g. web_search was skipped for this path). Strictly fail-open.
    remediation_links = state.get("remediation_links", []) or []
    if len(remediation_links) < _MIN_LINKS:
        try:
            query = " ".join(
                p for p in [language, concept, error_type.replace("_", " "), "error fix tutorial"] if p
            )
            topped_up = link_store.get_verified_links(
                error_type=error_type,
                language=language,
                concept=concept,
                kind="remediation",
                min_links=_MIN_LINKS,
                query=query,
            )
            # Merge, de-duplicating on URL while preserving order (upstream first).
            seen = {l.get("url") for l in remediation_links}
            for l in topped_up:
                if l.get("url") and l["url"] not in seen:
                    seen.add(l["url"])
                    remediation_links.append(l)
        except Exception as exc:  # noqa: BLE001 — never break the turn on link top-up
            logger.debug("remediation link top-up failed: %s", exc)
    remediation_excerpt = explanation

    # Targeted curated video review for this error (existing fallback content).
    videos = retrieve_video_for_error(language, concept, error_type)

    # Update progress: increment failures, reset success streak, enter remediation.
    failures = state.get("consecutive_failures", 0) + 1
    if user_id:
        prog = get_or_create_progress(user_id, skill_id)
        update_progress(
            user_id,
            skill_id,
            state="remediation",
            attempts=prog["attempts"] + 1,
            consecutive_failures=failures,
            consecutive_successes=0,
        )

    # ------------------------------------------------------------------
    # Assemble the message in the required order (Problem 3):
    #   (a) simplified trace → (b) Explanation + embedded links → correct example
    # The (c) "similar task" block is appended by task_selector afterwards.
    # ------------------------------------------------------------------
    parts: list[str] = [_simplified_trace(student_error, exec_result, error_type)]

    # (b) Explanation block with embedded links.
    explanation_block_lines: list[str] = []
    if explanation:
        explanation_block_lines.append(f"**Explanation:** {explanation}")

    link_lines: list[str] = []
    # Show all verified links (>=4 by §4.6), capped to keep the message tidy.
    for link in remediation_links[:6]:
        title = (link.get("title") or link.get("url") or "Resource").strip()
        url = (link.get("url") or "").strip()
        if url:
            link_lines.append(f"- [{title}]({url})")
    if videos:
        v = videos[0]
        url = v.get("url", "")
        tc = f" — {v['timecode']}" if v.get("timecode") else ""
        link_lines.append(f"- 📺 {v['title']}{f' ({url})' if url else ''}{tc}")
    if link_lines:
        explanation_block_lines.append("\n**📺 Watch / 📖 Read:**\n" + "\n".join(link_lines))

    if explanation_block_lines:
        parts.append("\n" + "\n".join(explanation_block_lines))

    # Correct-solution example (Problem 1).
    example = _reference_example(task)
    if example:
        parts.append(example)

    response = "\n".join(parts)
    logger.info(
        "Remediation for skill=%s error=%s (failures=%d) links=%d explanation=%s example=%s",
        skill_id,
        error_type,
        failures,
        len(remediation_links),
        bool(explanation),
        bool(example),
    )

    return {
        "skill_state": "remediation",
        "consecutive_failures": failures,
        "consecutive_successes": 0,
        "agent_response": response,
        "retrieved_context": videos,
        # Pass the structured remediation data through so the runner payload can
        # surface it for the frontend (Group E).
        "remediation_links": remediation_links,
        "remediation_excerpt": remediation_excerpt,
        "next_action": "select_task",
    }
