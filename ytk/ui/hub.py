"""Ingest-hub backend: queue operations, background ingest job, fresh feed.

The hub shares the pending-queue state file with the `ytk reels` CLI. Ingestion
reuses the `ytk add` pipeline in-process; after each success the note is located
by its frontmatter url, annotated with the user's bucket and thought, logged to
the daily digest, and removed from the queue.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from ytk import reels, vault

STATE_PATH = reels.STATE_PATH
PACING_SECONDS = 3.0

_LOCK = threading.Lock()
_JOB: dict = {
    "running": False,
    "total": 0,
    "done": 0,
    "current": None,
    "failures": [],
    "annotated": 0,
}


class HubBusy(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Queue operations
# ---------------------------------------------------------------------------


def queue_items() -> list[reels.ReelItem]:
    return reels.load_state(STATE_PATH).pending


def queue_add(urls: list[str]) -> int:
    with _LOCK:
        state = reels.load_state(STATE_PATH)
        added = reels.add_urls(state, urls)
        if added:
            reels.save_state(state, STATE_PATH)
    return len(added)


def _remove_from_queue(url: str) -> None:
    with _LOCK:
        state = reels.load_state(STATE_PATH)
        state.pending = [i for i in state.pending if i.url != url]
        reels.save_state(state, STATE_PATH)


# ---------------------------------------------------------------------------
# Source pulls: Instagram DM thread + YouTube ytk playlist
# ---------------------------------------------------------------------------


def _ig_pull(state: reels.ReelsState) -> int:
    """Drain new Instagram DM links into the state's pending queue in place."""
    import os

    sessionid = os.environ.get("INSTAGRAM_SESSIONID", "")
    client = reels.get_client(sessionid)
    peer = os.environ.get("INSTAGRAM_PEER") or None
    refreshed = reels.refresh(client, state, peer=peer)
    added = len(refreshed.pending) - len(state.pending)
    state.pending = refreshed.pending
    state.thread_id = refreshed.thread_id
    state.last_seen_message_id = refreshed.last_seen_message_id
    return added


def _yt_fetch() -> list[dict]:
    from ytk.scheduler import authenticate, fetch_playlist_videos

    return fetch_playlist_videos(authenticate())


def _yt_is_processed(video_id: str) -> bool:
    from ytk import db

    return db.is_processed(video_id)


def _pin_fetch() -> list[dict]:
    """Fetch pins from the configured Pinterest board RSS feeds."""
    import urllib.request
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime

    from ytk.config import load_config

    pins: list[dict] = []
    for feed_url in load_config().hub.pinterest_feeds:
        req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            root = ET.fromstring(resp.read())
        for item in root.iter("item"):
            link = (item.findtext("link") or "").strip()
            if not link:
                continue
            desc = item.findtext("description") or ""
            img = re.search(r'<img src="([^"]+)"', desc)
            date = None
            pub = item.findtext("pubDate")
            if pub:
                try:
                    date = parsedate_to_datetime(pub).date().isoformat()
                except Exception:
                    date = None
            pins.append(
                {
                    "url": link,
                    "title": (item.findtext("title") or "").strip() or None,
                    "image": img.group(1) if img else None,
                    "date": date,
                }
            )
    return pins


# test seams
IG_PULL = _ig_pull
YT_FETCH = _yt_fetch
YT_IS_PROCESSED = _yt_is_processed
PIN_FETCH = _pin_fetch


PULL_TTL_SECONDS = 15 * 60


def refresh_sources(force: bool = False) -> dict:
    """Pull new items from all discovery sources into the queue.

    Auto-pull is throttled: within PULL_TTL_SECONDS of the last pull the call
    is a no-op (a source hit on every page load is bot-shaped traffic).
    Each source fails independently; errors are reported, not raised.
    """
    result: dict = {
        "instagram": 0, "youtube": 0, "pinterest": 0,
        "errors": [], "skipped": False,
    }
    with _LOCK:
        state = reels.load_state(STATE_PATH)

        if (
            not force
            and state.last_pull_at is not None
            and time.time() - state.last_pull_at < PULL_TTL_SECONDS
        ):
            result["skipped"] = True
            return result

        try:
            result["instagram"] = IG_PULL(state)
        except Exception as exc:
            result["errors"].append(f"instagram: {exc}")

        try:
            known = {i.url for i in state.pending}
            for v in YT_FETCH():
                url = f"https://www.youtube.com/watch?v={v['video_id']}"
                if url in known or YT_IS_PROCESSED(v["video_id"]):
                    continue
                state.pending.append(
                    reels.ReelItem(
                        url=url,
                        author=v.get("title") or None,
                        shared_at=(v.get("added_at") or "")[:10] or None,
                        preview_url=f"https://i.ytimg.com/vi/{v['video_id']}/hqdefault.jpg",
                        source="youtube",
                    )
                )
                result["youtube"] += 1
        except Exception as exc:
            result["errors"].append(f"youtube: {exc}")

        try:
            known = {i.url for i in state.pending}
            for pin in PIN_FETCH():
                if pin["url"] in known:
                    continue
                state.pending.append(
                    reels.ReelItem(
                        url=pin["url"],
                        author=pin.get("title"),
                        shared_at=pin.get("date"),
                        preview_url=pin.get("image"),
                        source="pinterest",
                    )
                )
                result["pinterest"] += 1
        except Exception as exc:
            result["errors"].append(f"pinterest: {exc}")

        state.last_pull_at = time.time()
        reels.save_state(state, STATE_PATH)
    return result


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def tag_list() -> list[str]:
    """Config-defined tags merged with UI-created ones, order preserved."""
    from ytk.config import load_config

    configured = load_config().hub.tags
    custom = reels.load_state(STATE_PATH).custom_tags
    return list(dict.fromkeys([*configured, *custom]))


