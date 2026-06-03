"""Remediation Planner node — video review → similar tasks.

On a failed attempt, retrieves a targeted video review for the error type, then
sets the skill into remediation so the Task Selector serves similar practice
tasks. Updates failure streak and progress state.
"""
from __future__ import annotations

import logging

from app.db.progress_repo import get_or_create_progress, update_progress
from app.db.skill_graph import concept_of
from app.graph.state import TutorState
from app.rag.retriever import retrieve_video_for_error

logger = logging.getLogger(__name__)


def remediation_planner(state: TutorState) -> dict:
    language = state.get("language", "python")
    skill_id = state.get("current_skill", "")
    concept = concept_of(skill_id) or ""
    error_type = state.get("last_error_type", "logic")
    user_id = state.get("user_id", "")
    exec_result = state.get("execution_result", {}) or {}

    # Web-search remediation produced upstream by ``web_search_node`` (req. 1,
    # Group C). Both are fail-open: empty list / empty string when search or the
    # LLM were unavailable, in which case we degrade to the curated video review.
    remediation_links = state.get("remediation_links", []) or []
    remediation_excerpt = (state.get("remediation_excerpt", "") or "").strip()

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

    # Build the failure response (plan §4.3). It must (a) clearly state the code
    # does NOT solve the task, (b) include web links (videos/articles), and (c)
    # include a short plain-language excerpt — WITHOUT restating the original
    # task verbatim (it is already on screen). The structured ``remediation_links``
    # / ``remediation_excerpt`` are also returned so the API/WS payload carries
    # them for the frontend (Group E); the text below is a sensible fallback.
    parts = [
        f"❌ Your code does not solve the task — passed "
        f"{exec_result.get('passed_tests', 0)}/{exec_result.get('total_tests', 0)} tests.",
        f"Diagnosed issue: **{error_type.replace('_', ' ')}**.",
    ]
    if exec_result.get("timed_out"):
        parts.append("Your code timed out — likely an infinite loop. Check your loop's exit condition.")

    # (c) Excerpt block — concise explanation. Prefer the web-derived excerpt;
    # fall back to the classifier-style nudge when search/LLM were unavailable.
    if remediation_excerpt:
        parts.append(f"\n**Explanation:** {remediation_excerpt}")

    # (b) Links block — web results first, then the curated video as a backstop.
    link_lines: list[str] = []
    for link in remediation_links[:4]:
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
        parts.append("\n**📺 Watch / 📖 Read:**\n" + "\n".join(link_lines))

    parts.append("\nWhen you're ready, try again or ask me for a similar task.")

    response = "\n".join(parts)
    logger.info(
        "Remediation for skill=%s error=%s (failures=%d) links=%d excerpt=%s",
        skill_id,
        error_type,
        failures,
        len(remediation_links),
        bool(remediation_excerpt),
    )

    return {
        "skill_state": "remediation",
        "consecutive_failures": failures,
        "consecutive_successes": 0,
        "agent_response": response,
        "retrieved_context": videos,
        # Pass the structured remediation data through so the runner payload can
        # surface it for the frontend (Group E). These were set by web_search_node;
        # re-returning keeps them on the state after this node's partial update.
        "remediation_links": remediation_links,
        "remediation_excerpt": remediation_excerpt,
        "next_action": "select_task",
    }
