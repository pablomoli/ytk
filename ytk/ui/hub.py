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


def start_ingest(indices: list[int], bucket: str, thought: str) -> int:
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

    threading.Thread(target=_worker, args=(items, bucket, thought), daemon=True).start()
    return len(items)


def _worker(items: list[reels.ReelItem], bucket: str, thought: str) -> None:
    started = time.time()
    for idx, item in enumerate(items):
        with _LOCK:
            _JOB["current"] = item.url
        try:
            INGEST(item.url)
            note = find_note_by_url(item.url, since=started - 5)
            if note and (bucket or thought.strip()):
                vault.annotate_note(note, bucket, thought)
                vault.append_daily_digest(note, bucket, thought)
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


def fresh_notes(n: int = 30) -> list[dict]:
    """The most recently written source notes, newest first, with thumbnails."""
    brain = vault._get_brain_path()
    sources = brain / "sources"
    if not sources.exists():
        return []
    files = sorted(
        sources.glob("**/*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:n]

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
                "thumbnail": thumb,
            }
        )
    return out
