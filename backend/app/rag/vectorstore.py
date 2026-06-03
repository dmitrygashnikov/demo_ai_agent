"""Qdrant vector store wrapper with metadata filtering."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import settings
from app.rag.embeddings import embed_text, embed_texts

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self) -> None:
        self.client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        self.collection = settings.QDRANT_COLLECTION

    def ensure_collection(self) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(
                    size=settings.EMBEDDING_DIM, distance=qm.Distance.COSINE
                ),
            )
            logger.info("Created Qdrant collection %s", self.collection)

    def count(self) -> int:
        try:
            return self.client.count(self.collection).count
        except Exception:
            return 0

    def upsert(self, docs: list[dict]) -> None:
        """docs: [{text, metadata}]. Embeds text and stores with payload."""
        if not docs:
            return
        vectors = embed_texts([d["text"] for d in docs])
        points = []
        for doc, vec in zip(docs, vectors):
            payload = dict(doc.get("metadata", {}))
            payload["text"] = doc["text"]
            points.append(
                qm.PointStruct(id=str(uuid.uuid4()), vector=vec, payload=payload)
            )
        self.client.upsert(collection_name=self.collection, points=points)

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        qvec = embed_text(query)
        qfilter = None
        if filters:
            conditions = [
                qm.FieldCondition(key=k, match=qm.MatchValue(value=v))
                for k, v in filters.items()
                if v is not None
            ]
            if conditions:
                qfilter = qm.Filter(must=conditions)
        try:
            hits = self.client.search(
                collection_name=self.collection,
                query_vector=qvec,
                query_filter=qfilter,
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Qdrant search failed: %s", exc)
            return []
        return [
            {"score": h.score, "payload": h.payload or {}} for h in hits
        ]


_store: VectorStore | None = None


def get_vectorstore() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
