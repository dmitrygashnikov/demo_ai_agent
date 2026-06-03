"""SearXNG MCP client — the PRIMARY web-search path.

Connects to the in-repo SearXNG **MCP** server (see ``searxng-mcp/server.py``)
using the official ``mcp`` Python SDK over the **Streamable HTTP** transport at
``${SEARXNG_MCP_URL}/mcp`` and invokes its ``web_search`` tool.

The MCP SDK is async, but the LangGraph nodes that consume search are
synchronous (see ``graph/nodes/task_selector.py``). We therefore expose a small
synchronous ``search_mcp(...)`` wrapper that drives the async client on a
private event loop — matching the surrounding sync node style while keeping the
MCP interaction correct.

Fail-open: any error (MCP server down, transport error, tool error, malformed
payload) raises :class:`McpSearchError`, which the orchestrator in
``__init__`` catches to fall back to the direct SearXNG client.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

# The MCP endpoint is the base SEARXNG_MCP_URL with the Streamable HTTP path.
_MCP_PATH = "/mcp"
# Short overall timeout so a hung MCP server never blocks a graph turn.
_TIMEOUT = 8.0


class McpSearchError(Exception):
    """Raised when the MCP web_search call cannot be completed."""


def _mcp_endpoint() -> str:
    base = (settings.SEARXNG_MCP_URL or "").rstrip("/")
    if not base:
        raise McpSearchError("SEARXNG_MCP_URL not configured")
    return f"{base}{_MCP_PATH}"


def _normalise(raw: Any, max_results: int) -> list[dict]:
    """Coerce the tool's return payload into ``[{title,url,snippet}]``.

    The MCP SDK returns tool output as structured content and/or text content;
    handle both a list-of-dicts and a JSON-encoded string.
    """
    items: list[dict] = []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    if isinstance(raw, dict):
        # Some servers wrap results under a key.
        raw = raw.get("results") or raw.get("result") or []
    if not isinstance(raw, list):
        return []
    for item in raw[: max(0, max_results)]:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": item.get("snippet") or item.get("content") or "",
            }
        )
    return items


async def _call_tool_async(query: str, max_results: int, language: str) -> list[dict]:
    # Imported lazily so the backend still boots if the optional ``mcp`` SDK is
    # not installed (fail-open: orchestrator falls back to the direct client).
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    endpoint = _mcp_endpoint()
    async with streamablehttp_client(endpoint) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "web_search",
                {
                    "query": query,
                    "max_results": max_results,
                    "language": language,
                },
            )

    if getattr(result, "isError", False):
        raise McpSearchError("web_search tool returned an error")

    # Prefer structured content when present; fall back to text content.
    structured = getattr(result, "structuredContent", None)
    if structured:
        return _normalise(structured, max_results)

    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            return _normalise(text, max_results)
    return []


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.3, min=0.3, max=2),
    reraise=True,
)
def search_mcp(query: str, max_results: int = 5, language: str = "en") -> list[dict]:
    """Synchronous wrapper around the async MCP ``web_search`` tool call.

    Returns a list of ``{"title", "url", "snippet"}`` dicts. Raises
    :class:`McpSearchError` on any failure so the orchestrator can fall back.
    """
    try:
        return asyncio.run(
            asyncio.wait_for(
                _call_tool_async(query, max_results, language),
                timeout=_TIMEOUT,
            )
        )
    except McpSearchError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP web_search failed for %r: %s", query, exc)
        raise McpSearchError(str(exc)) from exc
