#!/usr/bin/env -S uv run python
"""Backfill YouTube descriptions onto vault notes and video store metadata (#105).

`ytk.metadata.fetch_metadata` has always fetched the description, but nothing
ever persisted it: the vault note writes thesis/commentary/concepts/moments/
transcript, and the store embeds enrichment text only. Every description ytk
ever downloaded was discarded at the end of the ingest call.

Descriptions carry signal the transcript misses — tool names, chapter markers,
hashtags, links — mixed with sponsor boilerplate. This backfill re-fetches them
for already-ingested videos and persists the raw text in two places:

1. A `## Description` section in the vault note, between `## Key Moments` and
   `## Transcript`, wrapped in `<details>` like the transcript already is.
2. The `description` key of the video's Chroma metadata.

Chroma metadata is NOT embedded, so this is storage only — the vector space is
untouched by this script. That is deliberate (decision 2026-07-24): raw
description text never enters an embedded document. The semantics reach the
vectors later, via re-enrichment, because `enrich()` now shows the description
to the model and the tools/terms it surfaces flow into thesis and summary,
which are what actually get embedded.

Usage:
    uv run python scripts/backfill_descriptions.py                # dry run
    uv run python scripts/backfill_descriptions.py --limit 5 --apply
    uv run python scripts/backfill_descriptions.py --apply
    uv run python scripts/backfill_descriptions.py --apply --retry-failed
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytk.vault import _get_brain_path  # noqa: E402

LEDGER_PATH = Path.home() / ".ytk" / "description-backfill.json"

# yt-dlp against a hundred-plus videos back to back invites throttling.
DEFAULT_SLEEP = 1.5
MAX_ATTEMPTS = 3
BACKOFF_BASE = 8.0

_URL_RE = re.compile(r"^url:\s*(\S+)\s*$", re.MULTILINE)
DESCRIPTION_HEADING = "## Description"
TRANSCRIPT_HEADING = "## Transcript"

# Section names the note parsers (ytk/enrich_eval.py, scripts/rebuild_video_parts.py)
# recognise. A description line matching one of these verbatim would forge a
# phantom section, so collisions are reported rather than silently written.
_PARSED_SECTIONS = (
    "Thesis", "Commentary", "Summary", "Key Concepts",
    "Insights", "Key Moments", "Transcript", "Description",
)
_COLLISION_RE = re.compile(
    r"^## (?:" + "|".join(_PARSED_SECTIONS) + r")\s*$", re.MULTILINE
)


# --- ledger ---------------------------------------------------------------


def load_ledger(path: Path) -> dict:
    """Read the resume ledger; a missing or corrupt file starts a fresh run."""
    if not path.exists():
        return {"videos": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"videos": {}}
    data.setdefault("videos", {})
    return data


def save_ledger(path: Path, ledger: dict) -> None:
    """Write the ledger atomically so an interrupt cannot truncate it."""
    ledger["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def record(ledger: dict, video_id: str, status: str, **fields) -> None:
    ledger["videos"][video_id] = {
        "status": status,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **fields,
    }


# --- note surgery ---------------------------------------------------------


def note_index(brain: Path) -> dict[str, Path]:
    """Map video url -> vault note path, read from each note's frontmatter."""
    out: dict[str, Path] = {}
    yt_dir = brain / "sources" / "youtube"
    if not yt_dir.exists():
        return out
    for md in sorted(yt_dir.glob("*.md")):
        head = md.read_text(encoding="utf-8")[:2000]
        if m := _URL_RE.search(head):
            out[m.group(1)] = md
    return out


def description_block(description: str) -> str:
    """The `## Description` section, verbatim inside a collapsible block.

    Hashtags, chapter markers and links survive exactly as YouTube served
    them — the raw text is the whole point of keeping it.
    """
    return (
        f"{DESCRIPTION_HEADING}\n"
        "<details>\n"
        "<summary>Video description</summary>\n\n"
        f"{description.strip()}\n"
        "</details>\n\n"
    )


def insert_description(content: str, description: str) -> tuple[str, str]:
    """Return (new_content, outcome).

    Outcome is 'written' when the section was inserted, 'already' when the note
    already carries one (idempotent — never duplicated), or 'no-anchor' when
    the note has no `## Transcript` heading to insert before.
    """
    if re.search(r"^## Description\s*$", content, re.MULTILINE):
        return content, "already"
    anchor = re.search(r"^## Transcript\s*$", content, re.MULTILINE)
    if not anchor:
        return content, "no-anchor"
    at = anchor.start()
    return content[:at] + description_block(description) + content[at:], "written"


def collides(description: str) -> list[str]:
    """Heading lines in a description that a note parser would misread."""
    return _COLLISION_RE.findall(description)


# --- fetch ----------------------------------------------------------------


def fetch_description(url: str) -> str:
    """Description text for a video url. Raises on fetch failure."""
    from ytk.metadata import fetch_metadata

    return fetch_metadata(url).get("description", "") or ""


