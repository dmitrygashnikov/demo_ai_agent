"""Optional Langfuse tracing integration for the LangGraph run.

Tracing is **fully optional** and best-effort: if Langfuse is not configured
(no keys) or the package/handler cannot be created for any reason, this module
returns ``None`` and the caller simply runs the graph without callbacks. A
failure here must NEVER break the main tutoring flow (edge case: external
observability is unavailable).
"""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Cache the handler so we don't recreate it on every turn.
_handler = None
_initialised = False


def get_langfuse_handler():
    """Return a Langfuse ``CallbackHandler`` or ``None``.

    Returns ``None`` when tracing is disabled (keys not set) or when the
    handler cannot be constructed (package missing, network/import error, …).
    Wrapped in try/except so observability problems never propagate.
    """
    global _handler, _initialised

    if not settings.langfuse_enabled:
        return None

    if _initialised:
        return _handler

    _initialised = True
    try:
        from langfuse.callback import CallbackHandler

        _handler = CallbackHandler(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        logger.info("Langfuse tracing enabled (host=%s)", settings.LANGFUSE_HOST)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse tracing unavailable (%s); continuing without it", exc)
        _handler = None

    return _handler
