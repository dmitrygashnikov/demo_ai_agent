"""Section (sidebar theme) REST endpoints + reusable service functions (spec §3).

Backs requirements #6 (human-readable sections, user-added, clickable, filter,
pinned current), #7 (section change emits chat msg + NEW themed task + cancels
prior task) and #8 ("?" intro material).

All endpoints are authenticated via the existing ``Depends(get_current_user)``
pattern; ``user_id`` is ALWAYS taken from the token, never the body. The service
functions (:func:`select_section_turn`, :func:`section_intro`) are factored out
so the WebSocket handlers (``app.api.ws``) can delegate to the exact same logic
via ``asyncio.to_thread`` — REST is the source of truth.

Fail-open philosophy mirrors the rest of the app: link assembly degrades to
whatever is available; a missing/invisible section is a clean ``400``/``404``.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.auth.deps import get_current_user
from app.db.models import Section, User
from app.db.progress_repo import set_current_section
from app.db.session import get_session
from app.graph.runner import run_turn
from app.rag import link_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Implemented languages (MVP set). Mirrors GET /api/topics' static philosophy.
_LANGUAGES: list[dict] = [
    {"id": "python", "label": "Python"},
    {"id": "javascript", "label": "JavaScript"},
]
_VALID_LANGUAGES = {lang["id"] for lang in _LANGUAGES}

# Title bounds (reuse the 120-char topic limit from routes.py per spec §3.4).
_MAX_TITLE_LEN = 120
_MAX_DESC_LEN = 1000


# ---------------------------------------------------------------------------
# Pydantic request models (mirroring routes.py style)
# ---------------------------------------------------------------------------
class SectionCreate(BaseModel):
    """Create a user-owned section (spec §3.4)."""

    language: str
    title: str
    description: str | None = None
    concept: str | None = None
    topic: str | None = None


class SectionSelect(BaseModel):
    """Select the user's current section, triggering a themed turn (spec §3.3)."""

    session_id: str
    section_id: str


class SectionIntro(BaseModel):
    """Fetch intro material for a section's concept + language (spec §3.5)."""

    session_id: str | None = None
    language: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _slugify(text: str) -> str:
    """Lowercase, hyphen-joined slug of a title (ASCII-ish, fail-soft)."""
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "section"


def _section_dict(s: Section, current_section_id: str | None = None) -> dict:
    """Serialise a Section row to the API shape (spec §3.1)."""
    return {
        "id": s.id,
        "key": s.key,
        "title": s.title,
        "description": s.description,
        "concept": s.concept,
        "topic": s.topic if s.topic is not None else s.title,
        "is_user_created": s.is_user_created,
        "owner_user_id": s.owner_user_id,
        "order_index": s.order_index,
        "is_current": bool(current_section_id and s.id == current_section_id),
    }


def _load_visible_section(session, section_id: str, user_id: str) -> Section | None:
    """Load a section the user is allowed to see (global OR their own)."""
    s = session.get(Section, section_id)
    if s is None:
        return None
    if s.owner_user_id is None or s.owner_user_id == user_id:
        return s
    return None


# ---------------------------------------------------------------------------
# Reusable service functions (shared by REST + WS)
# ---------------------------------------------------------------------------
def select_section_turn(user_id: str, session_id: str, section_id: str) -> dict:
    """Set the current section + run a fresh themed turn (spec §3.3, req #7).

    Persists ``users.current_section_id`` + ``users.topic`` (from the section),
    then runs ``run_turn(..., section_change=True)`` so the graph cancels the
    previously-served task and produces a NEW themed task while emitting the
    theme-set acknowledgement. Returns the turn result (same shape as /api/chat)
    with ``state.current_section_id`` filled in. Raises ``HTTPException`` on a
    not-found/invisible section; otherwise fail-open like other turns.
    """
    with get_session() as session:
        s = _load_visible_section(session, section_id, user_id)
        if s is None:
            raise HTTPException(status_code=400, detail="Section not found or not visible")
        language = s.language
        resolved_topic = (s.topic or s.title or "").strip()
        section_title = s.title

    # Persist the current section + topic (orthogonal to skill progress).
    set_current_section(user_id, section_id)
    try:
        from app.db.progress_repo import set_user_topic

        set_user_topic(user_id, resolved_topic)
    except Exception as exc:  # noqa: BLE001 — persistence is best-effort
        logger.debug("set_user_topic during select failed: %s", exc)

    result = run_turn(
        user_id,
        session_id,
        user_message="",
        language=language,
        topic=resolved_topic,
        section_change=True,
        section_title=section_title,
    )
    # Surface the new current section id in the turn state (the graph does not
    # own this column; the route persisted it above).
    state = result.get("state")
    if isinstance(state, dict):
        state["current_section_id"] = section_id
    return result


