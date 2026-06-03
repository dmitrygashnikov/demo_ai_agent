"""Pragmatic relational link store + health tracking (req. 3).

This module is the reusable seam the API / graph subtasks call to persist,
reuse, verify, prune and top-up remediation/intro links. It is the authoritative
source for the link-health features (independent of Qdrant).

Design principles (mirroring the project's existing fail-open philosophy):

* **Never raise to callers.** Every public helper wraps its work in try/except
  and degrades to a safe value (empty list / no-op / ``False``) on error.
* **Counter-based health, not event logging.** A rolling 3-day window + a fail
  counter drives pruning ("more than 50 fails within the last 3 days → delete"),
  exactly as specified in the spec's §2.3.
* **Verification at serve-time.** Availability is checked when assembling a
  response (≤4s HTTP timeout, concurrent, fail-open), not at save-time.

Public API (stable — the C subtask wires these into web_search / remediation /
the "?" intro flow):

    ``save_link(...) -> str | None``           — upsert one link, returns its id.
    ``save_links(items) -> int``               — bulk upsert, returns count saved.
    ``get_links(error_type, language, ...)``   — fetch candidate links (ordered).
    ``check_url(url) -> bool``                  — single HTTP availability probe.
    ``verify_links(links) -> list[dict]``       — concurrent verify + health update.
    ``record_failure(link_id) / record_success(link_id)`` — health bookkeeping.
    ``get_verified_links(error_type, language, *, min_links=4, ...)``
                                                — the >=4-verified-links getter
                                                  with a replacement-via-search seam.
    ``set_replacement_search(fn)``              — inject the real web_search (seam
                                                  for subtask C); a working
                                                  seeded fallback is used until then.

All timestamps are naive UTC (``datetime.utcnow``), matching the model columns.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Callable, Iterable, Optional

from sqlalchemy import select

from app.db.models import RemediationLink
from app.db.session import get_session

logger = logging.getLogger(__name__)

# --- Health-tracking constants (the "50 fails in 3 days" rule, spec §2.3) ---
FAIL_WINDOW = timedelta(days=3)
FAIL_THRESHOLD = 50

# Minimum links an error explanation / intro panel must surface (req. 3 / #8).
MIN_LINKS = 4

# HTTP availability probe budget (spec §4.4 / §8: short timeout, concurrent).
_HTTP_TIMEOUT = 4.0
_MAX_VERIFY_WORKERS = 6
# A link verified successfully within this window is trusted without re-probing
# (spec §8 latency mitigation).
_TRUST_WINDOW = timedelta(hours=6)


# ---------------------------------------------------------------------------
# Replacement-search seam (subtask C wires the real web_search here)
# ---------------------------------------------------------------------------
# Signature: fn(query: str, *, max_results: int, language: str) -> list[dict]
# where each dict has at least {"title", "url", "snippet"}. Until C injects the
# real searcher, ``get_verified_links`` falls back to the seeded store only.
_replacement_search: Optional[Callable[..., list[dict]]] = None


def set_replacement_search(fn: Optional[Callable[..., list[dict]]]) -> None:
    """Inject the link-replacement searcher (clean seam for subtask C).

    Subtask C calls this once at startup with an adapter around the real
    ``app.search.web_search`` (converting ``SearchResult`` → dict). Passing
    ``None`` clears it (tests / offline). Never raises.
    """
    global _replacement_search
    _replacement_search = fn


def _utcnow() -> datetime:
    return datetime.utcnow()


def _to_dict(link: RemediationLink) -> dict:
    """Serialise a row to the plain dict shape callers consume."""
    return {
        "id": link.id,
        "url": link.url,
        "title": link.title,
        "snippet": link.snippet,
        "language": link.language,
        "error_type": link.error_type,
        "concept": link.concept,
        "kind": link.kind,
        "fail_count": link.fail_count,
        "last_ok": link.last_ok,
    }


# ---------------------------------------------------------------------------
# Persistence (save / upsert)
# ---------------------------------------------------------------------------
def save_link(
    url: str,
    *,
    error_type: str = "",
    language: str = "",
    title: str = "",
    snippet: str = "",
    concept: str = "",
    kind: str = "remediation",
) -> Optional[str]:
    """Upsert a single link on the ``(url, error_type, language)`` unique key.

    Get-or-create: an existing row is refreshed with the latest title/snippet/
    concept/kind but its **health counters are left untouched** (re-saving a link
    must not reset its fail history, spec §4.2). Returns the row id, or ``None``
    on failure. Never raises.
    """
    url = (url or "").strip()
    if not url:
        return None
    error_type = (error_type or "").strip()
    language = (language or "").strip()
    try:
        with get_session() as session:
            existing = session.execute(
                select(RemediationLink).where(
                    RemediationLink.url == url,
                    RemediationLink.error_type == error_type,
                    RemediationLink.language == language,
                )
            ).scalar_one_or_none()
            if existing is not None:
                # Refresh display fields only; never touch health counters.
                if title:
                    existing.title = title
                if snippet:
                    existing.snippet = snippet
                if concept:
                    existing.concept = concept
                if kind:
                    existing.kind = kind
                return existing.id
            row = RemediationLink(
                url=url,
                title=title or "",
                snippet=snippet or "",
                language=language,
                error_type=error_type,
                concept=(concept or "").strip(),
                kind=kind or "remediation",
            )
            session.add(row)
            session.flush()
            return row.id
    except Exception as exc:  # noqa: BLE001 — fail-open, never break a turn.
        logger.warning("save_link failed for %r: %s", url, exc)
        return None


def save_links(items: Iterable[dict]) -> int:
    """Bulk upsert. Each item: ``{url, error_type, language, title, snippet,
    concept, kind}`` (only ``url`` required). Returns how many were saved/updated.
    Never raises.
    """
    saved = 0
    for it in items or []:
        try:
            res = save_link(
                str(it.get("url") or ""),
                error_type=str(it.get("error_type") or ""),
                language=str(it.get("language") or ""),
                title=str(it.get("title") or ""),
                snippet=str(it.get("snippet") or ""),
                concept=str(it.get("concept") or ""),
                kind=str(it.get("kind") or "remediation"),
            )
            if res:
                saved += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("save_links item skipped: %s", exc)
    return saved


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
def get_links(
    error_type: str = "",
    language: str = "",
    *,
    concept: str = "",
    kind: str = "remediation",
    limit: int = 12,
) -> list[dict]:
    """Load candidate links for an error/topic, ordered by health.

    Remediation lookups key on ``error_type`` + ``language``; intro lookups
    (``kind='intro'``) key on ``concept`` + ``language``. Ordering puts healthy
    links first (``last_ok`` desc, then fewest fails), per spec §4.3. Returns
    plain dicts; never raises.
    """
    error_type = (error_type or "").strip()
    language = (language or "").strip()
    concept = (concept or "").strip()
    try:
        with get_session() as session:
            stmt = select(RemediationLink)
            if kind:
                stmt = stmt.where(RemediationLink.kind == kind)
            if language:
                stmt = stmt.where(RemediationLink.language == language)
            if kind == "intro" and concept:
                stmt = stmt.where(RemediationLink.concept == concept)
            elif error_type:
                stmt = stmt.where(RemediationLink.error_type == error_type)
            elif concept:
                stmt = stmt.where(RemediationLink.concept == concept)
            stmt = stmt.order_by(
                RemediationLink.last_ok.desc(),
                RemediationLink.fail_count.asc(),
                RemediationLink.created_at.asc(),
            ).limit(max(1, limit))
            rows = session.execute(stmt).scalars().all()
            return [_to_dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_links failed (%s/%s): %s", error_type, language, exc)
        return []


# ---------------------------------------------------------------------------
# Availability verification (HTTP)
# ---------------------------------------------------------------------------
def check_url(url: str) -> bool:
    """Probe a URL's availability with a short-timeout HTTP HEAD (→ GET fallback).

    Treats ``2xx``/``3xx`` as alive; everything else (incl. timeout / connection
    error) as dead. Strictly fail-open at the feature level: a network error
    marks the *link* dead for this serve but this function never raises — it just
    returns ``False``. Redirects are followed (spec §4.4).
    """
    url = (url or "").strip()
    if not url:
        return False
    try:
        import httpx

        with httpx.Client(
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (AdaptiveTutor LinkCheck)"},
        ) as client:
            try:
                resp = client.head(url)
                # Some servers reject/!=200 HEAD; retry with a tiny ranged GET.
                if resp.status_code >= 400:
                    resp = client.get(url, headers={"Range": "bytes=0-0"})
            except Exception:  # noqa: BLE001 — HEAD unsupported; try GET.
                resp = client.get(url, headers={"Range": "bytes=0-0"})
            return 200 <= resp.status_code < 400
    except Exception as exc:  # noqa: BLE001 — fail-open: dead, never raise.
        logger.debug("check_url dead %r: %s", url, exc)
        return False


def record_success(link_id: str) -> None:
    """Mark a link healthy after a successful probe (spec §2.3).

    Updates ``last_checked`` + ``last_ok``; does NOT reset ``fail_count``
    mid-window (the window is purely time-based and self-resets). Never raises.
    """
    if not link_id:
        return
    try:
        with get_session() as session:
            link = session.get(RemediationLink, link_id)
            if link is None:
                return
            link.last_checked = _utcnow()
            link.last_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.debug("record_success failed for %s: %s", link_id, exc)


def record_failure(link_id: str) -> bool:
    """Bump a link's rolling fail counter; prune (delete) if it exceeds the
    threshold within the active window (spec §2.3).

    Algorithm:
        now = utcnow()
        if window unset or older than FAIL_WINDOW: reset window, fail_count = 1
        else: fail_count += 1
        last_checked = now; last_ok = False
        if fail_count > FAIL_THRESHOLD: delete the link.

    Returns ``True`` if the link was pruned. Never raises.
    """
    if not link_id:
        return False
    try:
        with get_session() as session:
            link = session.get(RemediationLink, link_id)
            if link is None:
                return False
            now = _utcnow()
            if link.fail_window_start is None or (
                now - link.fail_window_start
            ) > FAIL_WINDOW:
                # Window expired or never started → reset the rolling window.
                link.fail_window_start = now
                link.fail_count = 1
            else:
                link.fail_count += 1
            link.last_checked = now
            link.last_ok = False
            if link.fail_count > FAIL_THRESHOLD:
                session.delete(link)
                logger.info(
                    "Pruned link %s (>%d fails within %s window)",
                    link.url,
                    FAIL_THRESHOLD,
                    FAIL_WINDOW,
                )
                return True
            return False
    except Exception as exc:  # noqa: BLE001
        logger.debug("record_failure failed for %s: %s", link_id, exc)
        return False


def verify_links(links: list[dict]) -> list[dict]:
    """Concurrently verify a list of link dicts; update health; return survivors.

    For each link:
      * if it has a recent successful ``last_checked`` (within ``_TRUST_WINDOW``)
        it is trusted without re-probing (latency mitigation, spec §8);
      * otherwise probe with :func:`check_url`. On success → ``record_success``
        and keep it; on failure → ``record_failure`` (may prune) and drop it.

    Returns only the links that verified alive, preserving input order. Never
    raises (a verification error simply drops that link from this serve).
    """
    if not links:
        return []

    # Resolve which need probing vs. can be trusted (recent OK).
    to_probe: list[dict] = []
    trusted: dict[int, dict] = {}
    try:
        ids = [l.get("id") for l in links if l.get("id")]
        recent_ok: dict[str, bool] = {}
        if ids:
            with get_session() as session:
                now = _utcnow()
                rows = (
                    session.execute(
                        select(RemediationLink).where(RemediationLink.id.in_(ids))
                    )
                    .scalars()
                    .all()
                )
                for r in rows:
                    recent_ok[r.id] = bool(
                        r.last_ok
                        and r.last_checked is not None
                        and (now - r.last_checked) < _TRUST_WINDOW
                    )
        for idx, link in enumerate(links):
            lid = link.get("id")
            if lid and recent_ok.get(lid):
                trusted[idx] = link
            else:
                to_probe.append(link)
    except Exception as exc:  # noqa: BLE001 — degrade: probe everything.
        logger.debug("verify_links trust-check failed: %s", exc)
        to_probe = list(links)
        trusted = {}

    # Probe the remainder concurrently.
    probe_alive: dict[str, bool] = {}
    if to_probe:
        try:
            urls = [(l.get("url") or "") for l in to_probe]
            with ThreadPoolExecutor(
                max_workers=min(_MAX_VERIFY_WORKERS, len(urls))
            ) as pool:
                results = list(pool.map(check_url, urls))
            for link, alive in zip(to_probe, results):
                url = link.get("url") or ""
                probe_alive[url] = alive
                lid = link.get("id")
                if alive:
                    if lid:
                        record_success(lid)
                else:
                    if lid:
                        record_failure(lid)
        except Exception as exc:  # noqa: BLE001
            logger.debug("verify_links probing failed: %s", exc)
            # Fail-open: if probing blew up, trust the links rather than dropping.
            for link in to_probe:
                probe_alive[link.get("url") or ""] = True

    out: list[dict] = []
    for idx, link in enumerate(links):
        if idx in trusted:
            out.append(link)
        elif probe_alive.get(link.get("url") or "", False):
            out.append(link)
    return out


# ---------------------------------------------------------------------------
# The >=4-verified-links getter (with replacement-via-search seam)
# ---------------------------------------------------------------------------
def get_verified_links(
    error_type: str = "",
    language: str = "",
    *,
    concept: str = "",
    kind: str = "remediation",
    min_links: int = MIN_LINKS,
    query: str = "",
) -> list[dict]:
    """Return ``>= min_links`` verified links for an error/topic explanation.

    Pipeline (spec §4.3 / §4.5 / §4.6):
      1. Load candidate links from the store (ordered by health).
      2. Verify availability concurrently; drop dead ones (health updated/pruned).
      3. If fewer than ``min_links`` survive, trigger replacement-via-search
         through the injected seam (:func:`set_replacement_search`), persist the
         new links, verify them, and append until the floor is met.
      4. Fail-open: if search is unavailable / still short, return whatever
         verified links we have (the seeded floor guarantees >=4 offline).

    Never raises. ``query`` is the search string used for top-up (subtask C
    supplies a themed query, e.g. ``"python TypeError fix"``).
    """
    min_links = max(1, min_links)
    try:
        candidates = get_links(
            error_type=error_type,
            language=language,
            concept=concept,
            kind=kind,
            limit=max(min_links * 3, 12),
        )
        verified = verify_links(candidates)
        if len(verified) >= min_links:
            return verified[: max(min_links, len(verified))]

        # Too few → try replacement-via-search through the C-wired seam.
        seen = {l.get("url") for l in verified}
        if _replacement_search is not None:
            search_query = (query or "").strip() or " ".join(
                p for p in [language, error_type or concept, "fix tutorial"] if p
            )
            try:
                raw = _replacement_search(
                    search_query,
                    max_results=max(min_links + 2, 6),
                    language="en",
                )
            except Exception as exc:  # noqa: BLE001 — seam must never break us.
                logger.debug("replacement search failed: %s", exc)
                raw = []
            new_items: list[dict] = []
            for item in raw or []:
                url = str(item.get("url") or "")
                if not url or url in seen:
                    continue
                seen.add(url)
                new_items.append(
                    {
                        "url": url,
                        "title": str(item.get("title") or ""),
                        "snippet": str(item.get("snippet") or ""),
                        "language": language,
                        "error_type": error_type,
                        "concept": concept,
                        "kind": kind,
                    }
                )
            if new_items:
                save_links(new_items)
                # Re-fetch (so the dicts carry ids for health tracking) + verify.
                refreshed = get_links(
                    error_type=error_type,
                    language=language,
                    concept=concept,
                    kind=kind,
                    limit=max(min_links * 3, 12),
                )
                verified = verify_links(refreshed)

        # Fail-open: return whatever we have (seeded floor guarantees >=4).
        return verified[: max(min_links, len(verified))] if verified else verified
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "get_verified_links failed (%s/%s): %s", error_type, language, exc
        )
        return []
