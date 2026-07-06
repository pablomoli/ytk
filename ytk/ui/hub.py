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

from ytk import directives, reels, vault
from ytk.config import load_config
from ytk.memo import (
    AUDIO_DIR as MEMO_AUDIO_DIR,
    ensure_wav as memo_ensure_wav,
    execute_route as memo_execute,
    finalize_memo_note as memo_finalize,
    index_memo_note as memo_index,
    notify as memo_notify,
    route as memo_route,
    transcribe as memo_transcribe,
    write_memo_note as memo_write_note,
)

STATE_PATH = reels.STATE_PATH
PACING_SECONDS = 3.0

_LOCK = threading.Lock()
_QUEUE: list = []  # (ReelItem, tags, thought) triples awaiting the drain worker
_JOB: dict = {
    "running": False,
    "total": 0,
    "done": 0,
    "current": None,
    "queued": [],
    "failures": [],
    "annotated": 0,
    "linked": [],
}


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


def _im_fetch() -> list:
    """Read the self-chat straight from chat.db and sessionize closed sessions.

    Direct sqlite read (no subprocess), bounded to a recent window so each pull
    stays cheap; the persistent imessage_seen set prevents re-adding older ones.
    """
    from datetime import datetime

    from ytk import imessage

    now = datetime.now()
    thread = imessage.read_recent(days=3, now=now)
    if not thread.messages:
        return []
    gap = load_config().hub.imessage_gap_minutes
    return imessage.sessionize(thread, gap_minutes=gap, now=now)


def ingest_imessage_item(item: reels.ReelItem, note: str = "") -> Path | None:
    """Ingest one iMessage session through the voice-memo pipeline.

    Typed self-notes are memos, just not spoken: the raw text is the artifact,
    saved verbatim before routing, then classified (memory/action/thought) and
    routed like a transcript. No thesis/summary enrichment — a scratchbook note
    doesn't need an essay written about it.
    """
    from ytk.imessage import split_urls

    # A note paired with a link: fetch the linked source and let the prose ride
    # along as the user-note that steers its enrichment (reuses `ytk add --note`).
    # The enriched source note IS the pairing, so no separate memo note.
    urls, prose = split_urls(item.text or "")
    if urls:
        steer = "\n\n".join(t for t in (prose, note) if t and t.strip())
        found: Path | None = None
        for u in urls:
            started = time.time()
            INGEST(u, steer)
            found = find_note_by_url(u, since=started - 5) or found
        return found

    transcript = (item.text or "").strip()
    if note.strip():
        transcript += f"\n\n[inbox note] {note.strip()}"
    if not transcript:
        return None
    cfg = load_config()
    path = memo_write_note(transcript, None, source="imessage")
    result = memo_route(transcript, repos=cfg.github_repos or [])
    routed = memo_execute(result, transcript, cfg.github_repos or [])
    memo_finalize(path, result.kind, routed)
    memo_index(path, transcript, result.kind)
    return path


# test seams
IG_PULL = _ig_pull
YT_FETCH = _yt_fetch
YT_IS_PROCESSED = _yt_is_processed
PIN_FETCH = _pin_fetch
IM_FETCH = _im_fetch
INGEST_TEXT = ingest_imessage_item


_READY = {"search": False}


def search_ready() -> bool:
    """Whether the embedding model + chroma are warm (first search won't stall)."""
    return _READY["search"]


def warm_search() -> bool:
    """Preload the embedding model and init chroma in the background on startup.

    The search lag isn't the query — it's the one-time model load. Exercising the
    real search path here moves that cost off the user's first search, and doing
    it once single-threaded also avoids the chroma init race two concurrent
    first-requests would hit. Returns False if already warm/warming.
    """
    if _READY["search"]:
        return False

    def _run() -> None:
        try:
            from ytk import visual
            from ytk.store import pending_visual_similar, visual_similar

            emb = visual.embed_text("warm up the index")
            for fn in (pending_visual_similar, visual_similar):
                try:
                    fn(embedding=emb, n=1)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            _READY["search"] = True  # unblock the UI even if warming errored

    threading.Thread(target=_run, daemon=True).start()
    return True


