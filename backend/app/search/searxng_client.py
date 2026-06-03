"""Direct SearXNG JSON HTTP client — the fail-open fallback path.

Used when the SearXNG **MCP** server is unreachable. Issues
``GET ${SEARXNG_URL}/search?format=json`` and normalises the response into the
shared ``{title, url, snippet}`` result shape.

Consistent with the project's fail-open philosophy: any error returns an empty
result list rather than raising (the orchestrator in ``__init__`` then degrades
to ``[]``). A short timeout + a couple of retries cover transient blips without
ever blocking a graph turn.
"""
from __future__ import annotations

import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

# Short timeout so search never stalls a turn (fail-open contract).
_TIMEOUT = 8.0


class SearxngError(Exception):
    """Raised internally when the direct SearXNG call cannot be completed."""


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.3, min=0.3, max=2),
    reraise=True,
)
def _fetch(query: str, language: str) -> dict:
    base = (settings.SEARXNG_URL or "").rstrip("/")
    params = {"q": query, "format": "json", "language": language}
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(f"{base}/search", params=params)
        resp.raise_for_status()
        return resp.json()


def search_direct(query: str, max_results: int = 5, language: str = "en") -> list[dict]:
    """Query SearXNG directly over HTTP/JSON.

    Returns a list of ``{"title", "url", "snippet"}`` dicts (top ``max_results``).
    Raises :class:`SearxngError` on failure so the orchestrator can fall through
    to the empty-result path; callers above never see the raw exception.
    """
    if not (settings.SEARXNG_URL or "").strip():
        raise SearxngError("SEARXNG_URL not configured")
    try:
        data = _fetch(query, language)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Direct SearXNG search failed for %r: %s", query, exc)
        raise SearxngError(str(exc)) from exc

    results: list[dict] = []
    for item in (data.get("results") or [])[: max(0, max_results)]:
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": item.get("content") or item.get("snippet") or "",
            }
        )
    return results
