"""SQLAlchemy ORM models — profile, progress, attempts, task-serve history.

Implements the data model from the architecture document (section 7) plus the
``task_serve_history`` table required for the task-uniqueness cooldown (req. 5).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
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

    # Stable internal identifier (UUID). All FKs (SkillProgress.user_id, etc.)
    # reference this column — it is NEVER derived from email so renaming/login
    # changes can never break referential integrity.
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # Login identifier. Unique + not null for authenticated users. Older rows
    # created before auth may have NULL email; the unique index allows multiple
    # NULLs in Postgres.
    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    # Bcrypt password hash. Nullable so legacy/seed-only rows remain valid.
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # Optional human-readable display name.
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String, nullable=True)
    # Active free-form THEME ("тематика", e.g. "data analysis with pandas").
    # Orthogonal to language and skill: it only biases generated-task flavour and
    # web-search queries. NULL/empty = neutral (today's behaviour). The DB column
    # is owned by Group B (schema); the topic switch API/UI is Group E.
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    # Active SECTION (sidebar theme, req. 6) selected by the user. Mirrors the
    # single-value ``topic`` pattern: exactly one current section per user.
    # NULL = none selected yet. The DB column is owned by Group B (schema); the
    # section select API/UI is a later group.
    current_section_id: Mapped[str | None] = mapped_column(String, nullable=True)
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
    # On-topic guardrail toggle (runtime-editable). Default True.
    topic_guard_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class GeneratedTask(Base):
    """A live-generated, sandbox-verified coding task (req. 3).

    Mirrors the curated task schema (prompt + visible/hidden tests + reference
    solution) so a generated task is a drop-in for ``tasks.repository.Task``.
    Persisting to Postgres gives durability: a generated task served by one
    worker can still be resolved by ``get_task(task_id)`` on a later Run & Check
    handled by a different worker / after a restart. The in-process cache lives
    in ``app.tasks.dynamic_store``; this table is the source of truth.

    Generated ids use the ``gen_<uuid>`` prefix so they never collide with the
    static curated ids and so provenance is obvious in logs / serve history.
    """

    __tablename__ = "generated_tasks"

    # e.g. "gen_<uuid>". Addressable exactly like a curated task id.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    language: Mapped[str] = mapped_column(String, nullable=False)
    concept: Mapped[str] = mapped_column(String, default="", nullable=False)
    skill_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    kind: Mapped[str] = mapped_column(String, default="practice", nullable=False)
    entry_point: Mapped[str] = mapped_column(String, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    reference_solution: Mapped[str] = mapped_column(Text, nullable=False)
    visible_tests: Mapped[list] = mapped_column(JSON, default=list)
    hidden_tests: Mapped[list] = mapped_column(JSON, default=list)
    # Problem 4: exercise-type taxonomy + supporting fields. Defaults keep older
    # generated rows backward-compatible (treated as ``implement_return`` with no
    # given_code/template/expected_answer). New columns are added in-place via an
    # idempotent ADD COLUMN IF NOT EXISTS migration in ``main.py`` so existing
    # volumes upgrade safely (create_all only adds them on a fresh volume).
    exercise_type: Mapped[str] = mapped_column(
        String, server_default="implement_return", default="implement_return", nullable=False
    )
    given_code: Mapped[str] = mapped_column(Text, server_default="", default="", nullable=False)
    template: Mapped[str] = mapped_column(Text, server_default="", default="", nullable=False)
    expected_answer: Mapped[str] = mapped_column(
        Text, server_default="", default="", nullable=False
    )
    # Free-form theme this task was generated for (may be NULL/empty = neutral).
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    # The user the task was generated for (audit/provenance; not a hard FK so a
    # generated task survives even if the user row is later removed).
    created_by: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Section(Base):
    """A learning section/theme shown in the sidebar (req. 6).

    Seeded sections are human-readable per language; users may also add their own.
    A section optionally maps to a skill concept so selecting it can set the topic
    and (when relevant) steer the skill axis. ``key`` is a stable slug used by the
    API/seed; ``title`` is what the sidebar renders.
    """

    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("language", "key", name="uq_section_lang_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    language: Mapped[str] = mapped_column(String, index=True, nullable=False)  # python | javascript
    key: Mapped[str] = mapped_column(String, nullable=False)                   # slug, e.g. "data_analysis_pandas"
    title: Mapped[str] = mapped_column(String, nullable=False)                 # human-readable, e.g. "Data analysis with pandas"
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Optional concept this section maps to (for skill steering); "" = pure topic theme.
    concept: Mapped[str] = mapped_column(String, default="", nullable=False)
    # Free-form topic string applied when this section is selected (defaults to title).
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    is_user_created: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # NULL for seeded/global sections; set to a user id for user-created sections.
    owner_user_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RemediationLink(Base):
    """Persisted remediation/intro link reusable across students (req. 3).

    Pragmatic counter-based health tracking (NOT full event logging): a rolling
    3-day window + a fail counter drives pruning. Saved by web_search/remediation
    and the "?" intro flow; verified for availability at serve-time.
    """

    __tablename__ = "remediation_links"
    __table_args__ = (
        UniqueConstraint("url", "error_type", "language", name="uq_link_url_err_lang"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    url: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, default="", nullable=False)
    snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String, default="", nullable=False, index=True)
    # Reuse key: the concrete error/topic this link explains. For remediation use
    # an error symbol/type (e.g. "TypeError", "off_by_one"); for intro/"?" use the
    # section concept/key (e.g. "loops", "data_analysis_pandas").
    error_type: Mapped[str] = mapped_column(String, default="", nullable=False, index=True)
    concept: Mapped[str] = mapped_column(String, default="", nullable=False, index=True)
    # "remediation" | "intro" — lets the "?" flow and the failure flow share a table.
    kind: Mapped[str] = mapped_column(
        String, default="remediation", server_default="remediation", nullable=False
    )

    # ---- Pragmatic health counters (the "50 fails in 3 days" rule) ----
    fail_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    fail_window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_ok: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