def imessage_warm() -> list[dict]:
    """Still-warm self-note sessions: captured but not yet closed into a node.

    These are notes you're likely still adding to — held back by the silence
    window. Surfacing them gives immediate feedback that a note landed, instead
    of the inbox looking empty until the gap elapses. Read-only; queues nothing.
    """
    from datetime import datetime

    from ytk import imessage

    now = datetime.now()
    thread = imessage.read_recent(days=3, now=now)
    if not thread.messages:
        return []
    gap = load_config().hub.imessage_gap_minutes
    closed = {s.note_id for s in imessage.sessionize(thread, gap_minutes=gap, now=now)}
    seen = set(reels.load_state(STATE_PATH).imessage_seen)
    out: list[dict] = []
    for s in imessage.sessionize(thread, gap_minutes=gap, now=None):
        if s.note_id in closed or s.note_id in seen:
            continue
        mins_left = max(0.0, gap - (now - s.end).total_seconds() / 60)
        out.append({
            "note_id": s.note_id,
            "count": len(s.messages),
            "text": "\n\n".join(m.text for m in s.messages),
            "minutes_left": round(mins_left),
        })
    return out


def ingested_urls() -> set[str]:
    """URLs that already have a vault note — the 'already ingested' set.

    Used to prune the pending queue: a full-thread re-pull (e.g. after a state
    rebuild) re-discovers items that were ingested long ago; anything whose url
    is already note-backed has no business waiting in the inbox again.
    """
    sources = vault._get_brain_path() / "sources"
    if not sources.exists():
        return set()
    urls: set[str] = set()
    for md in sources.glob("**/*.md"):
        try:
            m = re.search(r"^url:\s*(\S+)\s*$", md.read_text(encoding="utf-8")[:2000], re.MULTILINE)
        except OSError:
            continue
        if m:
            urls.add(m.group(1))
    return urls


INGESTED_URLS = ingested_urls  # test seam


_watcher_started = False


def start_imessage_watcher(interval: float = 3.0, debounce: float = 8.0) -> bool:
    """Watch chat.db for writes and pull the self-chat within seconds.

    macOS exposes no message-insertion hook, so this polls the SQLite
    write-ahead-log's mtime (cheap, no DB open) and, on change, runs a targeted
    imessage-only refresh. Debounced so a burst of messages triggers at most one
    pull per window — and since sessionize withholds still-warm sessions anyway,
    normal notes still wait out the gap; only "$$" notes ingest near-instantly.
    Returns False if already running or IMESSAGE_SELF is unset.
    """
    global _watcher_started
    import os

    if _watcher_started or not os.environ.get("IMESSAGE_SELF"):
        return False
    _watcher_started = True

    def _run() -> None:
        from ytk.imessage import chatdb_path

        db = chatdb_path()
        watched = [db, db.parent / (db.name + "-wal")]
        last_sig = None
        last_pull = 0.0
        pending = False
        while True:
            try:
                sig = tuple(p.stat().st_mtime if p.exists() else 0 for p in watched)
                if sig != last_sig:
                    last_sig = sig
                    pending = True
                if pending and time.time() - last_pull >= debounce:
                    pending = False
                    last_pull = time.time()
                    refresh_sources(force=True, only={"imessage"})
            except Exception:
                pass
            time.sleep(interval)

    threading.Thread(target=_run, daemon=True).start()
    return True


def _pull_due(state: reels.ReelsState, source: str, cadence_minutes: dict, force: bool) -> bool:
    """Whether a source's per-source throttle window has elapsed."""
    if force:
        return True
    last = state.last_pulls.get(source, state.last_pull_at)
    if last is None:
        return True
    return time.time() - last >= cadence_minutes.get(source, 15) * 60


