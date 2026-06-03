"""RAG Retriever node — pulls relevant theory/examples for the query."""
from __future__ import annotations

import logging

from app.db.skill_graph import concept_of
from app.graph.state import TutorState
from app.rag.retriever import retrieve

logger = logging.getLogger(__name__)


def rag_retriever(state: TutorState) -> dict:
    query = state.get("user_message", "")
    language = state.get("language") or None
    concept = concept_of(state.get("current_skill", "")) if state.get("current_skill") else None

    context = retrieve(query, language=language, concept=concept, top_k=4)
    logger.info("Retrieved %d chunks for query", len(context))
    return {"retrieved_context": context, "next_action": "generate"}
