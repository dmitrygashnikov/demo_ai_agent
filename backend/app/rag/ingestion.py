"""Ingestion pipeline: index curated content into Qdrant with metadata.

Theory, video reviews and task prompts are chunked (kept whole here — small
curated base) and stored with rich metadata for filtered retrieval.
"""
from __future__ import annotations

import logging
import os

from app.rag.vectorstore import get_vectorstore
from app.seed.content.curated import THEORY, VIDEOS
from app.tasks.repository import all_tasks

logger = logging.getLogger(__name__)


def ingest_all(force: bool = False) -> int:
    """Index theory, videos and task prompts. Returns number of docs indexed.

    Idempotency (req. 9 enablement): historically this early-returned whenever
    ``count() > 0``, which blocked newly seeded content from ever being added on
    an existing volume. The skip is now gated behind ``force`` OR the
    ``RAG_REINGEST`` env flag, so re-seeding new docs is possible on demand while
    a normal restart on a populated store stays cheap. Qdrant upsert is itself
    idempotent (stable per-doc ids), so re-ingesting is safe.
    """
    store = get_vectorstore()
    store.ensure_collection()

    reingest = force or os.getenv("RAG_REINGEST", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not reingest and store.count() > 0:
        logger.info("Vector store already populated (%d docs); skipping", store.count())
        return store.count()

    docs: list[dict] = []

    for t in THEORY:
        docs.append(
            {
                "text": f"{t['title']}. {t['text']}",
                "metadata": {
                    "doc_type": "theory",
                    "language": t["language"],
                    "concept": t["concept"],
                    "level": t.get("level", ""),
                    "title": t["title"],
                },
            }
        )

    for v in VIDEOS:
        docs.append(
            {
                "text": f"{v['title']}. {v['text']}",
                "metadata": {
                    "doc_type": "video",
                    "language": v["language"],
                    "concept": v["concept"],
                    "error_type": v.get("error_type", ""),
                    "title": v["title"],
                    "url": v["url"],
                    "timecode": v.get("timecode", ""),
                },
            }
        )

    for task in all_tasks():
        docs.append(
            {
                "text": f"Task: {task.prompt}",
                "metadata": {
                    "doc_type": "task",
                    "language": task.language,
                    "concept": task.concept,
                    "skill_id": task.skill_id,
                    "difficulty": task.difficulty,
                    "kind": task.kind,
                    "task_id": task.id,
                },
            }
        )

    store.upsert(docs)
    logger.info("Ingested %d documents into Qdrant", len(docs))
    return len(docs)
