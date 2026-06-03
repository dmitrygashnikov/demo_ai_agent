"""Retrieval with metadata filtering (language + concept) and reranking.

Implements the architecture's retrieval strategy:
  * filter by language and concept (always scoped to current skill),
  * dense vector search,
  * lightweight keyword-overlap rerank,
  * context-aware queries for remediation (built from error_type → video).
Returns chunks with source metadata for citation.
"""
from __future__ import annotations

import logging
from typing import Any

from app.rag.vectorstore import get_vectorstore

logger = logging.getLogger(__name__)


def _rerank(query: str, hits: list[dict]) -> list[dict]:
    """Simple keyword-overlap rerank on top of dense scores."""
    q_tokens = set(query.lower().split())

    def boost(hit: dict) -> float:
        text = (hit.get("payload", {}).get("text", "") or "").lower()
        overlap = len(q_tokens & set(text.split()))
        return hit.get("score", 0.0) + 0.01 * overlap

    return sorted(hits, key=boost, reverse=True)


def retrieve(
    query: str,
    language: str | None = None,
    concept: str | None = None,
    doc_type: str | None = None,
    top_k: int = 4,
) -> list[dict]:
    filters: dict[str, Any] = {}
    if language:
        filters["language"] = language
    if concept:
        filters["concept"] = concept
    if doc_type:
        filters["doc_type"] = doc_type

    store = get_vectorstore()
    hits = store.search(query, filters=filters, top_k=top_k * 2)
    hits = _rerank(query, hits)[:top_k]
    return [
        {
            "text": h["payload"].get("text", ""),
            "doc_type": h["payload"].get("doc_type", ""),
            "title": h["payload"].get("title", ""),
            "url": h["payload"].get("url", ""),
            "timecode": h["payload"].get("timecode", ""),
            "score": h["score"],
        }
        for h in hits
    ]


def retrieve_video_for_error(
    language: str, concept: str, error_type: str
) -> list[dict]:
    """Context-aware retrieval: video review targeted at the student's error."""
    store = get_vectorstore()
    filters = {"language": language, "concept": concept, "doc_type": "video"}
    query = f"{concept} {error_type} error explanation"
    hits = store.search(query, filters=filters, top_k=3)
    if not hits:
        # Relax error filter — any video for this concept.
        hits = store.search(query, filters={"language": language, "concept": concept, "doc_type": "video"}, top_k=3)
    return [
        {
            "text": h["payload"].get("text", ""),
            "title": h["payload"].get("title", ""),
            "url": h["payload"].get("url", ""),
            "timecode": h["payload"].get("timecode", ""),
            "error_type": h["payload"].get("error_type", ""),
            "score": h["score"],
        }
        for h in hits
    ]