def add_tag(name: str) -> list[str]:
    """Persist a new UI-created tag (normalized); returns the merged list."""
    normalized = vault._normalize_tag(name)
    if not normalized:
        raise ValueError("Tag name is empty.")
    with _LOCK:
        state = reels.load_state(STATE_PATH)
        if normalized not in state.custom_tags:
            state.custom_tags.append(normalized)
            reels.save_state(state, STATE_PATH)
    return tag_list()


# ---------------------------------------------------------------------------
# Ingest job
# ---------------------------------------------------------------------------


def ingest_via_cli(url: str) -> None:
    """Run the existing `ytk add` pipeline in-process for one URL."""
    from ytk.cli import cli as click_cli

    try:
        click_cli.main(args=["add", url], standalone_mode=False)
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise RuntimeError(f"add exited with code {exc.code}")


# test seams: stubbed in unit tests, real in production
INGEST = ingest_via_cli
REINDEX = vault.reindex_vault


def find_note_by_url(url: str, since: float) -> Path | None:
    """Locate the note a pipeline run just wrote by its frontmatter url."""
    sources = vault._get_brain_path() / "sources"
    if not sources.exists():
        return None
    for md in sources.glob("**/*.md"):
        if md.stat().st_mtime < since:
            continue
        head = md.read_text(encoding="utf-8")[:2000]
        if re.search(rf"^url:\s*{re.escape(url)}\s*$", head, re.MULTILINE):
            return md
    return None


def job_status() -> dict:
    with _LOCK:
        return dict(_JOB, failures=list(_JOB["failures"]))


def start_ingest(indices: list[int], tags: list[str], thought: str) -> int:
    """Kick off a background ingest of the given 1-based queue indices.

    Raises HubBusy if a job is already running, ValueError on bad indices.
    """
    with _LOCK:
        if _JOB["running"]:
            raise HubBusy("An ingest job is already running.")
        pending = reels.load_state(STATE_PATH).pending
        if not indices:
            raise ValueError("No items selected.")
        bad = [i for i in indices if i < 1 or i > len(pending)]
        if bad:
            raise ValueError(f"Selection out of range 1-{len(pending)}: {bad}")
        items = [pending[i - 1] for i in sorted(set(indices))]
        _JOB.update(
            running=True, total=len(items), done=0, current=None,
            failures=[], annotated=0,
        )

    threading.Thread(target=_worker, args=(items, tags, thought), daemon=True).start()
    return len(items)


def _worker(items: list[reels.ReelItem], tags: list[str], thought: str) -> None:
    started = time.time()
    for idx, item in enumerate(items):
        with _LOCK:
            _JOB["current"] = item.url
        try:
            INGEST(item.url)
            note = find_note_by_url(item.url, since=started - 5)
            if note and (tags or thought.strip()):
                vault.annotate_note(note, tags, thought)
                vault.append_daily_digest(note, tags, thought)
                with _LOCK:
                    _JOB["annotated"] += 1
            _remove_from_queue(item.url)
        except Exception as exc:
            with _LOCK:
                _JOB["failures"].append({"url": item.url, "error": str(exc)})
        with _LOCK:
            _JOB["done"] += 1
        if idx < len(items) - 1:
            time.sleep(PACING_SECONDS)

    try:
        REINDEX()
    except Exception:
        pass
    with _LOCK:
        _JOB["running"] = False
        _JOB["current"] = None


# ---------------------------------------------------------------------------
# Fresh feed
# ---------------------------------------------------------------------------

_FM_LINE = re.compile(r"^(url|title|type|date):\s*(.+)$", re.MULTILINE)


def _ingested_at(p: Path) -> float:
    """Best approximation of when a note entered the vault.

    mtime alone is unreliable: iCloud sync, reindexing, and wikilink edits all
    touch it. The earlier of creation time and mtime survives those.
    """
    st = p.stat()
    birth = getattr(st, "st_birthtime", st.st_mtime)
    return min(birth, st.st_mtime)


def fresh_notes(n: int = 30) -> list[dict]:
    """The most recently ingested source notes, newest first, with thumbnails."""
    brain = vault._get_brain_path()
    sources = brain / "sources"
    if not sources.exists():
        return []
    files = sorted(
        sources.glob("**/*.md"),
        key=_ingested_at,
        reverse=True,
    )[:n]

    from datetime import date

    out = []
    for md in files:
        text = md.read_text(encoding="utf-8")[:3000]
        meta = {k: v.strip() for k, v in _FM_LINE.findall(text)}
        thumb = None
        m = re.search(r"^image_paths:\n\s+- (.+)$", text, re.MULTILINE)
        if m and (brain / m.group(1).strip()).exists():
            thumb = m.group(1).strip()
        out.append(
            {
                "path": str(md.relative_to(brain.parent)),
                "stem": md.stem,
                "title": meta.get("title", md.stem),
                "url": meta.get("url"),
                "source": meta.get("type", md.parent.name),
                "date": meta.get("date"),
                "added": date.fromtimestamp(_ingested_at(md)).isoformat(),
                "thumbnail": thumb,
            }
        )
    return out
