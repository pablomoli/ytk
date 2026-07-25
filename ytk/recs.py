"""Recommendation resolution + a growing deduped store.

Two responsibilities:

1. Resolve a loosely-named recommendation (a title the user's notes mention) to
   canonical metadata via free public APIs — TMDb for movies/shows, AniList for
   anime/manga, Open Library for books — and persist every mention into a
   growing deduped store at ``~/.ytk/recs.json``. Unresolved titles are kept
   under an ``unresolved:`` key so a mention is never silently dropped.

2. Pull recommendations out of arbitrary note text with a single cheap Haiku
   pass (:func:`extract_recommendations`), mirroring the schema-forced style of
   ``ytk.enrich``. The backfill step calls this over already-ingested notes.

Network policy: every HTTP request routes through :func:`_http_get` /
:func:`_http_post_json`, which apply a 10s timeout, a User-Agent, and swallow
all failures (returning ``None``). Resolvers therefore never raise out of
:func:`resolve`. Routing every request through those two functions is also what
lets the tests mock the network by monkeypatching just two names.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from pydantic import BaseModel

from .enrich import REC_KINDS, Recommendation
from .sdk import run_structured

try:  # .env is not loaded on plain import of ytk.config; load it here too.
    from dotenv import load_dotenv

    load_dotenv(Path.home() / ".ytk" / ".env")
    load_dotenv()
except Exception:  # pragma: no cover - dotenv always present, guard anyway
    pass


VALID_KINDS = set(REC_KINDS)
VALID_STATUS = {"want", "seen", "skip", None}
RECS_PATH = Path.home() / ".ytk" / "recs.json"

_USER_AGENT = "ytk-recs/1.0 (+https://github.com/ytk)"
_TIMEOUT = 10


# --------------------------------------------------------------------------- #
# HTTP transport (the only two functions that touch the network)
# --------------------------------------------------------------------------- #


def _http_get(url: str, headers: dict | None = None) -> dict | None:
    """GET ``url`` and parse the JSON body. Returns ``None`` on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _http_post_json(url: str, payload: dict, headers: dict | None = None) -> dict | None:
    """POST ``payload`` as JSON and parse the JSON body. ``None`` on failure."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Resolvers
# --------------------------------------------------------------------------- #


def _tmdb_request(path: str, params: dict | None = None) -> dict | None:
    """Call a TMDb v3 endpoint. Prefers the v4 bearer token
    (``TMDB_READ_TOKEN``); falls back to the v3 ``TMDB_API_KEY`` query param."""
    params = dict(params or {})
    headers = {}
    token = os.environ.get("TMDB_READ_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        key = os.environ.get("TMDB_API_KEY")
        if key:
            params["api_key"] = key
    url = f"https://api.themoviedb.org/3{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return _http_get(url, headers=headers)


def _tmdb_poster(poster_path: str | None) -> str | None:
    return f"https://image.tmdb.org/t/p/w342{poster_path}" if poster_path else None


def _year_prefix(date_str: str | None) -> int | None:
    if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
        return int(date_str[:4])
    return None


def _resolve_movie(title: str, year: int | None) -> dict | None:
    params: dict[str, str | int] = {"query": title}
    if year:
        params["year"] = year
    data = _tmdb_request("/search/movie", params)
    results = (data or {}).get("results") or []
    if not results:
        return None
    m = results[0]
    mid = m["id"]
    creator = None
    credits = _tmdb_request(f"/movie/{mid}/credits")
    if credits:
        for c in credits.get("crew", []):
            if c.get("job") == "Director":
                creator = c.get("name")
                break
    return {
        "canonical_key": f"tmdb:movie:{mid}",
        "kind": "movie",
        "title": m.get("title") or title,
        "year": _year_prefix(m.get("release_date")),
        "creator": creator,
        "poster": _tmdb_poster(m.get("poster_path")),
        "rating": m.get("vote_average"),
        "overview": m.get("overview") or None,
        "external_url": f"https://www.themoviedb.org/movie/{mid}",
    }


def _resolve_show(title: str, year: int | None) -> dict | None:
    params: dict[str, str | int] = {"query": title}
    if year:
        params["first_air_date_year"] = year
    data = _tmdb_request("/search/tv", params)
    results = (data or {}).get("results") or []
    if not results:
        return None
    m = results[0]
    mid = m["id"]
    return {
        "canonical_key": f"tmdb:tv:{mid}",
        "kind": "show",
        "title": m.get("name") or title,
        "year": _year_prefix(m.get("first_air_date")),
        "creator": None,  # skip a credits call for shows to keep resolution cheap
        "poster": _tmdb_poster(m.get("poster_path")),
        "rating": m.get("vote_average"),
        "overview": m.get("overview") or None,
        "external_url": f"https://www.themoviedb.org/tv/{mid}",
    }


_ANILIST_URL = "https://graphql.anilist.co"

_ANIME_QUERY = """
query ($q: String) {
  Media(search: $q, type: ANIME) {
    id
    title { romaji english }
    coverImage { large }
    seasonYear
    averageScore
    siteUrl
    studios(isMain: true) { nodes { name } }
  }
}
"""

_MANGA_QUERY = """
query ($q: String) {
  Media(search: $q, type: MANGA) {
    id
    title { romaji english }
    coverImage { large }
    seasonYear
    averageScore
    siteUrl
    staff(perPage: 1) { nodes { name { full } } }
  }
}
"""


def _anilist_media(query: str, title: str) -> dict | None:
    data = _http_post_json(_ANILIST_URL, {"query": query, "variables": {"q": title}})
    media = ((data or {}).get("data") or {}).get("Media")
    return media or None


def _resolve_anime(title: str) -> dict | None:
    m = _anilist_media(_ANIME_QUERY, title)
    if not m:
        return None
    names = m.get("title") or {}
    studios = ((m.get("studios") or {}).get("nodes")) or []
    creator = studios[0].get("name") if studios else None
    return {
        "canonical_key": f"anilist:{m['id']}",
        "kind": "anime",
        "title": names.get("english") or names.get("romaji") or title,
        "year": m.get("seasonYear"),
        "creator": creator,
        "poster": (m.get("coverImage") or {}).get("large"),
        # averageScore is AniList's 0-100 scale; kept as-is (not rescaled to /10).
        "rating": m.get("averageScore"),
        "overview": None,
        "external_url": m.get("siteUrl"),
    }


def _resolve_manga(title: str) -> dict | None:
    m = _anilist_media(_MANGA_QUERY, title)
    if not m:
        return None
    names = m.get("title") or {}
    staff = ((m.get("staff") or {}).get("nodes")) or []
    creator = (staff[0].get("name") or {}).get("full") if staff else None
    return {
        "canonical_key": f"anilist:{m['id']}",
        "kind": "manga",
        "title": names.get("english") or names.get("romaji") or title,
        "year": m.get("seasonYear"),
        "creator": creator,
        "poster": (m.get("coverImage") or {}).get("large"),
        "rating": m.get("averageScore"),
        "overview": None,
        "external_url": m.get("siteUrl"),
    }


def _resolve_book(title: str, creator: str | None) -> dict | None:
    params = {"title": title, "limit": 1}
    if creator:
        params["author"] = creator
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
    data = _http_get(url)
    docs = (data or {}).get("docs") or []
    if not docs:
        return None
    d = docs[0]
    authors = d.get("author_name") or []
    isbns = d.get("isbn") or []
    ol_key = d.get("key") or ""
    canonical_key = f"isbn:{isbns[0]}" if isbns else f"ol:{ol_key}"
    cover_i = d.get("cover_i")
    poster = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg" if cover_i else None
    return {
        "canonical_key": canonical_key,
        "kind": "book",
        "title": d.get("title") or title,
        "year": d.get("first_publish_year"),
        "creator": authors[0] if authors else (creator or None),
        "poster": poster,
        "rating": None,
        "overview": None,
        "external_url": f"https://openlibrary.org{ol_key}" if ol_key else None,
    }


def resolve(
    kind: str, title: str, creator: str | None = None, year: int | None = None
) -> dict | None:
    """Resolve a title to canonical metadata, dispatching by ``kind``.

    Returns a canonical dict (see module docstring) or ``None`` when the title
    cannot be resolved, the kind is unknown, or any network call fails.
    """
    title = (title or "").strip()
    if not title:
        return None
    kind = (kind or "").strip().lower()
    if kind not in VALID_KINDS:
        return None
    try:
        if kind == "movie":
            return _resolve_movie(title, year)
        if kind == "show":
            return _resolve_show(title, year)
        if kind == "anime":
            return _resolve_anime(title)
        if kind == "manga":
            return _resolve_manga(title)
        if kind == "book":
            return _resolve_book(title, creator)
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")


def load_recs(path=RECS_PATH) -> dict:
    """Load the store as ``{canonical_key: entry}``. Missing or corrupt files
    yield an empty dict so a bad write never blocks recording."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_recs(data: dict, path=RECS_PATH) -> None:
    """Atomically persist the store (write to a temp sibling, then replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)


_ENTRY_META_FIELDS = (
    "canonical_key",
    "kind",
    "title",
    "year",
    "creator",
    "poster",
    "rating",
    "overview",
    "external_url",
)


def record(kind, title, creator, note_path, path=RECS_PATH) -> dict | None:
    """Resolve ``title`` and fold the mention into the store.

    Creates a new entry or bumps an existing one. ``sources`` is deduped so a
    given note counts a title once; ``count`` tracks ``len(sources)``.
    Unresolved titles are stored under ``unresolved:{kind}:{slug}`` with the
    same entry shape (metadata fields ``None``) so nothing is dropped. Returns
    the entry, or ``None`` only when ``title`` is empty.
    """
    title = (title or "").strip()
    if not title:
        return None

    resolved = resolve(kind, title, creator)
    if resolved:
        seed = resolved
        key = resolved["canonical_key"]
    else:
        key = f"unresolved:{(kind or '').strip().lower()}:{_slug(title)}"
        seed = {
            "canonical_key": key,
            "kind": (kind or "").strip().lower(),
            "title": title,
            "year": None,
            "creator": creator or None,
            "poster": None,
            "rating": None,
            "overview": None,
            "external_url": None,
        }

    data = load_recs(path)
    entry = data.get(key)
    if entry is None:
        entry = {
            **seed,
            "sources": [],
            "count": 0,
            "first_seen": None,
            "status": None,
        }
    else:
        # Refresh metadata from the latest resolution, filling only non-null
        # fields so a later thinner result never erases known metadata.
        for field in _ENTRY_META_FIELDS:
            if seed.get(field) is not None:
                entry[field] = seed[field]

    if note_path and note_path not in entry["sources"]:
        entry["sources"].append(note_path)
    entry["count"] = len(entry["sources"])

    data[key] = entry
    save_recs(data, path)
    return entry


def set_status(key, status, path=RECS_PATH) -> dict:
    """Set the watch/read status of an entry. Raises ``ValueError`` on an
    invalid status and ``KeyError`` when the entry does not exist."""
    if status not in VALID_STATUS:
        raise ValueError(
            f"invalid status: {status!r} (allowed: {sorted(s for s in VALID_STATUS if s)})"
        )
    data = load_recs(path)
    entry = data.get(key)
    if entry is None:
        raise KeyError(key)
    entry["status"] = status
    data[key] = entry
    save_recs(data, path)
    return entry


def entries(kind: str | None = None, path=RECS_PATH) -> list[dict]:
    """All stored entries, optionally filtered by ``kind``, sorted by ``count``
    descending then title ascending."""
    data = load_recs(path)
    items = list(data.values())
    if kind is not None:
        items = [e for e in items if e.get("kind") == kind]
    items.sort(key=lambda e: (-e.get("count", 0), (e.get("title") or "").lower()))
    return items


# --------------------------------------------------------------------------- #
# Extraction (focused Haiku pass)
# --------------------------------------------------------------------------- #


class _ExtractionResult(BaseModel):
    """Wrapper so the extractor schema has an object root (run_structured
    requires it) while reusing the canonical Recommendation shape."""

    recommendations: list[Recommendation] = []


_EXTRACT_SCHEMA = _ExtractionResult.model_json_schema()

_EXTRACT_SYSTEM = """\
You extract media recommendations from a note. Return a JSON object matching the \
provided schema: a "recommendations" list. Each item is a specific movie, TV show, \
anime, book, or manga that the text recommends or discusses substantively enough that \
someone might want to watch or read it. For each: kind (movie | show | anime | book | \
manga), title (as actually named — do not invent or translate), creator \
(director/author/studio if stated, else null), and reason (why it came up, if stated, \
else null). Distinguish anime from live-action show, and manga from book. Return an \
empty list when the note recommends nothing — this is the common case, do not force \
entries.\
"""


def extract_recommendations(text: str) -> list[dict]:
    """Extract recommendations from arbitrary note text via one Haiku pass.

    Returns a list of ``{kind, title, creator, reason}`` dicts (empty when the
    text names none, or is blank).
    """
    text = (text or "").strip()
    if not text:
        return []
    data = run_structured(_EXTRACT_SYSTEM, text, _EXTRACT_SCHEMA)
    result = _ExtractionResult.model_validate(data)
    return [r.model_dump() for r in result.recommendations]
