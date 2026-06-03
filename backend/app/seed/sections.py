"""Seed human-readable sidebar SECTIONS + baseline intro/remediation LINKS.

Implements the spec's Seed Plan (§5): 20 human-readable sections per language
and a >=4-article + >=1-video link floor per section concept, persisted into the
``remediation_links`` table so the serve-time verify/replace/prune logic (and the
"?" intro flow) have an offline baseline.

Both seeders are idempotent and mirror :func:`app.seed.skills.seed_skills`:

* :func:`seed_sections` get-or-creates per ``(language, key)``.
* :func:`seed_links` upserts links via :func:`app.rag.link_store.save_link`
  (idempotent on ``(url, error_type, language)``), so a restart never duplicates.

Both are invoked from ``app.main._startup_seed`` after ``seed_skills``.
"""
from __future__ import annotations

import logging

from app.db.models import Section
from app.db.session import get_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Section definitions (spec §5.1). 20 per language; concepts 1-15 reuse the
# existing skill concepts so section selection can steer the skill axis, 16-20
# are domain themes (concept "" → pure topic theme). topic defaults to title.
# Tuple shape: (key, title, concept). description is derived from the title.
# ---------------------------------------------------------------------------
PYTHON_SECTIONS: list[tuple[str, str, str]] = [
    ("variables", "Variables & types", "variables"),
    ("io", "Input / output", "io"),
    ("conditions", "Conditions & branching", "conditions"),
    ("loops", "Loops & iteration", "loops"),
    ("functions", "Functions", "functions"),
    ("collections", "Lists & collections", "collections"),
    ("dicts", "Dictionaries", "dicts"),
    ("strings", "String processing", "strings"),
    ("errors", "Error handling", "errors"),
    ("oop", "Object-oriented programming", "oop"),
    ("comprehensions", "Comprehensions & functional", "comprehensions"),
    ("recursion", "Recursion", "recursion"),
    ("modules", "Modules & imports", "modules"),
    ("api", "Working with APIs", "api"),
    ("project", "Mini project", "project"),
    ("data_analysis_pandas", "Data analysis with pandas", ""),
    ("web_scraping", "Web scraping", ""),
    ("automation", "Automation scripting", ""),
    ("file_csv", "File & CSV processing", ""),
    ("testing_pytest", "Testing with pytest", ""),
]

JAVASCRIPT_SECTIONS: list[tuple[str, str, str]] = [
    ("variables", "Variables & types", "variables"),
    ("io", "Input / output", "io"),
    ("conditions", "Conditions & branching", "conditions"),
    ("loops", "Loops & iteration", "loops"),
    ("functions", "Functions", "functions"),
    ("collections", "Arrays & collections", "collections"),
    ("dicts", "Objects", "dicts"),
    ("strings", "String processing", "strings"),
    ("errors", "Error handling", "errors"),
    ("oop", "Object-oriented programming", "oop"),
    ("comprehensions", "Array methods & functional", "comprehensions"),
    ("recursion", "Recursion", "recursion"),
    ("modules", "Modules & imports", "modules"),
    ("api", "Working with APIs", "api"),
    ("project", "Mini project", "project"),
    ("dom", "DOM manipulation basics", ""),
    ("async", "Async & promises", ""),
    ("fetch_http", "Fetch & HTTP requests", ""),
    ("json_data", "JSON data handling", ""),
    ("node_scripting", "Node.js scripting", ""),
]


def seed_sections() -> int:
    """Insert the human-readable sidebar sections (idempotent). Returns count.

    Get-or-create per ``(language, key)`` mirroring ``seed_skills``: existing
    rows are refreshed (title/description/concept/topic/order) so seed edits
    propagate, but ids and ``is_user_created``/``owner_user_id`` stay stable.
    """
    total = 0
    plan = [("python", PYTHON_SECTIONS), ("javascript", JAVASCRIPT_SECTIONS)]
    with get_session() as session:
        for language, sections in plan:
            for order_index, (key, title, concept) in enumerate(sections):
                description = f"Practice and learn: {title} in {language}."
                existing = (
                    session.query(Section)
                    .filter(Section.language == language, Section.key == key)
                    .one_or_none()
                )
                if existing is None:
                    session.add(
                        Section(
                            language=language,
                            key=key,
                            title=title,
                            description=description,
                            concept=concept,
                            topic=title,
                            is_user_created=False,
                            owner_user_id=None,
                            order_index=order_index,
                        )
                    )
                else:
                    existing.title = title
                    existing.description = description
                    existing.concept = concept
                    # Preserve a user-customised topic; only backfill if empty.
                    if not existing.topic:
                        existing.topic = title
                    existing.order_index = order_index
                total += 1
    logger.info("Seeded %d sections", total)
    return total


def seed_links() -> int:
    """Seed the baseline intro + remediation links (idempotent). Returns count.

    Reads the generated ``INTRO_LINKS`` floor from
    ``app.seed.content.curated_links`` and upserts each into ``remediation_links``
    via the link store (idempotent on the unique key). Best-effort / fail-open.
    """
    try:
        from app.rag.link_store import save_links
        from app.seed.content.curated_links import build_seed_links

        items = build_seed_links()
        saved = save_links(items)
        logger.info("Seeded %d remediation/intro links", saved)
        return saved
    except Exception as exc:  # noqa: BLE001 — fail-open, never break startup.
        logger.error("seed_links failed: %s", exc)
        return 0
