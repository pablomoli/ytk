#!/usr/bin/env -S uv run python
"""Re-enrich already-ingested videos now that enrichment reads the description (#105).

Phase 2 of the description backfill. `scripts/backfill_descriptions.py` stores the
raw description; this script is how its *meaning* reaches the vector space.

The rule that shapes this script: raw description text never enters an embedded
document (decision 2026-07-24). Instead the description goes into the enrichment
prompt, and whatever the model surfaces from it — tool names, correct spellings,
chapter topics — lands in the thesis and summary, which are exactly what
`store.upsert` embeds. The embedded document keeps the shape the retrieval gate
was measured on; only its content improves.

What it does per video:

1. Re-fetches full metadata with yt-dlp. Deliberately a fresh fetch rather than a
   read of the stored description: the original enrichment prompt also carried
   YouTube tags and chapters, which ytk never persisted either. Re-fetching keeps
   the prompt identical to the original in every respect except the added
   description, so a change in retrieval is attributable to the description and
   not to input we silently dropped.
2. Skips videos with an empty description — their prompt input is unchanged, so
   re-enriching them would only add prompt-drift noise and burn a model call.
3. Rebuilds the transcript from the segments collection (the same text that was
   embedded) and re-runs `enrich()`.
4. Rewrites only the enrichment prose sections of the vault note. Frontmatter
   tags are left alone: they are user-curated through the hub and must round-trip
   byte-exact. `## Description`, `## Transcript` and any user-authored section
   (`## My take`) survive untouched.
5. Re-embeds the representative video vector, preserving any `My take:` suffix
   that `store.append_video_take` appended to the document.

Segment vectors are not touched — the transcript did not change.

Usage:
    uv run python scripts/reenrich_with_descriptions.py                # dry run
    uv run python scripts/reenrich_with_descriptions.py --limit 3 --apply
    uv run python scripts/reenrich_with_descriptions.py --apply
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytk.vault import _get_brain_path

LEDGER_PATH = Path.home() / ".ytk" / "reenrich-descriptions.json"

DEFAULT_SLEEP = 1.5
MAX_ATTEMPTS = 3
BACKOFF_BASE = 8.0

_URL_RE = re.compile(r"^url:\s*(\S+)\s*$", re.MULTILINE)
_DURATION_RE = re.compile(r"^duration:\s*(\S+)\s*$", re.MULTILINE)

# Sections this script owns. Everything else in a note is either user-authored
# or belongs to another stage of the pipeline, and must survive verbatim.
_OWNED = ("Thesis", "Commentary", "Key Concepts", "Insights", "Key Moments")


# --- ledger ---------------------------------------------------------------


def load_ledger(path: Path) -> dict:
    if not path.exists():
        return {"videos": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"videos": {}}
    data.setdefault("videos", {})
    return data


def save_ledger(path: Path, ledger: dict) -> None:
    ledger["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def record(ledger: dict, video_id: str, status: str, **fields) -> None:
    ledger["videos"][video_id] = {
        "status": status,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        **fields,
    }


# --- inputs ---------------------------------------------------------------


def note_index(brain: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    yt_dir = brain / "sources" / "youtube"
    if not yt_dir.exists():
        return out
    for md in sorted(yt_dir.glob("*.md")):
        head = md.read_text(encoding="utf-8")[:2000]
        if m := _URL_RE.search(head):
            out[m.group(1)] = md
    return out


def transcripts_by_video(store) -> dict[str, str]:
    """Rebuild each video's transcript from its embedded 60s segment blocks.

    The segment documents are the transcript as ytk stored it, so this
    reconstructs the enrichment input without a second network fetch.
    """
    col = store._segments_collection()
    got = col.get(include=["documents", "metadatas"])
    blocks: dict[str, list[tuple[float, str]]] = {}
    for doc, meta in zip(got["documents"], got["metadatas"]):
        vid = (meta or {}).get("video_id", "")
        if not vid or not doc:
            continue
        blocks.setdefault(vid, []).append((float((meta or {}).get("start", 0.0)), doc))
    return {vid: " ".join(text for _, text in sorted(parts)) for vid, parts in blocks.items()}


def fetch_with_backoff(url: str, attempts: int = MAX_ATTEMPTS) -> dict:
    """yt-dlp metadata with exponential backoff; re-raises on exhaustion."""
    from ytk.metadata import fetch_metadata

    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return fetch_metadata(url)
        except Exception as exc:
            last = exc
            if attempt < attempts - 1:
                delay = BACKOFF_BASE * (2**attempt) + random.uniform(0, 2)
                print(f"      retry in {delay:.0f}s ({exc.__class__.__name__})")
                time.sleep(delay)
    assert last is not None
    raise last


# --- note surgery ---------------------------------------------------------


def replace_section(content: str, name: str, body: str) -> tuple[str, bool]:
    """Replace one `## name` section's body, leaving every other byte alone."""
    pattern = re.compile(rf"^## {re.escape(name)}\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    m = pattern.search(content)
    if not m:
        return content, False
    return content[: m.start()] + f"## {name}\n{body}\n\n" + content[m.end() :], True


def rewrite_note(content: str, enrichment) -> tuple[str, list[str]]:
    """Rewrite the enrichment prose sections. Returns (content, sections missed)."""
    bodies = {
        "Thesis": enrichment.thesis,
        "Commentary": enrichment.summary,
        "Key Concepts": "\n".join(f"- {c}" for c in enrichment.key_concepts),
        "Insights": "\n".join(f"- {i}" for i in enrichment.insights),
        "Key Moments": "\n".join(
            f"- **{km.timestamp}** — {km.description}" for km in enrichment.key_moments
        ),
    }
    missed: list[str] = []
    for name in _OWNED:
        content, ok = replace_section(content, name, bodies[name].strip())
        if not ok:
            missed.append(name)
    return content, missed


# --- main -----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="write notes and re-embed (default: dry run)"
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    args = parser.parse_args()

    from ytk import store
    from ytk.enrich import enrich

    brain = _get_brain_path()
    notes = note_index(brain)
    ledger = load_ledger(args.ledger)

    col = store._videos_collection()
    got = col.get(include=["documents", "metadatas"])
    videos = [
        (vid, doc or "", meta or {})
        for vid, doc, meta in zip(got["ids"], got["documents"], got["metadatas"])
        if "#" not in vid
    ]
    videos.sort(key=lambda row: row[0])
    transcripts = transcripts_by_video(store)

    done = {"ok", "no-description", "no-transcript", "no-note"}
    if args.retry_failed:
        done -= {"failed"}
    else:
        done |= {"failed"}

    pending = [
        (vid, doc, meta)
        for vid, doc, meta in videos
        if ledger["videos"].get(vid, {}).get("status") not in done
    ]
    outstanding = len(pending)
    if args.limit:
        pending = pending[: args.limit]

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{mode}: {len(videos)} videos, {len(transcripts)} with segment transcripts")
    print(
        f"  {len(videos) - outstanding} settled in the ledger, "
        f"{outstanding} outstanding, {len(pending)} this run"
    )
    if not args.apply:
        print("  (no writes; re-run with --apply)")
    print()

    counts: dict[str, int] = {}
    failures: list[tuple[str, str]] = []
    started = time.time()

    for n, (vid, doc, meta) in enumerate(pending, 1):
        url = meta.get("url", "")
        title = (meta.get("title") or "")[:56]
        print(f"[{n}/{len(pending)}] {vid}  {title}")

        note = notes.get(url)
        if note is None:
            counts["no-note"] = counts.get("no-note", 0) + 1
            print("      no vault note — skipped")
            if args.apply:
                record(ledger, vid, "no-note", url=url)
                save_ledger(args.ledger, ledger)
            continue

        transcript = transcripts.get(vid, "").strip()
        if not transcript:
            counts["no-transcript"] = counts.get("no-transcript", 0) + 1
            print("      no segment transcript — skipped")
            if args.apply:
                record(ledger, vid, "no-transcript", url=url)
                save_ledger(args.ledger, ledger)
            continue

        try:
            fresh = fetch_with_backoff(url)
        except Exception as exc:
            reason = f"{exc.__class__.__name__}: {exc}"
            counts["failed"] = counts.get("failed", 0) + 1
            failures.append((vid, reason))
            print(f"      FETCH FAILED {reason[:110]}")
            if args.apply:
                record(ledger, vid, "failed", url=url, stage="fetch", error=reason[:500])
                save_ledger(args.ledger, ledger)
            time.sleep(args.sleep)
            continue

        description = (fresh.get("description") or "").strip()
        if not description:
            counts["no-description"] = counts.get("no-description", 0) + 1
            print("      empty description — nothing would change, skipped")
            if args.apply:
                record(ledger, vid, "no-description", url=url)
                save_ledger(args.ledger, ledger)
            time.sleep(args.sleep)
            continue

        fresh["url"] = url
        print(
            f"      description {len(description)} chars, "
            f"transcript {len(transcript)} chars — enriching..."
        )
        t0 = time.time()
        try:
            if args.apply:
                result = enrich(transcript, fresh)
            else:
                result = None
        except Exception as exc:
            reason = f"{exc.__class__.__name__}: {exc}"
            counts["failed"] = counts.get("failed", 0) + 1
            failures.append((vid, reason))
            print(f"      ENRICH FAILED {reason[:110]}")
            record(ledger, vid, "failed", url=url, stage="enrich", error=reason[:500])
            save_ledger(args.ledger, ledger)
            time.sleep(args.sleep)
            continue

        if result is None:
            counts["would-enrich"] = counts.get("would-enrich", 0) + 1
            time.sleep(args.sleep)
            continue

        elapsed = time.time() - t0
        content, missed = rewrite_note(note.read_text(encoding="utf-8"), result)
        note.write_text(content, encoding="utf-8")

        # The representative vector is thesis+summary, exactly as store.upsert
        # builds it. A user's take was appended to the old document by
        # append_video_take and would be lost by a naive rebuild.
        new_doc = result.thesis + "\n\n" + result.summary
        if take := re.search(r"\n\nMy take: (.+)\Z", doc, re.DOTALL):
            new_doc += f"\n\nMy take: {take.group(1)}"
        col.upsert(
            ids=[vid],
            documents=[new_doc],
            metadatas=[
                {
                    **meta,
                    "thesis": result.thesis,
                    "summary": result.summary,
                    "description": description,
                }
            ],
        )

        counts["ok"] = counts.get("ok", 0) + 1
        print(
            f"      re-embedded in {elapsed:.0f}s"
            + (f"  (sections missing from note: {missed})" if missed else "")
        )
        record(
            ledger,
            vid,
            "ok",
            url=url,
            seconds=round(elapsed, 1),
            description_chars=len(description),
            kept_take=bool(take),
            missed_sections=missed,
        )
        save_ledger(args.ledger, ledger)
        time.sleep(args.sleep)

    print(f"\n--- {mode} summary ({time.time() - started:.0f}s) ---")
    for key in sorted(counts):
        print(f"  {key:<16} {counts[key]}")
    if failures:
        print(f"\n  {len(failures)} failures:")
        for vid, reason in failures:
            print(f"    {vid}: {reason[:200]}")
    if args.apply:
        print(f"\nledger: {args.ledger}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