def refresh_sources(force: bool = False, only: set | None = None) -> dict:
    """Pull new items from all discovery sources into the queue.

    Auto-pull is throttled per source by hub.cadence_minutes (a source hit on
    every page load is bot-shaped traffic); `skipped` is True when every
    source was inside its window. Each source fails independently; errors are
    reported, not raised. Pass `only={"imessage"}` to pull just those sources
    (used by the chat.db watcher for cheap, targeted refreshes).
    """
    from ytk.config import load_config

    cadence = load_config().hub.cadence_minutes
    result: dict = {
        "instagram": 0, "youtube": 0, "pinterest": 0, "imessage": 0,
        "errors": [], "skipped": False, "skipped_sources": [],
    }
    auto_ingest_ids: list[str] = []
    with _LOCK:
        state = reels.load_state(STATE_PATH)
        now = time.time()

        due = {
            s: (only is None or s in only) and _pull_due(state, s, cadence, force)
            for s in ("instagram", "youtube", "pinterest", "imessage")
        }
        if not any(due.values()):
            result["skipped"] = True
            result["skipped_sources"] = list(due)
            return result
        result["skipped_sources"] = [s for s, d in due.items() if not d]

        if due["instagram"]:
            try:
                result["instagram"] = IG_PULL(state)
                state.last_pulls["instagram"] = now
            except Exception as exc:
                result["errors"].append(f"instagram: {exc}")

        if due["youtube"]:
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
                state.last_pulls["youtube"] = now
            except Exception as exc:
                result["errors"].append(f"youtube: {exc}")

        if due["pinterest"]:
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
                state.last_pulls["pinterest"] = now
            except Exception as exc:
                result["errors"].append(f"pinterest: {exc}")

        if due["imessage"]:
            try:
                from ytk.imessage import split_urls

                seen = set(state.imessage_seen)
                known = {i.url for i in state.pending}
                for s in IM_FETCH():
                    if s.note_id in seen or s.note_id in known:
                        continue
                    state.imessage_seen.append(s.note_id)

                    # A link paired with prose is a deliberate note-plus-source
                    # pairing: keep them together, link embedded in the text. A
                    # bare link on its own reuses the normal fetch pipeline
                    # (classified by url), same as a pasted or IG-shared link.
                    full = "\n\n".join(m.text for m in s.messages)
                    urls, prose = split_urls(full)
                    if prose:
                        state.pending.append(
                            reels.ReelItem(
                                url=s.note_id,
                                author=s.date,
                                shared_at=s.start.strftime("%Y-%m-%d"),
                                source="imessage",
                                text=full,
                            )
                        )
                        result["imessage"] += 1
                        if s.override:
                            auto_ingest_ids.append(s.note_id)
                    else:
                        for u in urls:
                            if u in known:
                                continue
                            known.add(u)
                            state.pending.append(
                                reels.ReelItem(
                                    url=u,
                                    shared_at=s.start.strftime("%Y-%m-%d"),
                                    source=reels.classify_url(u),
                                )
                            )
                            result["imessage"] += 1
                            if s.override:
                                auto_ingest_ids.append(u)
                state.last_pulls["imessage"] = now
            except Exception as exc:
                result["errors"].append(f"imessage: {exc}")

        # prune anything the vault already has a note for (re-pulled duplicates)
        try:
            done = INGESTED_URLS()
            before = len(state.pending)
            state.pending = [i for i in state.pending if i.url not in done]
            result["dropped_ingested"] = before - len(state.pending)
        except Exception:
            result["dropped_ingested"] = 0

        state.last_pull_at = now
        reels.save_state(state, STATE_PATH)

    # $$-marked sessions bypass the inbox pick — ingest them now. Done outside
    # the lock: enrichment is slow, and start_ingest re-acquires the lock.
    if auto_ingest_ids:
        try:
            start_ingest(auto_ingest_ids, tags=[], thought="")
        except Exception as exc:
            result["errors"].append(f"imessage-autoingest: {exc}")
    return result


# ---------------------------------------------------------------------------
# Cover cache: Instagram's signed CDN slow-walks hotlinking and defeats the
# browser cache (unique query strings, expiring signatures). Download each
# cover once, keyed by the stable item URL, and serve the local copy.
# ---------------------------------------------------------------------------

COVERS_DIR = Path.home() / ".ytk" / "covers"


