"""FastAPI entry point — wires REST + WebSocket and performs startup seeding."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import auth_router
from app.api.routes import router as rest_router
from app.api.sections import router as sections_router
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
            # Active sidebar SECTION (req. 6). Mirrors the ``topic`` pattern:
            # create_all only adds the column on a fresh volume, so add it
            # idempotently here for in-place upgrades on existing volumes. The
            # ``sections`` and ``remediation_links`` TABLES are added by
            # create_all on existing volumes (it only skips already-present
            # tables), so no explicit CREATE TABLE is required here.
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                    "current_section_id VARCHAR"
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email "
                    "ON users (email)"
                )
            )
            # Problem 4 (exercise-type taxonomy): the generated_tasks table gains
            # an ``exercise_type`` column plus supporting fields. create_all only
            # adds columns on a fresh volume, so mirror the idempotent ADD COLUMN
            # IF NOT EXISTS pattern for in-place upgrades on existing volumes.
            # Defaults keep pre-existing generated rows valid as implement_return.
            conn.execute(
                text(
                    "ALTER TABLE generated_tasks ADD COLUMN IF NOT EXISTS "
                    "exercise_type VARCHAR NOT NULL DEFAULT 'implement_return'"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE generated_tasks ADD COLUMN IF NOT EXISTS "
                    "given_code TEXT NOT NULL DEFAULT ''"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE generated_tasks ADD COLUMN IF NOT EXISTS "
                    "template TEXT NOT NULL DEFAULT ''"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE generated_tasks ADD COLUMN IF NOT EXISTS "
                    "expected_answer TEXT NOT NULL DEFAULT ''"
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

    # Seed the human-readable sidebar SECTIONS (req. 6) — idempotent get-or-create
    # per (language, key), mirroring seed_skills. Done after skills so a section's
    # ``concept`` can map onto an existing skill concept.
    try:
        from app.seed.sections import seed_sections

        seed_sections()
    except Exception as exc:  # noqa: BLE001
        logger.error("Section seeding failed: %s", exc)

    # Seed the baseline intro + remediation LINKS (req. 3/9) into the
    # remediation_links table — idempotent upsert on (url, error_type, language).
    # Guarantees the >=4-links-per-concept floor offline (the serve-time
    # verify/replace/prune logic reads this table).
    try:
        from app.seed.sections import seed_links

        seed_links()
    except Exception as exc:  # noqa: BLE001
        logger.error("Link seeding failed: %s", exc)

    # Wire the link-store's replacement-search SEAM (spec §4.5 / B3) once at
    # startup. ``get_verified_links`` calls this to fetch fresh links when the
    # verified set falls below the floor (dead-link replacement). We inject an
    # adapter around the real ``app.search.web_search`` that converts its
    # ``SearchResult`` objects into the ``{title,url,snippet}`` dicts the store
    # expects. Strictly fail-open: the adapter swallows errors → empty list, so
    # link replacement never breaks a turn and the seeded floor still applies.
    try:
        from app.rag import link_store
        from app.search import web_search as _web_search

        def _replacement_search_adapter(
            query: str, *, max_results: int = 6, language: str = "en"
        ) -> list[dict]:
            try:
                results = _web_search(
                    query, max_results=max_results, language=language
                )
                return [r.as_dict() for r in results]
            except Exception as exc:  # noqa: BLE001 — seam must never raise.
                logger.debug("replacement_search adapter failed: %s", exc)
                return []

        link_store.set_replacement_search(_replacement_search_adapter)
        logger.info("Link-store replacement search seam wired")
    except Exception as exc:  # noqa: BLE001
        logger.error("Replacement-search seam wiring failed: %s", exc)

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
app.include_router(sections_router)
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