def fetch_with_backoff(url: str, attempts: int = MAX_ATTEMPTS) -> str:
    """Fetch with exponential backoff. Re-raises the last error on exhaustion.

    Backing off matters more than retrying: a failure here is usually YouTube
    throttling the whole run, not one bad video, and hammering turns a slow
    job into a blocked one.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return fetch_description(url)
        except Exception as exc:  # yt-dlp raises a wide family
            last = exc
            if attempt < attempts - 1:
                delay = BACKOFF_BASE * (2**attempt) + random.uniform(0, 2)
                print(f"      retry in {delay:.0f}s ({exc.__class__.__name__})")
                time.sleep(delay)
    assert last is not None
    raise last


# --- main -----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="write notes and store metadata (default: dry run)")
    parser.add_argument("--limit", type=int, default=0,
                        help="process at most N videos (0 = all)")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP,
                        help=f"seconds between fetches (default {DEFAULT_SLEEP})")
    parser.add_argument("--retry-failed", action="store_true",
                        help="re-attempt videos the ledger recorded as failed")
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    args = parser.parse_args()

    from ytk import store

    brain = _get_brain_path()
    notes = note_index(brain)
    ledger = load_ledger(args.ledger)

    col = store._videos_collection()
    got = col.get(include=["metadatas"])
    videos = [
        (vid, meta or {})
        for vid, meta in zip(got["ids"], got["metadatas"])
        if "#" not in vid
    ]
    videos.sort(key=lambda row: row[0])

    done_states = {"ok", "empty", "no-note"}
    if not args.retry_failed:
        done_states = done_states | {"failed"}

    pending = []
    resumed = 0
    for vid, meta in videos:
        prior = ledger["videos"].get(vid, {}).get("status")
        if prior in done_states:
            resumed += 1
            continue
        pending.append((vid, meta))

    if args.limit:
        pending = pending[: args.limit]

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{mode}: {len(videos)} videos in store, {len(notes)} notes indexed by url")
    print(f"  {resumed} already settled in the ledger, {len(pending)} to process")
    if not args.apply:
        print("  (no writes will be made; re-run with --apply)")
    print()

    counts: dict[str, int] = {}
    failures: list[tuple[str, str, str]] = []
    collisions: list[tuple[str, list[str]]] = []

    for n, (vid, meta) in enumerate(pending, 1):
        url = meta.get("url", "")
        title = (meta.get("title") or "")[:58]
        note = notes.get(url)
        print(f"[{n}/{len(pending)}] {vid}  {title}")

        if note is None:
            counts["no-note"] = counts.get("no-note", 0) + 1
            print("      no vault note for this url — skipped")
            if args.apply:
                record(ledger, vid, "no-note", url=url)
                save_ledger(args.ledger, ledger)
            continue

        try:
            description = fetch_with_backoff(url)
        except Exception as exc:
            reason = f"{exc.__class__.__name__}: {exc}"
            counts["failed"] = counts.get("failed", 0) + 1
            failures.append((vid, title, reason))
            print(f"      FAILED {reason[:120]}")
            if args.apply:
                record(ledger, vid, "failed", url=url, error=reason[:500])
                save_ledger(args.ledger, ledger)
            time.sleep(args.sleep)
            continue

        if not description.strip():
            counts["empty"] = counts.get("empty", 0) + 1
            print("      description is empty")
            if args.apply:
                record(ledger, vid, "empty", url=url, chars=0)
                save_ledger(args.ledger, ledger)
            time.sleep(args.sleep)
            continue

        bad = collides(description)
        if bad:
            collisions.append((vid, bad))

        content = note.read_text(encoding="utf-8")
        new_content, outcome = insert_description(content, description)
        counts[outcome] = counts.get(outcome, 0) + 1
        print(f"      {len(description)} chars, note: {outcome}")

        if args.apply:
            if outcome == "written":
                note.write_text(new_content, encoding="utf-8")
            ids = [i for i in got["ids"] if i.split("#", 1)[0] == vid]
            existing = col.get(ids=ids, include=["metadatas"])
            col.update(
                ids=existing["ids"],
                metadatas=[
                    {**(m or {}), "description": description}
                    for m in existing["metadatas"]
                ],
            )
            record(
                ledger, vid,
                "ok" if outcome != "no-anchor" else "no-anchor",
                url=url, chars=len(description), note=str(note), section=outcome,
            )
            save_ledger(args.ledger, ledger)

        time.sleep(args.sleep)

    print(f"\n--- {mode} summary ---")
    for key in sorted(counts):
        print(f"  {key:<12} {counts[key]}")
    if collisions:
        print(f"\n  {len(collisions)} descriptions contain a line a note parser "
              "could misread as a section heading:")
        for vid, heads in collisions[:10]:
            print(f"    {vid}: {heads}")
    if failures:
        print(f"\n  {len(failures)} failures:")
        for vid, title, reason in failures:
            print(f"    {vid}  {title}\n      {reason[:200]}")
    if args.apply:
        print(f"\nledger: {args.ledger}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
