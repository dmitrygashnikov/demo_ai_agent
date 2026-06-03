"""Web Search node — failure-path remediation links + excerpt (req. 1, Group C).

Runs ONLY on the failure path, inserted between ``error_classifier`` and
``remediation_planner`` (edge: ``error_classifier → web_search_node →
remediation_planner``). It:

  1. Builds a search query themed by ``language`` + ``concept`` +
     ``last_error_type`` + (optional) ``topic``.
  2. Calls the fail-open :func:`app.search.web_search` client to fetch
     videos/articles → ``remediation_links`` (top 3–5).
  3. Derives a short plain-language ``remediation_excerpt``: prefer an LLM
     summary of the snippets; if the LLM is unavailable fall back to the top
     snippet(s); if no links at all, fall back to the classifier explanation /
     a static hint.

**Strictly fail-open.** Live remediation is gated behind
``INTERNET_TASKS_ENABLED`` + ``search_enabled`` (consistent with Group B); when
disabled, search down, or the LLM is unavailable, the node degrades to the
existing curated/classifier behaviour and NEVER raises — it always returns
``next_action="remediate"`` so the graph proceeds to ``remediation_planner``.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.db.skill_graph import concept_of
from app.graph.state import TutorState
from app.llm.client import LLMUnavailable, chat
from app.search import web_search

logger = logging.getLogger(__name__)

# How many links to surface to the student.
_MAX_LINKS = 4


def _build_query(language: str, concept: str, error_type: str, topic: str) -> str:
    """Compose a remediation search query themed by the error/skill/topic."""
    parts = [language]
    if concept:
        parts.append(concept)
    if error_type:
        parts.append(error_type.replace("_", " "))
    if topic:
        parts.append(topic)
    parts.append("error explanation tutorial")
    # e.g. "python loops off by one error explanation tutorial"
    return " ".join(p for p in parts if p).strip()


def _summarise(
    *,
    error_type: str,
    links: list[dict],
) -> str:
    """Distil a 2–3 sentence plain-language excerpt from the search snippets.

    Prefers an LLM summary grounded in the snippets; falls back to the top
    snippet text when the LLM is unavailable. Returns ``""`` when there is
    nothing to summarise (caller then falls back to the classifier explanation).
    """
    snippets = [l.get("snippet", "") for l in links if l.get("snippet")]
    if not snippets:
        return ""

    joined = "\n".join(f"- {s}" for s in snippets[:_MAX_LINKS])

    try:
        excerpt = chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a programming tutor. In 2-3 short sentences and "
                        "plain language, explain the '"
                        f"{error_type.replace('_', ' ')}' mistake the student "
                        "likely made and how to fix it. Ground your explanation "
                        "ONLY in the provided search snippets. Do not include "
                        "links or markdown."
                    ),
                },
                {"role": "user", "content": f"Snippets:\n{joined}"},
            ],
            temperature=0.2,
        )
        excerpt = (excerpt or "").strip()
        if excerpt:
            return excerpt
    except LLMUnavailable:
        logger.info("LLM unavailable for remediation excerpt; using snippet fallback")
    except Exception as exc:  # noqa: BLE001 — never break the turn on summarisation
        logger.warning("Remediation excerpt summarisation failed (%s); snippet fallback", exc)

    # Snippet-only fallback: the single most relevant snippet.
    return snippets[0]


def web_search_node(state: TutorState) -> dict:
    """Fetch remediation links + excerpt on the failure path (fail-open)."""
    language = state.get("language", "python")
    skill_id = state.get("current_skill", "")
    concept = concept_of(skill_id) or ""
    error_type = state.get("last_error_type", "logic") or "logic"
    topic = (state.get("topic", "") or "").strip()

    # Gate live web-search remediation consistently with Group B. When disabled
    # we still proceed to remediation_planner, just with no web links/excerpt —
    # the curated video review + classifier explanation cover that path.
    if not (settings.INTERNET_TASKS_ENABLED and settings.search_enabled):
        logger.debug(
            "Web-search remediation disabled (INTERNET_TASKS_ENABLED=%s search_enabled=%s)",
            settings.INTERNET_TASKS_ENABLED,
            settings.search_enabled,
        )
        return {
            "remediation_links": [],
            "remediation_excerpt": "",
            "next_action": "remediate",
        }

    query = _build_query(language, concept, error_type, topic)

    # web_search is itself fail-open (never raises, returns [] when unavailable),
    # but we wrap defensively so this node can never break the failure turn.
    try:
        results = web_search(query, max_results=_MAX_LINKS, language="en")
    except Exception as exc:  # noqa: BLE001 — defensive: never propagate
        logger.warning("web_search raised unexpectedly (%s); proceeding with no links", exc)
        results = []

    links = [r.as_dict() for r in results][:_MAX_LINKS]
    excerpt = _summarise(error_type=error_type, links=links)

    logger.info(
        "Web-search remediation query=%r links=%d excerpt=%s",
        query,
        len(links),
        bool(excerpt),
    )

    return {
        "remediation_links": links,
        "remediation_excerpt": excerpt,
        "next_action": "remediate",
    }
