"""Runtime-editable adaptive graph settings (Postgres + Redis cache).

The adaptive knobs (``COOLDOWN_SOLVES``, ``MAX_REGEN_ATTEMPTS``,
``MASTERY_SUCCESS_STREAK``, ``ADVANCED_SUCCESS_STREAK``) and the on-topic
guardrail toggle (``TOPIC_GUARD_ENABLED``) can be changed at runtime via the
API/UI and are applied WITHOUT restarting the backend.

* **Source of truth:** the single ``graph_settings`` row in Postgres.
* **Cache:** Redis key ``graph:settings`` (JSON), so reads are cheap. Writes
  update Postgres first, then refresh/invalidate the cache.

All Redis access is best-effort: if Redis is unavailable, reads fall back to
Postgres and the system keeps working (just without the cache speed-up).
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text

from app.config import settings
from app.db.models import GraphSettings
from app.db.session import engine, get_session

logger = logging.getLogger(__name__)

REDIS_KEY = "graph:settings"
_CACHE_TTL = 300  # seconds

# Integer runtime keys: key -> (ORM column, settings default attr).
_INT_FIELDS = {
    "COOLDOWN_SOLVES": ("cooldown_solves", "COOLDOWN_SOLVES"),
    "MAX_REGEN_ATTEMPTS": ("max_regen_attempts", "MAX_REGEN_ATTEMPTS"),
    "MASTERY_SUCCESS_STREAK": ("mastery_success_streak", "MASTERY_SUCCESS_STREAK"),
    "ADVANCED_SUCCESS_STREAK": ("advanced_success_streak", "ADVANCED_SUCCESS_STREAK"),
}

# Boolean runtime keys: key -> (ORM column, settings default attr).
_BOOL_FIELDS = {
    "TOPIC_GUARD_ENABLED": ("topic_guard_enabled", "TOPIC_GUARD_ENABLED"),
}

# Reasonable validation bounds for each integer parameter (inclusive).
BOUNDS = {
    "COOLDOWN_SOLVES": (1, 100000),
    "MAX_REGEN_ATTEMPTS": (1, 20),
    "MASTERY_SUCCESS_STREAK": (1, 50),
    "ADVANCED_SUCCESS_STREAK": (1, 50),
}

_redis = None


def _get_redis():
    """Lazily create a Redis client (best-effort)."""
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis

        _redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable for settings cache (%s)", exc)
        _redis = None
    return _redis


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "t")
    return bool(value)


def _defaults() -> dict:
    out: dict = {key: int(getattr(settings, attr)) for key, (_, attr) in _INT_FIELDS.items()}
    out.update({key: bool(getattr(settings, attr)) for key, (_, attr) in _BOOL_FIELDS.items()})
    return out


def _row_to_dict(row: GraphSettings) -> dict:
    out: dict = {key: int(getattr(row, col)) for key, (col, _) in _INT_FIELDS.items()}
    out.update({key: bool(getattr(row, col)) for key, (col, _) in _BOOL_FIELDS.items()})
    return out


def _normalise(data: dict) -> dict:
    """Coerce a (possibly JSON-deserialised) settings dict to proper types."""
    out: dict = {}
    for key in _INT_FIELDS:
        if key in data:
            out[key] = int(data[key])
    for key in _BOOL_FIELDS:
        if key in data:
            out[key] = _coerce_bool(data[key])
    return out


def _cache_write(data: dict) -> None:
    client = _get_redis()
    if client is None:
        return
    try:
        client.set(REDIS_KEY, json.dumps(data), ex=_CACHE_TTL)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Settings cache write failed (%s)", exc)


def _cache_read() -> dict | None:
    client = _get_redis()
    if client is None:
        return None
    try:
        raw = client.get(REDIS_KEY)
        if raw:
            return _normalise(json.loads(raw))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Settings cache read failed (%s)", exc)
    return None


def _ensure_schema() -> None:
    """Lightweight migration: add the topic_guard_enabled column if missing.

    ``Base.metadata.create_all`` creates new tables but does NOT alter an
    existing ``graph_settings`` table, so deployments that already have the row
    need this idempotent ``ADD COLUMN IF NOT EXISTS`` to pick up the new flag.
    """
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE graph_settings "
                    "ADD COLUMN IF NOT EXISTS topic_guard_enabled "
                    "BOOLEAN NOT NULL DEFAULT TRUE"
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("graph_settings schema ensure skipped (%s)", exc)


def seed_runtime_settings() -> None:
    """Create the graph_settings row from defaults if it does not exist."""
    _ensure_schema()
    try:
        with get_session() as session:
            row = session.get(GraphSettings, 1)
            if row is None:
                d = _defaults()
                session.add(
                    GraphSettings(
                        id=1,
                        cooldown_solves=d["COOLDOWN_SOLVES"],
                        max_regen_attempts=d["MAX_REGEN_ATTEMPTS"],
                        mastery_success_streak=d["MASTERY_SUCCESS_STREAK"],
                        advanced_success_streak=d["ADVANCED_SUCCESS_STREAK"],
                        topic_guard_enabled=d["TOPIC_GUARD_ENABLED"],
                    )
                )
                logger.info("Seeded graph_settings with defaults: %s", d)
        # Warm the cache.
        _cache_write(get_runtime_settings())
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed seeding runtime settings: %s", exc)


def get_runtime_settings() -> dict:
    """Return current runtime settings, served from Redis cache when possible.

    Falls back to Postgres (source of truth), and finally to in-code defaults if
    everything fails, so callers always get a usable dict.
    """
    cached = _cache_read()
    if cached is not None and len(cached) == len(_INT_FIELDS) + len(_BOOL_FIELDS):
        return cached

    try:
        with get_session() as session:
            row = session.get(GraphSettings, 1)
            if row is not None:
                data = _row_to_dict(row)
                _cache_write(data)
                return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Reading runtime settings from DB failed (%s)", exc)

    return _defaults()


def update_runtime_settings(updates: dict) -> dict:
    """Validate + persist settings to Postgres, then refresh the Redis cache.

    Only known keys are accepted; integer values must be within bounds, boolean
    values are coerced. Returns the full, updated settings dict.
    """
    clean: dict = {}
    for key, value in updates.items():
        if key in _INT_FIELDS:
            try:
                ivalue = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be an integer")
            lo, hi = BOUNDS[key]
            if ivalue < lo or ivalue > hi:
                raise ValueError(f"{key} must be between {lo} and {hi}")
            clean[key] = ivalue
        elif key in _BOOL_FIELDS:
            clean[key] = _coerce_bool(value)
        else:
            raise ValueError(f"Unknown setting: {key}")

    with get_session() as session:
        row = session.get(GraphSettings, 1)
        if row is None:
            d = _defaults()
            d.update(clean)
            row = GraphSettings(
                id=1,
                cooldown_solves=d["COOLDOWN_SOLVES"],
                max_regen_attempts=d["MAX_REGEN_ATTEMPTS"],
                mastery_success_streak=d["MASTERY_SUCCESS_STREAK"],
                advanced_success_streak=d["ADVANCED_SUCCESS_STREAK"],
                topic_guard_enabled=d["TOPIC_GUARD_ENABLED"],
            )
            session.add(row)
        else:
            for key, value in clean.items():
                col = (_INT_FIELDS.get(key) or _BOOL_FIELDS[key])[0]
                setattr(row, col, value)
        session.flush()
        data = _row_to_dict(row)

    # Refresh cache (write-through) so the new values are immediately effective.
    _cache_write(data)
    logger.info("Updated runtime graph settings: %s", clean)
    return data
