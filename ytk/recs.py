# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
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


# Genre-id -> name maps, one API call per media type per process. TMDb search
# results carry only genre_ids; the names are what the shelf UI groups by.
_TMDB_GENRE_CACHE: dict[str, dict[int, str]] = {}


def _tmdb_genres(media: str, genre_ids: list[int] | None) -> list[str]:
    if not genre_ids:
        return []
    if media not in _TMDB_GENRE_CACHE:
        data = _tmdb_request(f"/genre/{media}/list")
        names = {g["id"]: g["name"] for g in (data or {}).get("genres", []) if g.get("name")}
        if not names:
            return []  # transient failure: do not cache, retry next call
        _TMDB_GENRE_CACHE[media] = names
    names = _TMDB_GENRE_CACHE[media]
    return [names[i] for i in genre_ids if i in names]


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
        "genres": _tmdb_genres("movie", m.get("genre_ids")),
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
        "genres": _tmdb_genres("tv", m.get("genre_ids")),
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
    genres
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
    genres
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
        "genres": m.get("genres") or [],
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
        "genres": m.get("genres") or [],
        "overview": None,
        "external_url": m.get("siteUrl"),
    }


# Haiku extracts creators as written in the note: "Goodfellow et al.",
# "Susskind and Hrabovsky", "edited by James M. Robinson". Neither search API
# matches those as an author; the first surname-bearing chunk does.
_AUTHOR_SPLIT_RE = re.compile(
    r"\s+and\s+|\s*&\s*|\s*,\s*|\s+et\s+al\.?|\s*\bedited by\b\s*|\s*\btranslated by\b\s*",
    re.IGNORECASE,
)


def _first_author(creator: str | None) -> str | None:
    if not creator:
        return None
    for chunk in _AUTHOR_SPLIT_RE.split(creator):
        chunk = (chunk or "").strip()
        if chunk:
            return chunk
    return None


# "Funny Games (1997)" — the year belongs in the search's year param, where it
# disambiguates, not in the title, where it guarantees a miss.
_TITLE_YEAR_RE = re.compile(r"^(.*?)\s*\((\d{4})\)\s*$")


def _split_title_year(title: str, year: int | None) -> tuple[str, int | None]:
    m = _TITLE_YEAR_RE.match(title)
    if m:
        return m.group(1).strip() or title, year or int(m.group(2))
    return title, year


def _resolve_book(title: str, creator: str | None) -> dict | None:
    """Google Books first (categories for the shelf UI, reliable covers),
    Open Library as fallback. Both keyless at this volume."""
    author = _first_author(creator)
    return _resolve_book_google(title, author) or _resolve_book_openlibrary(title, author)


def _resolve_book_google(title: str, creator: str | None) -> dict | None:
    q = f'intitle:"{title}"'
    if creator:
        q += f' inauthor:"{creator}"'
    params: dict[str, str | int] = {"q": q, "maxResults": 1, "printType": "books"}
    # Keyless calls share an anonymous per-IP daily quota that is often already
    # exhausted (observed 429 on first call); a key makes this path reliable.
    key = os.environ.get("GOOGLE_BOOKS_API_KEY")
    if key:
        params["key"] = key
    url = "https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(params)
    data = _http_get(url)
    items = (data or {}).get("items") or []
    if not items:
        return None
    item = items[0]
    info = item.get("volumeInfo") or {}
    isbn13 = next(
        (
            i.get("identifier")
            for i in info.get("industryIdentifiers", [])
            if i.get("type") == "ISBN_13"
        ),
        None,
    )
    # ISBN keys join with Open Library resolutions of the same book, so a
    # fallback-resolved entry upgrades in place instead of duplicating.
    canonical_key = f"isbn:{isbn13}" if isbn13 else f"gbooks:{item.get('id')}"
    thumb = (info.get("imageLinks") or {}).get("thumbnail")
    if thumb:
        thumb = thumb.replace("http://", "https://")
    authors = info.get("authors") or []
    # Categories arrive as paths ("Fiction / Science Fiction / General"); the
    # shelf name is the most specific segment that is not the "General"
    # catch-all, deduped case-insensitively across categories.
    genres: list[str] = []
    for cat in info.get("categories") or []:
        segments = [s.strip() for s in cat.split("/")]
        leaf = next((s for s in reversed(segments) if s and s.lower() != "general"), None)
        if leaf and leaf.lower() not in {g.lower() for g in genres}:
            genres.append(leaf)
    return {
        "canonical_key": canonical_key,
        "kind": "book",
        "title": info.get("title") or title,
        "year": _year_prefix(info.get("publishedDate")),
        "creator": authors[0] if authors else (creator or None),
        "poster": thumb,
        "rating": info.get("averageRating"),
        "genres": genres,
        "overview": info.get("description") or None,
        "external_url": info.get("canonicalVolumeLink") or None,
    }


