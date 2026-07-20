"""Channels surface — the creators you consume, aggregated from note metadata.

Unlike the movie/book rec surfaces, this needs no extraction and no external API:
every note already stamps its creator, just under a source-specific key. This
module normalizes that key, aggregates notes into per-channel entries, and
persists a small loved/muted affinity flag that feeds auto-ingest priority.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

AFFINITY_PATH = Path.home() / ".ytk" / "channels.json"

# The frontmatter key that names the creator, per source. Reddit's channel is
# the subreddit (not the individual poster); web/pinterest fall back to domain.
_CREATOR_FIELD = {
    "youtube": "uploader",
    "tiktok": "username",
    "instagram": "username",
    "reddit": "subreddit",
}

# The user's own captures are not external creators.
_EXCLUDED_SOURCES = {"memo", "imessage", "journal", "voice"}

_VALID_STATUS = {"loved", "muted", None}


def channel_of(meta: dict, source: str, url: str | None = None) -> str | None:
    """Resolve the display name of a note's creator, or None if it has none.

    Source-aware: reddit -> subreddit, youtube -> uploader, tiktok/instagram ->
    username, everything else -> author, then the URL domain as a last resort.
    """
    source = (source or "").lower()
    if source in _EXCLUDED_SOURCES:
        return None
    field = _CREATOR_FIELD.get(source)
    if field:
        val = (meta.get(field) or "").strip()
        if val:
            return val
    author = (meta.get("author") or "").strip()
    # Reddit's `author` is the poster, not the channel — never fall back to it.
    if author and source != "reddit":
        return author
    u = url or meta.get("url")
    if u:
        host = urlparse(u).netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        if host:
            return host
    return None


def channel_key(source: str, channel: str) -> str:
    """Stable dedupe key for a channel, case- and prefix-insensitive."""
    return f"{(source or '').lower()}:{channel.strip().lower()}"


def aggregate(cards: list[dict]) -> list[dict]:
    """Group note cards into per-channel entries.

    Each card needs `source`, `channel`, and optionally `tags`, `title`, `path`,
    `added`/`date`. Cards without a channel are skipped. Returns entries sorted
    by note count, descending.
    """
    groups: dict[str, dict] = {}
    for card in cards:
        channel = card.get("channel")
        source = card.get("source") or ""
        # Memos re-set `channel` downstream of channel_of, so exclude the user's
        # own captures here by source, not just by a null channel.
        if not channel or source.lower() in _EXCLUDED_SOURCES:
            continue
        key = channel_key(source, channel)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "key": key,
                "source": source,
                "channel": channel,
                "count": 0,
                "last_seen": "",
                "_tags": Counter(),
                "notes": [],
            }
        g["count"] += 1
        seen = card.get("added") or card.get("date") or ""
        if seen > g["last_seen"]:
            g["last_seen"] = seen
        for t in card.get("tags") or []:
            g["_tags"][t] += 1
        if len(g["notes"]) < 50:
            g["notes"].append({"title": card.get("title") or card.get("stem"), "path": card.get("path")})

    entries = []
    for g in groups.values():
        top_tags = [t for t, _ in g.pop("_tags").most_common(3)]
        g["top_tags"] = top_tags
        entries.append(g)
    entries.sort(key=lambda e: e["count"], reverse=True)
    return entries


def load_affinity(path: Path = AFFINITY_PATH) -> dict:
    """Per-channel affinity flags: {key: {"status": "loved"|"muted"}}."""
    try:
        if path.exists() and path.stat().st_size > 0:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_affinity(affinity: dict, path: Path = AFFINITY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(affinity, indent=2), encoding="utf-8")
    tmp.replace(path)


def set_status(key: str, status: str | None, path: Path = AFFINITY_PATH) -> dict:
    """Set (or clear, when status is None/falsey) a channel's affinity flag."""
    if status not in _VALID_STATUS:
        raise ValueError(f"Invalid status: {status!r}")
    affinity = load_affinity(path)
    if status:
        affinity[key] = {"status": status}
    else:
        affinity.pop(key, None)
    save_affinity(affinity, path)
    return affinity


def merge_affinity(entries: list[dict], affinity: dict) -> list[dict]:
    """Attach status to entries and sort loved-first, then by count."""
    for e in entries:
        e["status"] = (affinity.get(e["key"]) or {}).get("status")
    rank = {"loved": 0, None: 1, "muted": 2}
    entries.sort(key=lambda e: (rank.get(e["status"], 1), -e["count"]))
    return entries


def loved_channels(affinity: dict | None = None) -> set[str]:
    """Channel keys flagged loved — consumed by auto-ingest priority."""
    affinity = affinity if affinity is not None else load_affinity()
    return {k for k, v in affinity.items() if (v or {}).get("status") == "loved"}


def muted_channels(affinity: dict | None = None) -> set[str]:
    affinity = affinity if affinity is not None else load_affinity()
    return {k for k, v in affinity.items() if (v or {}).get("status") == "muted"}
