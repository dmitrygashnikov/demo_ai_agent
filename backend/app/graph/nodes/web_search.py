"""Web Search node — failure-path remediation links + code-grounded explanation.

Runs ONLY on the failure path, inserted between ``error_classifier`` and
``remediation_planner`` (edge: ``error_classifier → web_search_node →
remediation_planner``). It:

  1. Builds a search query themed by ``language`` + ``concept`` +
     ``last_error_type`` + the **concrete error symbol** (e.g. ``TypeError``) +
     (optional) ``topic`` — so links explain the actual type/class/object where
     the mistake happened (Problem 1).
  2. Calls the fail-open :func:`app.search.web_search` client to fetch
     videos/articles → ``remediation_links`` (top 3–5).
  3. Produces a **code-grounded** ``remediation_excerpt``: the explanation now
     analyzes the student's actual submitted code + the real sandbox error +
     the failing cases (Problems 1 & 2), with web snippets as supporting
     context only. When the LLM is unavailable it degrades to a deterministic
     explanation built from the real error itself — never a generic template.

**Strictly fail-open.** Live remediation is gated behind
``INTERNET_TASKS_ENABLED`` + ``search_enabled``; when disabled, search down, or
the LLM is unavailable, the node degrades gracefully and NEVER raises — it
always returns ``next_action="remediate"`` so the graph proceeds to
``remediation_planner``. Even with web-search disabled it still produces a
code-grounded explanation (the explanation no longer depends on web snippets).
"""
from __future__ import annotations

import logging

from app.config import settings
from app.db.skill_graph import concept_of
from app.graph.state import TutorState
from app.llm.client import LLMUnavailable, chat
from app.rag import link_store
from app.search import web_search

logger = logging.getLogger(__name__)

# Minimum links to surface to the student (req. 3 / spec §4.6: ">=4 verified
# links per error explanation"). We fetch a few extra (``_FETCH_RESULTS``) so the
# floor survives dead-link pruning during serve-time verification.
_MIN_LINKS = 4
_FETCH_RESULTS = 6
# Backward-compatible alias (older references / tests).
_MAX_LINKS = _MIN_LINKS


def _build_query(
    language: str,
    concept: str,
    error_type: str,
    topic: str,
    symbol: str | None = None,
) -> str:
    """Compose a remediation search query themed by the error/skill/topic.

    Includes the concrete exception ``symbol`` (e.g. ``TypeError``) when known
    so the returned links explain the real type/class/object involved.
    """
    parts = [language]
    if concept:
        parts.append(concept)
    if symbol:
        parts.append(symbol)
    if error_type:
        parts.append(error_type.replace("_", " "))
    if topic:
        parts.append(topic)
    parts.append("error explanation tutorial")
    # e.g. "python loops TypeError off by one error explanation tutorial"
    return " ".join(p for p in parts if p).strip()


def _deterministic_explanation(
    *, student_error: dict, error_type: str, input_diagnosis: dict | None
) -> str:
    """Build an explanation grounded in the student's input WITHOUT the LLM.

    Used as the fail-open fallback: still references the real error / first
    failing case (or the non-code diagnosis), never a generic template.
    """
    if input_diagnosis and input_diagnosis.get("message"):
        return input_diagnosis["message"]

    summary = (student_error or {}).get("summary", "").strip()
    if summary:
        return summary

    return (
        f"Your solution didn't pass the tests ({error_type.replace('_', ' ')}). "
        "Re-check the logic against the task requirements."
    )


def _grounded_explanation(
    *,
    submitted_code: str,
    student_error: dict,
    error_type: str,
    task_prompt: str,
    entry_point: str,
    input_diagnosis: dict | None,
    snippets: list[str],
) -> str:
    """Generate a code-grounded explanation of the student's actual mistake.

    Analyzes the submitted code + the real error + failing cases (Problems 1 &
    2). Web snippets are supporting context only. Falls back deterministically
    when the LLM is unavailable.
    """
    # Non-code / empty / syntax issues already have a precise, code-grounded
    # message from the input guard — prefer it directly (no LLM needed).
    if input_diagnosis and input_diagnosis.get("kind") in ("empty", "not_code", "syntax"):
        return input_diagnosis.get("message") or _deterministic_explanation(
            student_error=student_error, error_type=error_type, input_diagnosis=input_diagnosis
        )

    real_error = (student_error or {}).get("summary", "").strip() or "(no diagnostic captured)"
    snippet_block = ""
    if snippets:
        snippet_block = "\n\nSupporting reference snippets (for context only):\n" + "\n".join(
            f"- {s}" for s in snippets[:_MAX_LINKS]
        )

    try:
        excerpt = chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a programming tutor. Analyze THIS student's "
                        "submitted code and the REAL error/diagnostics from "
                        "running it. In 2-4 short sentences and plain language, "
                        "explain precisely what is wrong in their code and how to "
                        "fix it. Refer to the actual values/inputs from the "
                        "failing cases when helpful. Do NOT speculate about "
                        "mistakes that aren't supported by the code or the error. "
                        "Do not include links or markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Task: {task_prompt}\n"
                        f"Expected function: `{entry_point}`\n\n"
                        f"Submitted code:\n```\n{submitted_code}\n```\n\n"
                        f"Real error / failing cases:\n{real_error}"
                        f"{snippet_block}"
                    ),
                },
            ],
            temperature=0.2,
        )
        excerpt = (excerpt or "").strip()
        if excerpt:
            return excerpt
    except LLMUnavailable:
        logger.info("LLM unavailable for code-grounded explanation; deterministic fallback")
    except Exception as exc:  # noqa: BLE001 — never break the turn on summarisation
        logger.warning("Code-grounded explanation failed (%s); deterministic fallback", exc)

    return _deterministic_explanation(
        student_error=student_error, error_type=error_type, input_diagnosis=input_diagnosis
    )


