"""SQLAlchemy ORM models — profile, progress, attempts, task-serve history.

Implements the data model from the architecture document (section 7) plus the
``task_serve_history`` table required for the task-uniqueness cooldown (req. 5).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String, nullable=True)
    # Total number of code solutions the student has submitted. Drives the
    # task-uniqueness cooldown counter.
    solve_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    goals: Mapped[list["Goal"]] = relationship(back_populates="user")
    progress: Mapped[list["SkillProgress"]] = relationship(back_populates="user")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    description: Mapped[str] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    level: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="goals")


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "py_loops"
    name: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String)  # python | javascript
    base_difficulty: Mapped[int] = mapped_column(Integer, default=1)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    # Comma-separated prerequisite skill ids.
    prerequisites: Mapped[str] = mapped_column(String, default="")
    # Logical/concept key shared across languages (e.g. "loops") so mastery can
    # be reused when the student switches language.
    concept: Mapped[str] = mapped_column(String, default="")


class SkillProgress(Base):
    __tablename__ = "skill_progress"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"))
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String, default="introducing")
    consecutive_successes: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped[User] = relationship(back_populates="progress")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[str] = mapped_column(String)
    skill_id: Mapped[str | None] = mapped_column(String, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    submitted_code: Mapped[str] = mapped_column(Text, default="")
    test_results: Mapped[dict] = mapped_column(JSON, default=dict)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    success: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskServeHistory(Base):
    """History of which task was served to which student and at what solve count.

    Powers the uniqueness cooldown (req. 5): a task is not re-served within
    ``COOLDOWN_SOLVES`` of the student's solves.
    """

    __tablename__ = "task_serve_history"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    served_at_solve_count: Mapped[int] = mapped_column(Integer, nullable=False)
    served_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GraphSettings(Base):
    """Single-row table holding the runtime-editable adaptive graph parameters.

    These mirror the four ``settings.*`` adaptive knobs but are editable at
    runtime (via the API/UI) and applied WITHOUT a backend restart. Postgres is
    the source of truth; reads are served from a Redis cache (see
    ``app.settings_store``). The row is seeded from ``settings`` defaults on
    startup if it does not yet exist.
    """

    __tablename__ = "graph_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    cooldown_solves: Mapped[int] = mapped_column(Integer, nullable=False)
    max_regen_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    mastery_success_streak: Mapped[int] = mapped_column(Integer, nullable=False)
    advanced_success_streak: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
