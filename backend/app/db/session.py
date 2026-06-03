"""SQLAlchemy engine / session management."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


@contextmanager
def get_session() -> Iterator[Session]:
    """Context-manager session with commit/rollback handling."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables (idempotent)."""
    from app.db import models  # noqa: F401  ensure models are imported

    models.Base.metadata.create_all(bind=engine)