# Open Library subjects are folksonomy noise ("Protected DAISY", "Reading
# Level-Grade 11"); only spine-label shelves pass through. Contains-matched,
# lowercased, first hit per shelf wins.
_OL_SUBJECT_SHELVES: tuple[tuple[str, str], ...] = (
    ("science fiction", "Science Fiction"),
    ("fantasy", "Fantasy"),
    ("horror", "Horror"),
    ("thriller", "Thriller"),
    ("mystery", "Mystery"),
    ("detective", "Mystery"),
    ("romance", "Romance"),
    ("historical fiction", "Historical Fiction"),
    ("biography", "Biography"),
    ("autobiography", "Biography"),
    ("memoir", "Biography"),
    ("poetry", "Poetry"),
    ("philosophy", "Philosophy"),
    ("psychology", "Psychology"),
    ("self-help", "Self-Help"),
    ("self-improvement", "Self-Help"),
    ("business", "Business"),
    ("economics", "Business"),
    ("history", "History"),
    ("science", "Science"),
    ("mathematics", "Science"),
    ("computer", "Technology"),
    ("programming", "Technology"),
    ("design", "Design"),
    ("art", "Art"),
    ("graphic novel", "Comics"),
    ("comics", "Comics"),
    ("fiction", "Fiction"),  # last: catch-all so genre fiction lands above
)


def _ol_genres(subjects: list[str] | None) -> list[str]:
    # A matched subject is consumed so a broad needle later in the table
    # cannot re-match it ("science fiction" must not also yield "Science").
    remaining = [s.lower() for s in subjects or []]
    genres: list[str] = []
    for needle, shelf in _OL_SUBJECT_SHELVES:
        hits = any(needle in s for s in remaining)
        if not hits:
            continue
        if shelf not in genres:
            genres.append(shelf)
        remaining = [s for s in remaining if needle not in s]
    return genres[:3]


_OL_FIELDS = "key,title,author_name,cover_i,first_publish_year,isbn,subject"


def _resolve_book_openlibrary(title: str, creator: str | None) -> dict | None:
    params: dict[str, str | int] = {"title": title, "limit": 1, "fields": _OL_FIELDS}
    if creator:
        params["author"] = creator
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
    data = _http_get(url)
    docs = (data or {}).get("docs") or []
    if not docs:
        # OL's fielded title=&author= search intermittently returns zero for
        # titles its general q= search finds (observed 2026-07-26, even for
        # exact author names). The fuzzy path is the fallback, not the
        # default, because it more readily returns the wrong edition.
        q = f"{title} {creator}" if creator else title
        url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(
            {"q": q, "limit": 1, "fields": _OL_FIELDS}
        )
        data = _http_get(url)
        docs = (data or {}).get("docs") or []
    if not docs:
        return None
    d = docs[0]
    # The q= path can surface a work under its original-language title
    # (Kafka on the Shore -> 海辺のカフカ); keep the title we searched for
    # when OL's is mostly non-ASCII, since the vault note named it in English.
    ol_title = d.get("title") or title
    if sum(c.isascii() for c in ol_title) < 0.8 * max(len(ol_title), 1):
        d = {**d, "title": title}
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
        "genres": _ol_genres(d.get("subject")),
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
            return _resolve_movie(*_split_title_year(title, year))
        if kind == "show":
            return _resolve_show(*_split_title_year(title, year))
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
    "genres",
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
            "genres": None,
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


def refresh(path=RECS_PATH, only_unresolved: bool = False) -> dict:
    """Re-resolve every stored entry against the live APIs (#21).

    Exists because resolution failures are otherwise permanent: ``record``
    only retries a title when a new note mentions it again, so entries
    recorded before credentials existed (59 of 92 movies at the time this
    was written) stayed ``unresolved:*`` stubs forever. Also backfills
    fields added after an entry was stored (``genres``).

    An ``unresolved:*`` entry that now resolves migrates to its canonical
    key; if that key already exists the two merge (union of sources,
    earliest ``first_seen``, an existing status is never overwritten).
    User state (``status``, ``sources``, ``first_seen``) is always
    preserved. Returns a summary dict.
    """
    data = load_recs(path)
    summary = {"total": len(data), "resolved": 0, "still_unresolved": 0, "merged": 0}
    out: dict[str, dict] = {}

    def _fold(key: str, entry: dict) -> None:
        existing = out.get(key)
        if existing is None:
            out[key] = entry
            return
        summary["merged"] += 1
        for src in entry.get("sources", []):
            if src not in existing["sources"]:
                existing["sources"].append(src)
        existing["count"] = len(existing["sources"])
        firsts = [f for f in (existing.get("first_seen"), entry.get("first_seen")) if f]
        existing["first_seen"] = min(firsts) if firsts else None
        existing["status"] = existing.get("status") or entry.get("status")
        for field in _ENTRY_META_FIELDS:
            if existing.get(field) is None and entry.get(field) is not None:
                existing[field] = entry[field]

    for key, entry in data.items():
        was_unresolved = key.startswith("unresolved:")
        if only_unresolved and not was_unresolved:
            _fold(key, entry)
            continue
        resolved = resolve(
            entry.get("kind"), entry.get("title"), entry.get("creator"), entry.get("year")
        )
        if resolved is None:
            if was_unresolved:
                summary["still_unresolved"] += 1
            _fold(key, entry)
            continue
        summary["resolved"] += 1
        merged = dict(entry)
        for field in _ENTRY_META_FIELDS:
            if resolved.get(field) is not None:
                merged[field] = resolved[field]
        _fold(merged["canonical_key"], merged)

    save_recs(out, path)
    summary["total_after"] = len(out)
    return summary


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
