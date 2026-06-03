"""OpenAI-compatible LLM client (req. 4).

A single client using the official ``openai`` SDK with a configurable
``base_url`` so any OpenAI-compatible provider (OpenAI, OpenRouter, Together,
local vLLM/Ollama, ...) can be plugged in purely through ``.env``.

All calls are wrapped with retry/backoff (edge case: transient external-API
errors) and degrade gracefully so the graph never crashes on an LLM outage.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Iterator

from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """Raised when the LLM provider cannot be reached after retries."""


@lru_cache
def get_llm_client() -> OpenAI:
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)
def _completion(messages: list[dict], model: str | None, **kwargs) -> Any:
    client = get_llm_client()
    return client.chat.completions.create(
        model=model or settings.LLM_MODEL,
        messages=messages,
        **kwargs,
    )


def chat(messages: list[dict], model: str | None = None, **kwargs) -> str:
    """Blocking chat completion returning the assistant text."""
    try:
        resp = _completion(messages, model, **kwargs)
        return resp.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM chat failed: %s", exc)
        raise LLMUnavailable(str(exc)) from exc


def chat_json(messages: list[dict], model: str | None = None, **kwargs) -> dict:
    """Chat completion that requests/parses JSON output.

    Falls back to best-effort extraction if the provider does not honour the
    ``response_format`` parameter.
    """
    try:
        resp = _completion(
            messages,
            model,
            response_format={"type": "json_object"},
            **kwargs,
        )
        content = resp.choices[0].message.content or "{}"
    except Exception:
        # Some providers reject response_format; retry without it.
        try:
            resp = _completion(messages, model, **kwargs)
            content = resp.choices[0].message.content or "{}"
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM chat_json failed: %s", exc)
            raise LLMUnavailable(str(exc)) from exc

    return _safe_json(content)


def stream_chat(messages: list[dict], model: str | None = None, **kwargs) -> Iterator[str]:
    """Yield response tokens as they arrive (used for WebSocket streaming)."""
    try:
        client = get_llm_client()
        stream = client.chat.completions.create(
            model=model or settings.LLM_MODEL,
            messages=messages,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM stream failed: %s", exc)
        raise LLMUnavailable(str(exc)) from exc


def _safe_json(content: str) -> dict:
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to extract the first {...} block.
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {}