def _download_cover(preview_url: str, dest: Path) -> None:
    import urllib.request

    req = urllib.request.Request(preview_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    dest.write_bytes(data)


DOWNLOAD_COVER = _download_cover


def cover_for(item_url: str) -> Path | None:
    """Local cover path for a queue item, downloading on first request."""
    import hashlib

    key = hashlib.sha1(item_url.encode()).hexdigest()[:20] + ".jpg"
    dest = COVERS_DIR / key
    if dest.exists():
        return dest

    item = next(
        (i for i in queue_items() if i.url == item_url and i.preview_url), None
    )
    if item is None:
        return None
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        DOWNLOAD_COVER(item.preview_url, dest)
    except Exception:
        dest.unlink(missing_ok=True)
        return None
    return dest if dest.exists() else None


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


def ingest_via_cli(url: str, note: str = "") -> None:
    """Run the existing `ytk add` pipeline in-process for one URL.

    The user's thought rides along so enrichment can steer toward it.
    """
    from ytk.cli import cli as click_cli

    # hand-picked from the inbox = explicit intent: bypass filter prompts,
    # which would otherwise raise a blank click.Abort in this TTY-less worker
    args = ["add", url, "--force"]
    if note.strip():
        args += ["--note", note]
    try:
        click_cli.main(args=args, standalone_mode=False)
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
        return dict(_JOB, failures=list(_JOB["failures"]), linked=list(_JOB["linked"]))


_memo_job: dict = {"state": "idle", "detail": ""}
_tags_job: dict = {"state": "idle", "detail": "", "proposals": []}


def tags_merge_status() -> dict:
    with _LOCK:
        return dict(_tags_job, proposals=list(_tags_job["proposals"]))


def start_tag_proposals() -> bool:
    """Run the merge proposer in a background thread. False if one is running."""
    with _LOCK:
        if _tags_job["state"] == "running":
            return False
        _tags_job.update(state="running", detail="", proposals=[])

    def _run():
        from ytk import tags as ytags
        try:
            proposals = [g.model_dump() for g in ytags.propose_merges()]
            with _LOCK:
                _tags_job.update(state="done", proposals=proposals)
        except Exception as exc:
            with _LOCK:
                _tags_job.update(state="error", detail=str(exc))

    threading.Thread(target=_run, daemon=True).start()
    return True


def apply_tag_merges(mapping: dict[str, str]) -> dict:
    """Apply accepted merges and invalidate the enrichment vocabulary cache."""
    from ytk import enrich
    from ytk import tags as ytags

    summary = ytags.apply_merges(mapping)
    enrich._VOCAB_CACHE = None
    with _LOCK:
        _tags_job.update(state="idle", proposals=[])
    return summary


def memo_status() -> dict:
    with _LOCK:
        return dict(_memo_job)


def start_memo(audio_bytes: bytes, filename: str, text: str) -> bool:
    """Run the memo pipeline in a background thread. False if one is running."""
    with _LOCK:
        if _memo_job["state"] == "running":
            return False
        _memo_job.update(state="running", detail="")
    threading.Thread(
        target=_memo_worker, args=(audio_bytes, filename, text), daemon=True
    ).start()
    return True


def _memo_worker(audio_bytes: bytes, filename: str, text: str) -> None:
    from datetime import datetime

    try:
        cfg = load_config()
        audio_path = None
        if text:
            transcript = text
        else:
            MEMO_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            suffix = Path(filename).suffix or ".m4a"
            raw = MEMO_AUDIO_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}{suffix}"
            raw.write_bytes(audio_bytes)
            audio_path = memo_ensure_wav(raw)
            transcript = memo_transcribe(audio_path, cfg.whisper_model)
        if not transcript:
            _memo_job.update(state="error", detail="empty transcription")
            return

        note_path = memo_write_note(transcript, audio_path)
        try:
            result = memo_route(transcript, repos=cfg.github_repos or [])
        except Exception as exc:
            memo_finalize(note_path, "failed", [])
            memo_index(note_path, transcript, "failed")
            memo_notify("saved raw, routing failed", "failed", cfg.memo_notify or None)
            _memo_job.update(state="error", detail=f"saved raw, routing failed: {exc}")
            return

        routed = memo_execute(result, transcript, cfg.github_repos or [])
        memo_finalize(note_path, result.kind, routed)
        memo_index(note_path, transcript, result.kind)
        memo_notify(result.summary, result.kind, cfg.memo_notify or None)
        _memo_job.update(state="done", detail=f"{result.kind}: {result.summary}")
    except Exception as exc:
        _memo_job.update(state="error", detail=str(exc))


def start_ingest(urls: list[str], tags: list[str], thought: str) -> int:
    """Enqueue the given pending-queue URLs for background ingestion.

    Appends to the running job if one is active (each batch keeps its own
    tags/thought), otherwise starts a fresh drain worker. Returns the number
    of items actually enqueued (already queued or in-flight URLs are
    skipped). Raises ValueError on an empty or unknown selection.
    """
    with _LOCK:
        pending = {item.url: item for item in reels.load_state(STATE_PATH).pending}
        if not urls:
            raise ValueError("No items selected.")
        unknown = [u for u in urls if u not in pending]
        if unknown:
            raise ValueError(f"Not in the pending queue: {unknown}")
        active = {e[0].url for e in _QUEUE} | {_JOB["current"]}
        fresh = [u for u in dict.fromkeys(urls) if u not in active]
        _QUEUE.extend((pending[u], tags, thought) for u in fresh)
        if _JOB["running"]:
            _JOB["total"] += len(fresh)
        else:
            _JOB.update(
                running=True, total=len(fresh), done=0, current=None,
                failures=[], annotated=0, linked=[],
            )
            threading.Thread(target=_drain, daemon=True).start()
        _JOB["queued"] = [e[0].url for e in _QUEUE]
    return len(fresh)