def section_intro(user_id: str, section_id: str, language: str | None = None) -> dict:
    """Assemble intro material for a section (spec §3.5, req #8).

    Returns >=4 verified intro links (articles) + at least one video for the
    section's concept/key and the selected language, shaped as a chat message
    (``response`` + ``links``) so the frontend can render it in the chat. Raises
    ``HTTPException`` if the section is not visible. Fail-open on link assembly.
    """
    with get_session() as session:
        s = _load_visible_section(session, section_id, user_id)
        if s is None:
            raise HTTPException(status_code=404, detail="Section not found or not visible")
        lang = (language or s.language or "python").strip()
        concept = (s.concept or s.key or "").strip()
        title = s.title

    query = " ".join(p for p in [lang, concept or title, "introduction tutorial"] if p)
    links: list[dict] = []
    try:
        links = link_store.get_verified_links(
            error_type="",
            language=lang,
            concept=concept,
            kind="intro",
            min_links=link_store.MIN_LINKS,
            query=query,
        )
    except Exception as exc:  # noqa: BLE001 — fail-open: degrade to whatever we have
        logger.debug("section_intro get_verified_links failed: %s", exc)
        links = []

    # Tag a coarse article/video kind so the frontend can split them; YouTube /
    # known video hosts → "video", else "article".
    shaped: list[dict] = []
    for l in links:
        url = l.get("url", "")
        is_video = any(h in url for h in ("youtube.com", "youtu.be", "vimeo.com"))
        shaped.append(
            {
                "title": l.get("title") or url or "Resource",
                "url": url,
                "snippet": l.get("snippet", ""),
                "kind": "video" if is_video else "article",
            }
        )

    response = f"📚 Intro to **{title}** ({lang}):"
    return {"response": response, "links": shaped, "section_id": section_id}


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@router.get("/languages")
def list_languages():
    """Return the implemented languages with display labels (spec §3.2).

    Public/static (no user data), like ``GET /api/topics`` — always available.
    """
    return {"languages": _LANGUAGES}


@router.get("/sections")
def list_sections(language: str, current_user: dict = Depends(get_current_user)):
    """List sections for a language: global seeded + the user's own (spec §3.1).

    Ordered by ``order_index, title``. Each item carries an ``is_current`` flag.
    """
    language = (language or "").strip()
    if language not in _VALID_LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported or missing language")
    user_id = current_user["id"]
    with get_session() as session:
        user = session.get(User, user_id)
        current_section_id = getattr(user, "current_section_id", None) if user else None
        rows = (
            session.execute(
                select(Section)
                .where(
                    Section.language == language,
                    or_(
                        Section.owner_user_id.is_(None),
                        Section.owner_user_id == user_id,
                    ),
                )
                .order_by(Section.order_index.asc(), Section.title.asc())
            )
            .scalars()
            .all()
        )
        sections = [_section_dict(s, current_section_id) for s in rows]
    return {
        "language": language,
        "current_section_id": current_section_id,
        "sections": sections,
    }


@router.post("/sections")
def create_section(req: SectionCreate, current_user: dict = Depends(get_current_user)):
    """Create a user-owned section (spec §3.4).

    ``is_user_created=True``, ``owner_user_id`` = current user. The key is
    derived as ``u_<short_uid>_<slug>`` so user slugs never clash with global
    ones (and the ``(language, key)`` unique constraint holds). ``409`` on
    duplicate, ``400`` on empty/oversized title.
    """
    user_id = current_user["id"]
    language = (req.language or "").strip()
    if language not in _VALID_LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported language")
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    if len(title) > _MAX_TITLE_LEN:
        raise HTTPException(
            status_code=400, detail=f"Title too long (max {_MAX_TITLE_LEN} characters)"
        )
    description = (req.description or "").strip()
    if len(description) > _MAX_DESC_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Description too long (max {_MAX_DESC_LEN} characters)",
        )
    concept = (req.concept or "").strip()
    topic = (req.topic or "").strip() or title

    short_uid = user_id.replace("-", "")[:8]
    key = f"u_{short_uid}_{_slugify(title)}"

    with get_session() as session:
        existing = session.execute(
            select(Section).where(
                Section.language == language, Section.key == key
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Section already exists")
        # Place user sections after the seeded ones.
        section = Section(
            language=language,
            key=key,
            title=title,
            description=description,
            concept=concept,
            topic=topic,
            is_user_created=True,
            owner_user_id=user_id,
            order_index=1000,
        )
        session.add(section)
        session.flush()
        user = session.get(User, user_id)
        current_section_id = getattr(user, "current_section_id", None) if user else None
        return _section_dict(section, current_section_id)


@router.post("/sections/select")
def post_select_section(
    req: SectionSelect, current_user: dict = Depends(get_current_user)
):
    """Set current section + run a fresh themed turn (spec §3.3, fixes req #7).

    Returns the turn result exactly like ``/api/chat``:
    ``{interrupted, response, state}`` where ``state.current_task_id`` is the NEW
    task, ``state.cancelled_task_id`` is the discarded one, ``state.topic`` is the
    new theme and ``state.current_section_id`` is the selected section.
    """
    return select_section_turn(current_user["id"], req.session_id, req.section_id)


@router.post("/sections/{section_id}/intro")
def post_section_intro(
    section_id: str,
    req: SectionIntro,
    current_user: dict = Depends(get_current_user),
):
    """The "?" pictogram: intro articles + a video for the section (spec §3.5).

    Returns a chat-message-shaped payload (``response`` + ``links``) the frontend
    appends to the chat. ``>=4`` verified links (dead ones replaced via search,
    fail-open to seeded links).
    """
    return section_intro(current_user["id"], section_id, req.language)