def web_search_node(state: TutorState) -> dict:
    """Fetch remediation links + code-grounded explanation (fail-open)."""
    language = state.get("language", "python")
    skill_id = state.get("current_skill", "")
    concept = concept_of(skill_id) or ""
    error_type = state.get("last_error_type", "logic") or "logic"
    topic = (state.get("topic", "") or "").strip()
    submitted_code = state.get("submitted_code", "") or ""
    student_error = state.get("student_error") or {}
    input_diagnosis = state.get("input_diagnosis")
    symbol = state.get("error_symbol") or student_error.get("symbol")

    # The task prompt + entry point help the explanation be concrete.
    task_prompt = ""
    entry_point = ""
    try:
        from app.tasks.repository import get_task

        task = get_task(state.get("current_task_id")) if state.get("current_task_id") else None
        if task is not None:
            task_prompt = task.prompt
            entry_point = task.entry_point
    except Exception:  # noqa: BLE001 — task lookup is best-effort
        pass

    links: list[dict] = []
    query = _build_query(language, concept, error_type, topic, symbol)

    # Gate live web-search remediation consistently with Group B. When disabled
    # we still produce a code-grounded explanation (it no longer depends on web
    # snippets) — only the external links are skipped.
    if settings.INTERNET_TASKS_ENABLED and settings.search_enabled:
        # web_search is itself fail-open; wrap defensively all the same.
        try:
            results = web_search(query, max_results=_FETCH_RESULTS, language="en")
        except Exception as exc:  # noqa: BLE001 — defensive: never propagate
            logger.warning("web_search raised unexpectedly (%s); proceeding with no links", exc)
            results = []
        live_links = [r.as_dict() for r in results]
        # Persist freshly-fetched links into the relational store (req. 3a /
        # spec §4.2) so they are reusable across students. Tagged with the
        # error_type/language/concept; upsert on (url, error_type, language).
        # Strictly fail-open — never break the turn on a store write.
        if live_links:
            try:
                link_store.save_links(
                    {
                        "url": l.get("url", ""),
                        "title": l.get("title", ""),
                        "snippet": l.get("snippet", ""),
                        "language": language,
                        "error_type": error_type,
                        "concept": concept,
                        "kind": "remediation",
                    }
                    for l in live_links
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("save_links (remediation) failed: %s", exc)
    else:
        logger.debug(
            "Web-search links disabled (INTERNET_TASKS_ENABLED=%s search_enabled=%s)",
            settings.INTERNET_TASKS_ENABLED,
            settings.search_enabled,
        )

    # Serve-time reuse + guarantee of >=4 VERIFIED links (spec §4.3/§4.6). This
    # reads the persisted store (incl. the seeded offline floor + the links we
    # just saved), verifies availability concurrently (≤4s/link), prunes/replaces
    # dead ones via the injected search seam, and returns up to ``min_links``.
    # Fully fail-open: on any error it yields whatever it has (possibly empty).
    try:
        links = link_store.get_verified_links(
            error_type=error_type,
            language=language,
            concept=concept,
            kind="remediation",
            min_links=_MIN_LINKS,
            query=query,
        )
    except Exception as exc:  # noqa: BLE001 — never break the turn on link assembly
        logger.debug("get_verified_links (remediation) failed: %s", exc)
        links = []

    snippets = [l.get("snippet", "") for l in links if l.get("snippet")]

    # If the classifier already produced an explanation (LLM/syntax guard), keep
    # it; otherwise generate a code-grounded one here.
    excerpt = (state.get("error_explanation", "") or "").strip()
    if not excerpt:
        excerpt = _grounded_explanation(
            submitted_code=submitted_code,
            student_error=student_error,
            error_type=error_type,
            task_prompt=task_prompt,
            entry_point=entry_point,
            input_diagnosis=input_diagnosis,
            snippets=snippets,
        )

    logger.info(
        "Web-search remediation links=%d excerpt=%s symbol=%s",
        len(links),
        bool(excerpt),
        symbol,
    )

    return {
        "remediation_links": links,
        "remediation_excerpt": excerpt,
        "error_explanation": excerpt,
        "next_action": "remediate",
    }
