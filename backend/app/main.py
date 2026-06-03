"""FastAPI entry point — wires REST + WebSocket and performs startup seeding."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import auth_router
from app.api.routes import router as rest_router
from app.api.ws import ws_router
from app.config import settings

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)


def _startup_seed() -> None:
    """Initialise DB, seed skills and ingest RAG content (best-effort)."""
    try:
        from app.db.session import init_db

        init_db()
        logger.info("Database initialised")
    except Exception as exc:  # noqa: BLE001
        logger.error("DB init failed: %s", exc)

    # Lightweight schema migration for the new auth columns on existing volumes
    # (ADD COLUMN IF NOT EXISTS). On a fresh volume create_all already added
    # them; this makes upgrades on a pre-existing DB safe too.
    try:
        from sqlalchemy import text

        from app.db.session import engine

        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR")
            )
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR")
            )
            # Free-form THEME ("тематика") column (Group B owns the model; the
            # topic switch API/UI is Group E). create_all does NOT add a column
            # to a pre-existing users table, so mirror settings_store's
            # idempotent ADD COLUMN IF NOT EXISTS for in-place upgrades. On a
            # `docker compose down -v` rebuild create_all already adds it; this
            # makes upgrades on an existing volume safe too.
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS topic VARCHAR")
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email "
                    "ON users (email)"
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Auth column migration failed: %s", exc)

    # Seed the runtime graph-settings row (idempotent) and warm the cache.
    try:
        from app.settings_store import seed_runtime_settings

        seed_runtime_settings()
    except Exception as exc:  # noqa: BLE001
        logger.error("Runtime settings seeding failed: %s", exc)

    # Seed skills BEFORE the default user so profile skill_progress rows have a
    # valid skills FK. Skills are always seeded (independent of SEED_ON_STARTUP)
    # because the default-user profile + adaptive graph depend on them.
    try:
        from app.seed.skills import seed_skills

        seed_skills()
    except Exception as exc:  # noqa: BLE001
        logger.error("Skill seeding failed: %s", exc)

    # Seed the default APPLICATION user (admin@example.com / qwerty123456 by
    # default) with an initialised learning profile. This is both a ready login
    # AND a safeguard guaranteeing a valid users row exists (FK safety).
    try:
        from app.seed.default_user import seed_default_user

        seed_default_user()
    except Exception as exc:  # noqa: BLE001
        logger.error("Default user seeding failed: %s", exc)

    if not settings.SEED_ON_STARTUP:
        return

    try:
        from app.rag.ingestion import ingest_all

        ingest_all()
    except Exception as exc:  # noqa: BLE001
        logger.error("Content ingestion failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup_seed()
    # Warm the graph (creates checkpointer tables).
    try:
        from app.graph.builder import get_graph

        get_graph()
    except Exception as exc:  # noqa: BLE001
        logger.error("Graph init failed: %s", exc)
    yield


app = FastAPI(title="Adaptive AI Coding Tutor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(rest_router)
app.include_router(ws_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {
        "service": "Adaptive AI Coding Tutor",
        "docs": "/docs",
        "rapidapi_enabled": settings.rapidapi_enabled,
    }
