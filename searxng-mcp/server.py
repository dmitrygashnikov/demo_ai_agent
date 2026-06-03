"""In-repo SearXNG MCP server for the Adaptive AI Coding Tutor.

Exposes a single ``web_search`` tool over the Model Context Protocol using the
**Streamable HTTP** transport, so the backend (a separate container) can reach
it over the compose network at ``http://searxng-mcp:8077/mcp``.

The tool wraps a SearXNG instance: it issues ``GET ${SEARXNG_URL}/search?...&
format=json`` and normalises the response into ``[{title, url, snippet}]``.

Design notes / consistency with the rest of the stack:
  * No external API keys — purely talks to the internal SearXNG service.
  * Fail-soft: search/HTTP errors return an empty result list rather than
    raising, mirroring the project's fail-open philosophy (the backend has its
    own direct-SearXNG fallback when this server is unreachable).
  * A plain ``/health`` HTTP endpoint is mounted for the compose healthcheck.

Env:
  SEARXNG_URL    base URL of the SearXNG service   (default http://searxng:8080)
  MCP_HTTP_PORT  port to bind the HTTP server on    (default 8077)
"""
# NOTE: do NOT enable `from __future__ import annotations` here. PEP 563 turns
# all annotations into strings, which breaks FastMCP.tool() introspection in
# mcp==1.12.4 (it runs `issubclass(param.annotation, Context)` expecting a real
# class, raising `TypeError: issubclass() arg 1 must be a class`). The native
# 3.12 `str`/`int`/`list[dict]` annotations below work without the future import.

import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("searxng-mcp")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://searxng:8080").rstrip("/")
MCP_HTTP_PORT = int(os.environ.get("MCP_HTTP_PORT", "8077"))

# Bind on all interfaces inside the container; expose Streamable HTTP at /mcp.
mcp = FastMCP("searxng-mcp", host="0.0.0.0", port=MCP_HTTP_PORT)


@mcp.tool()
async def web_search(
    query: str,
    max_results: int = 5,
    language: str = "en",
) -> list[dict]:
    """Search the web via SearXNG and return normalised results.

    Args:
        query: free-text search query.
        max_results: maximum number of results to return (top N).
        language: ISO language code biasing the search (e.g. "en").

    Returns:
        A list of ``{"title": str, "url": str, "snippet": str}`` dicts. Returns
        an empty list on any error (fail-soft).
    """
    params = {"q": query, "format": "json", "language": language}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{SEARXNG_URL}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 — fail-soft, never raise to caller
        logger.warning("web_search failed for query %r: %s", query, exc)
        return []

    results: list[dict] = []
    for item in (data.get("results") or [])[: max(0, max_results)]:
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": item.get("content") or "",
            }
        )
    return results


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    """Liveness probe used by the docker-compose healthcheck."""
    return JSONResponse({"status": "ok", "searxng_url": SEARXNG_URL})


if __name__ == "__main__":
    logger.info(
        "Starting SearXNG MCP server on :%s (SEARXNG_URL=%s)",
        MCP_HTTP_PORT,
        SEARXNG_URL,
    )
    # Streamable HTTP transport — MCP endpoint served at /mcp.
    mcp.run(transport="streamable-http")
