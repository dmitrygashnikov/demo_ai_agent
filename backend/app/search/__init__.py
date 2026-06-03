"""Web-search client package — fail-open orchestrator.

A thin abstraction so the graph/generator never talk to MCP or SearXNG
directly. The orchestrator tries, in order:

  1. the SearXNG **MCP** server (primary; what the architecture advertises),
  2. the **direct SearXNG JSON HTTP** fallback (when MCP is unreachable),
  3. an **empty result list** (logged) — never raises to callers.

This mirrors the project's existing fail-open patterns (executor/Langfuse/Redis
degradation): search is optional and must never crash a graph turn.

Public API:
    ``SearchResult``                       — ``{title, url, snippet}`` dataclass.
    ``web_search(query, *, max_results, language) -> list[SearchResult]``
    ``search_health() -> {"mcp": bool, "searxng": bool}``  (best-effort diag).
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from app.config import settings
from app.search.mcp_client import McpSearchError, search_mcp
from app.search.searxng_client import SearxngError, search_direct

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def as_dict(self) -> dict:
        return asdict(self)


def _to_results(raw: list[dict]) -> list[SearchResult]:
    out: list[SearchResult] = []
    for item in raw:
        out.append(
            SearchResult(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                snippet=str(item.get("snippet") or ""),
            )
        )
    return out


def web_search(
    query: str,
    *,
    max_results: int = 5,
    language: str = "en",
) -> list[SearchResult]:
    """Fail-open web search: MCP → direct SearXNG → empty list.

    Never raises. Returns up to ``max_results`` :class:`SearchResult` items, or
    an empty list if both paths are unavailable (logged at WARNING).
    """
    query = (query or "").strip()
    if not query:
        return []
    if not settings.search_enabled:
        logger.debug("Search disabled (no SearXNG/MCP endpoint configured)")
        return []

    # 1) Primary path — MCP.
    try:
        results = search_mcp(query, max_results=max_results, language=language)
        if results:
            return _to_results(results)
        logger.debug("MCP search returned no results for %r; trying direct", query)
    except McpSearchError as exc:
        logger.info("MCP search unavailable (%s); falling back to direct SearXNG", exc)
    except Exception as exc:  # noqa: BLE001 — defensive: never propagate
        logger.warning("Unexpected MCP search error (%s); falling back", exc)

    # 2) Fallback path — direct SearXNG JSON HTTP.
    try:
        results = search_direct(query, max_results=max_results, language=language)
        return _to_results(results)
    except SearxngError as exc:
        logger.info("Direct SearXNG unavailable (%s); returning empty results", exc)
    except Exception as exc:  # noqa: BLE001 — defensive: never propagate
        logger.warning("Unexpected SearXNG error (%s); returning empty results", exc)

    # 3) Final fail-open — empty list.
    return []


def search_health() -> dict:
    """Best-effort diagnostic of the two search paths.

    Performs a tiny probe query against MCP and direct SearXNG. Each probe is
    independently fail-open; a ``False`` only means *that* path did not return
    usable results just now. Intended for ``GET /api/search/health``.
    """
    mcp_ok = False
    searxng_ok = False

    try:
        search_mcp("ping", max_results=1, language="en")
        mcp_ok = True
    except Exception:  # noqa: BLE001
        mcp_ok = False

    try:
        search_direct("ping", max_results=1, language="en")
        searxng_ok = True
    except Exception:  # noqa: BLE001
        searxng_ok = False

    return {"mcp": mcp_ok, "searxng": searxng_ok}


__all__ = ["SearchResult", "web_search", "search_health"]
