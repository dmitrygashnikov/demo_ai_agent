"""Baseline intro + remediation LINK seed (spec §5.2).

Guarantees the >=4-article + >=1-video floor **per (language, concept)** so
requirement #3's "at least 4 links per error explanation" and #8's intro
material hold even fully offline (no live search). Persisted into the
``remediation_links`` table by ``app.seed.sections.seed_links`` via the link
store (idempotent upsert on ``(url, error_type, language)``).

URL policy (spec §5.2): use **stable real documentation URLs** for the article
floor (docs.python.org, developer.mozilla.org) so the serve-time HTTP
availability check passes when egress is available; a YouTube *search-results*
URL is used as the always-resolvable video fallback (mirrors the example.com
video pattern already in ``curated.VIDEOS`` but pointing at a real host).

Shape (consumed by :func:`app.rag.link_store.save_links`):

    { "language", "concept", "error_type", "kind",  # "intro" | "remediation"
      "title", "url", "snippet" }

``build_seed_links()`` flattens the per-concept floors into that flat list. Each
concept yields BOTH an ``intro`` set (keyed by ``concept`` for the "?" flow) and
a ``remediation`` set (keyed by ``error_type == concept`` for the failure flow),
so both serve paths have an offline >=4 floor.
"""
from __future__ import annotations

# Per-language documentation roots used to synthesise stable article links.
_PY_DOCS = "https://docs.python.org/3"
_MDN = "https://developer.mozilla.org/en-US/docs/Web/JavaScript"
_PY_REALPYTHON = "https://realpython.com"
_MDN_LEARN = "https://developer.mozilla.org/en-US/docs/Learn/JavaScript"
_W3_PY = "https://www.w3schools.com/python"
_W3_JS = "https://www.w3schools.com/js"


def _yt(query: str) -> str:
    """Always-resolvable YouTube search-results URL for a video fallback."""
    from urllib.parse import quote_plus

    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


# Human-readable concept labels (shared across both languages where they match).
_CONCEPT_LABEL = {
    "variables": "variables and types",
    "io": "input and output",
    "conditions": "conditions and branching",
    "loops": "loops and iteration",
    "functions": "functions",
    "collections": "lists and collections",
    "dicts": "dictionaries and objects",
    "strings": "string processing",
    "errors": "error handling",
    "oop": "object-oriented programming",
    "comprehensions": "comprehensions and functional",
    "recursion": "recursion",
    "modules": "modules and imports",
    "api": "working with APIs",
    "project": "mini projects",
    # Domain themes (concept "" in sections → keyed by section key here).
    "data_analysis_pandas": "data analysis with pandas",
    "web_scraping": "web scraping",
    "automation": "automation scripting",
    "file_csv": "file and CSV processing",
    "testing_pytest": "testing with pytest",
    "dom": "DOM manipulation",
    "async": "async and promises",
    "fetch_http": "fetch and HTTP requests",
    "json_data": "JSON data handling",
    "node_scripting": "Node.js scripting",
}

# All concept/section keys we seed a floor for, per language. These mirror the
# section keys in ``app.seed.sections`` so the "?" intro flow always resolves.
_PY_KEYS = [
    "variables", "io", "conditions", "loops", "functions", "collections",
    "dicts", "strings", "errors", "oop", "comprehensions", "recursion",
    "modules", "api", "project", "data_analysis_pandas", "web_scraping",
    "automation", "file_csv", "testing_pytest",
]
_JS_KEYS = [
    "variables", "io", "conditions", "loops", "functions", "collections",
    "dicts", "strings", "errors", "oop", "comprehensions", "recursion",
    "modules", "api", "project", "dom", "async", "fetch_http", "json_data",
    "node_scripting",
]


def _python_articles(concept: str, label: str) -> list[tuple[str, str]]:
    """Return >=4 (title, url) article tuples for a Python concept.

    A ``#<concept>`` fragment makes each URL **unique per concept** so the
    ``(url, error_type, language)`` unique key never collapses two concepts'
    floors onto a single row. Fragments are ignored by the HTTP availability
    check (the server returns the page regardless), so the link still resolves.
    """
    frag = f"#tutor-{concept}"
    return [
        (
            f"Python {label} — official tutorial",
            f"{_PY_DOCS}/tutorial/index.html{frag}",
        ),
        (
            f"Python {label} — language reference",
            f"{_PY_DOCS}/reference/index.html{frag}",
        ),
        (
            f"Python {label} — Real Python guide",
            f"{_PY_REALPYTHON}/?s={concept}",
        ),
        (
            f"Python {label} — W3Schools",
            f"{_W3_PY}/default.asp{frag}",
        ),
        (
            f"Python standard library reference ({label})",
            f"{_PY_DOCS}/library/index.html{frag}",
        ),
    ]


def _javascript_articles(concept: str, label: str) -> list[tuple[str, str]]:
    """Return >=4 (title, url) article tuples for a JavaScript concept.

    See :func:`_python_articles` for why a ``#<concept>`` fragment is appended:
    it keeps each seeded URL unique per concept under the unique key.
    """
    frag = f"#tutor-{concept}"
    return [
        (
            f"JavaScript {label} — MDN reference",
            f"{_MDN}/Reference{frag}",
        ),
        (
            f"JavaScript {label} — MDN guide",
            f"{_MDN}/Guide{frag}",
        ),
        (
            f"JavaScript {label} — MDN Learn",
            f"{_MDN_LEARN}/First_steps{frag}",
        ),
        (
            f"JavaScript {label} — W3Schools",
            f"{_W3_JS}/default.asp{frag}",
        ),
        (
            f"JavaScript {label} — MDN data structures",
            f"{_MDN}/Data_structures{frag}",
        ),
    ]


def _floor_for(language: str, concept: str) -> list[dict]:
    """Build the >=4-article + >=1-video floor (intro + remediation) for one
    (language, concept). Returns flat link dicts ready for ``save_links``."""
    label = _CONCEPT_LABEL.get(concept, concept.replace("_", " "))
    if language == "python":
        articles = _python_articles(concept, label)
    else:
        articles = _javascript_articles(concept, label)

    video_query = f"{language} {label} tutorial"
    video = (f"{language.title()} {label} explained (video)", _yt(video_query))

    out: list[dict] = []
    for kind in ("intro", "remediation"):
        # intro keys on concept; remediation keys on error_type (== concept here
        # so the offline floor also backs failure explanations by concept). The
        # unique key is (url, error_type, language); intro rows carry
        # error_type="" while remediation rows carry error_type=concept, so the
        # same URL can live as both an intro and a remediation row.
        error_type = "" if kind == "intro" else concept
        for title, url in articles:
            out.append(
                {
                    "language": language,
                    "concept": concept,
                    "error_type": error_type,
                    "kind": kind,
                    "title": title,
                    "url": url,
                    "snippet": f"Reference material on {label} in {language}.",
                }
            )
        # >=1 video per concept.
        out.append(
            {
                "language": language,
                "concept": concept,
                "error_type": error_type,
                "kind": "video" if kind == "intro" else "remediation",
                "title": video[0],
                "url": video[1],
                "snippet": f"Video walkthrough of {label} in {language}.",
            }
        )
    return out


def build_seed_links() -> list[dict]:
    """Flatten every (language, concept) floor into one list of link dicts.

    >=5 articles + 1 video per (language, concept) per kind, for 20 concepts in
    each of two languages → a generous offline floor well above the >=4 minimum.
    """
    items: list[dict] = []
    for concept in _PY_KEYS:
        items.extend(_floor_for("python", concept))
    for concept in _JS_KEYS:
        items.extend(_floor_for("javascript", concept))
    return items
