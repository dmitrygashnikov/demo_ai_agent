"""FastAPI entry point — wires REST + WebSocket and performs startup seeding."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    # Seed the runtime graph-settings row (idempotent) and warm the cache.
    try:
        from app.settings_store import seed_runtime_settings

        seed_runtime_settings()
    except Exception as exc:  # noqa: BLE001
        logger.error("Runtime settings seeding failed: %s", exc)

    if not settings.SEED_ON_STARTUP:
        return

    try:
        from app.seed.skills import seed_skills

        seed_skills()
    except Exception as exc:  # noqa: BLE001
        logger.error("Skill seeding failed: %s", exc)

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
