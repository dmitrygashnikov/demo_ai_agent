"""OpenAI-compatible embeddings (req. 4).

Uses the same configurable ``base_url`` provider as the chat client. Includes a
deterministic local fallback so the system still works (with degraded retrieval
quality) when the embeddings endpoint is unavailable — important for demos and
for the offline edge case.
"""
from __future__ import annotations

import hashlib
import logging

from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.llm.client import get_llm_client

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
def _embed_remote(texts: list[str]) -> list[list[float]]:
    client = get_llm_client()
    resp = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def _embed_fallback(text: str) -> list[float]:
    """Deterministic hash-based pseudo-embedding (offline fallback)."""
    dim = settings.EMBEDDING_DIM
    vec = [0.0] * dim
    for token in text.lower().split():
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        idx = h % dim
        vec[idx] += 1.0
    # L2 normalise
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        return _embed_remote(texts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding endpoint failed (%s); using local fallback", exc)
        return [_embed_fallback(t) for t in texts]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