def _drain() -> None:
    started = time.time()
    while True:
        with _LOCK:
            if not _QUEUE:
                # end the job under the lock so a concurrent start_ingest
                # either lands before this (we keep draining) or after
                # (it sees running=False and spawns a new worker)
                _JOB["running"] = False
                _JOB["current"] = None
                break
            item, tags, thought = _QUEUE.pop(0)
            _JOB["current"] = item.url
            _JOB["queued"] = [e[0].url for e in _QUEUE]
        try:
            if item.source == "imessage":
                note = INGEST_TEXT(item, thought)
            else:
                INGEST(item.url, thought)
                note = find_note_by_url(item.url, since=started - 5)
            if note and (tags or thought.strip()):
                vault.annotate_note(note, tags, thought)
                vault.append_daily_digest(note, tags, thought)
                applied = directives.process(note, thought)
                with _LOCK:
                    _JOB["annotated"] += 1
                    _JOB["linked"].extend(applied)
            _remove_from_queue(item.url)
        except Exception as exc:
            with _LOCK:
                _JOB["failures"].append({"url": item.url, "error": str(exc)})
        with _LOCK:
            _JOB["done"] += 1
            _JOB["current"] = None
            more = bool(_QUEUE)
        if more:
            time.sleep(PACING_SECONDS)

    try:
        REINDEX()
    except Exception:
        pass
    try:
        from ytk import visual

        visual.index_covers(skip_existing=True)
        visual.sync_pending_visual()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Fresh feed
# ---------------------------------------------------------------------------

_FM_LINE = re.compile(r"^(url|title|type|date|audio|route|captured|source):\s*(.+)$", re.MULTILINE)


def _ingested_at(p: Path) -> float:
    """Best approximation of when a note entered the vault.

    mtime alone is unreliable: iCloud sync, reindexing, and wikilink edits all
    touch it. The earlier of creation time and mtime survives those.
    """
    st = p.stat()
    birth = getattr(st, "st_birthtime", st.st_mtime)
    return min(birth, st.st_mtime)


def fresh_notes(n: int = 30) -> list[dict]:
    """The most recently ingested source notes, newest first, with thumbnails.

    Includes voice/text memos from inbox/memos — they're ingested and indexed
    like everything else, so they belong in the feed.
    """
    brain = vault._get_brain_path()
    sources = brain / "sources"
    memos = brain / "inbox" / "memos"
    pool = list(sources.glob("**/*.md")) if sources.exists() else []
    pool += list(memos.glob("*.md")) if memos.exists() else []
    if not pool:
        return []
    files = sorted(pool, key=_ingested_at, reverse=True)[:n]

    from datetime import date

    out = []
    for md in files:
        full = md.read_text(encoding="utf-8")
        text = full[:3000]
        meta = {k: v.strip() for k, v in _FM_LINE.findall(text)}
        thumb = None
        m = re.search(r"^image_paths:\n\s+- (.+)$", text, re.MULTILINE)
        if m and (brain / m.group(1).strip()).exists():
            thumb = m.group(1).strip()
        elif m2 := re.search(r"!\[\[([^\]|]+\.(?:png|jpe?g|webp|gif))", text, re.IGNORECASE):
            # notes without image_paths (e.g. screenshots) embed their image
            candidate = md.parent / m2.group(1).strip()
            if candidate.exists():
                thumb = str(candidate.relative_to(brain))
        tags_m = re.search(r"^tags:\n((?:\s+- .+\n)+)", text, re.MULTILINE)
        tags = re.findall(r"- (.+)", tags_m.group(1)) if tags_m else []
        entry = {
            "path": str(md.relative_to(brain.parent)),
            "stem": md.stem,
            "title": meta.get("title", md.stem),
            "url": meta.get("url"),
            "source": meta.get("type", md.parent.name),
            "date": meta.get("date"),
            "added": date.fromtimestamp(_ingested_at(md)).isoformat(),
            "thumbnail": thumb,
            "tags": tags,
            "has_take": "## My take" in full,
        }
        if md.parent == memos:
            # memo cards carry their transcript inline; audio (if any) is
            # served by name from AUDIO_DIR via /api/memo-audio
            body = full.split("---", 2)[-1].strip()
            entry.update(
                source="memo",
                channel=meta.get("source", "voice"),  # voice | imessage, for filtering
                title=body.splitlines()[0][:80] if body else md.stem,
                preview=body[:600],
                audio=Path(meta["audio"]).name if meta.get("audio") else None,
                kind=meta.get("route"),
                date=(meta.get("captured") or "")[:10] or entry["date"],
            )
        out.append(entry)
    return out
