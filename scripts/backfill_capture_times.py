#!/usr/bin/env -S uv run python
"""Backfill honest capture timestamps for store records that predate stamping.

`ingested_at` stamping began 2026-07-15, leaving every earlier record with an
unknown capture time. That gap made "captured recently" mean "captured since
stamping began", which skewed profile freshness toward a single heavy-use day.

This one-off migration stamps the missing records from evidence of when the
note actually entered the vault, never from publication dates:

1. File birthtime (APFS st_birthtime) of the vault source note — notes are
   written at ingest, so birthtime is the capture moment unless the file was
   later rewritten by a migration.
2. Daily ingest digests (inbox/review-YYYY-MM-DD.md) — an authored record of
   what was captured on which day. When a digest names the note and disagrees
   with birthtime by more than DIGEST_TOLERANCE_DAYS, the digest date wins and
   the disagreement is reported (rewritten files carry a false birthtime).

Existing `ingested_at` stamps are never touched: first write wins, matching
`_with_ingest_time`. Run with --dry-run to print the audit without writing.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytk.signals import _YT_ID_RE
from ytk.vault import _get_brain_path

DIGEST_TOLERANCE_DAYS = 2

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
_DIGEST_NAME_RE = re.compile(r"review-(\d{4}-\d{2}-\d{2})\.md$")


def iter_source_notes(brain: Path) -> list[Path]:
    """Vault source notes, mirroring ytk.signals.signal_map's filters."""
    sources = brain / "sources"
    return [
        md
        for md in sorted(sources.glob("**/*.md"))
        if md.parent.name not in ("thumbnails", "channels") and "frames" not in md.parts
    ]


def digest_dates(brain: Path) -> dict[str, str]:
    """Map note stem -> digest date for every note named in an ingest digest."""
    out: dict[str, str] = {}
    for digest in sorted((brain / "inbox").glob("review-*.md")):
        m = _DIGEST_NAME_RE.search(digest.name)
        if not m:
            continue
        for stem in _WIKILINK_RE.findall(digest.read_text(encoding="utf-8")):
            out.setdefault(stem.strip(), m.group(1))
    return out


def note_store_keys(note: Path) -> list[str]:
    """Join keys a source note may appear under in the store.

    YouTube notes join on the 11-char video id. Memory docs use truncated
    doc ids, so the reliable key there is the absolute source_path kept in
    record metadata; the doc-id form is included as a fallback.
    """
    keys = [str(note), f"{note.parent.name}_{note.stem}"]
    text = note.read_text(encoding="utf-8")
    m = _YT_ID_RE.search(text)
    if m and note.parent.name == "youtube":
        keys.append(m.group(1))
    return keys


def capture_time(note: Path, digests: dict[str, str]) -> tuple[str, str | None]:
    """(UTC ISO capture time, anomaly description or None) for one note."""
    birth = datetime.fromtimestamp(note.stat().st_birthtime, tz=UTC)
    digest_day = digests.get(note.stem)
    if digest_day:
        digest_date = datetime.fromisoformat(digest_day).replace(tzinfo=UTC)
        if abs(birth - digest_date) > timedelta(days=DIGEST_TOLERANCE_DAYS):
            return (
                digest_date.isoformat(timespec="seconds"),
                f"birthtime {birth.date()} vs digest {digest_day}"
                " — file likely rewritten; digest wins",
            )
    return birth.isoformat(timespec="seconds"), None


def digest_stamps(notes: list[Path], digests: dict[str, str]) -> dict[str, str]:
    """source_path -> digest-derived stamp, for notes an ingest digest names.

    Digest dates are the strongest capture evidence available and may
    OVERWRITE an existing `ingested_at` on the vault-reindexed
    (note_sources_*) records: those were stamped at reindex time, not
    capture time, so a reel from the July 5 DM-backlog sync carried a July
    16-17 reindex stamp until this correction.
    """
    out: dict[str, str] = {}
    for note in notes:
        digest_day = digests.get(note.stem)
        if digest_day:
            stamp = datetime.fromisoformat(digest_day).replace(tzinfo=UTC)
            out[str(note)] = stamp.isoformat(timespec="seconds")
    return out


def stamp_collection(
    col,
    stamps: dict[str, str],
    overwrite: dict[str, str],
    dry_run: bool,
) -> tuple[int, int, int]:
    """Stamp base records and their '#'-suffixed overflow parts.

    ``stamps`` fills missing `ingested_at` only (first write wins).
    ``overwrite`` (source_path -> stamp) replaces existing stamps too, but
    only on `note_sources_*` ids — the reindexer-stamped records whose
    `ingested_at` records reindex time rather than capture time.
    Returns (written, overwritten, kept).
    """
    data = col.get(include=["metadatas"])
    ids, metas, written, overwritten, kept = [], [], 0, 0, 0
    for item_id, meta in zip(data["ids"], data["metadatas"]):
        base = item_id.split("#", 1)[0]
        source_path = (meta or {}).get("source_path", "")
        existing = (meta or {}).get("ingested_at", "")
        correction = overwrite.get(source_path) if base.startswith("note_sources_") else None
        if correction and existing != correction:
            ids.append(item_id)
            metas.append({**(meta or {}), "ingested_at": correction})
            overwritten += 1
            continue
        stamp = stamps.get(source_path) or stamps.get(base)
        if stamp is None:
            continue
        if existing:
            kept += 1
            continue
        ids.append(item_id)
        metas.append({**(meta or {}), "ingested_at": stamp})
        written += 1
    if ids and not dry_run:
        col.update(ids=ids, metadatas=metas)
    return written, overwritten, kept


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="print the audit report without writing"
    )
    args = parser.parse_args()

    brain = _get_brain_path()
    notes = iter_source_notes(brain)
    digests = digest_dates(brain)

    stamps: dict[str, str] = {}
    note_stamps: list[str] = []
    anomalies: list[tuple[Path, str]] = []
    for note in notes:
        stamp, anomaly = capture_time(note, digests)
        note_stamps.append(stamp)
        for key in note_store_keys(note):
            stamps[key] = stamp
        if anomaly:
            anomalies.append((note, anomaly))

    print(
        f"{len(notes)} source notes, {len(digests)} digest-dated stems, "
        f"{len(anomalies)} birthtime/digest disagreements"
    )
    months = Counter(s[:7] for s in note_stamps)
    for month in sorted(months):
        print(f"  {month}  {months[month]:>4}")
    if anomalies:
        print("\nanomalies (digest date used):")
        for note, why in anomalies:
            print(f"  {note.name}: {why}")

    from ytk.store import _memories_collection, _videos_collection

    overwrite = digest_stamps(notes, digests)
    total_written = total_over = total_kept = 0
    for name, col in (("videos", _videos_collection()), ("memories", _memories_collection())):
        written, overwritten, kept = stamp_collection(col, stamps, overwrite, args.dry_run)
        total_written += written
        total_over += overwritten
        total_kept += kept
        verb = "would stamp" if args.dry_run else "stamped"
        print(
            f"\n{name}: {verb} {written}, corrected {overwritten} "
            f"reindex-era stamps, kept {kept} existing stamps"
        )

    print(
        f"\n{'DRY RUN — nothing written' if args.dry_run else 'DONE'}: "
        f"{total_written} stamped, {total_over} corrected, {total_kept} untouched"
    )
    print(
        "confound: note_sources_* records with no digest evidence keep their "
        "reindex-era stamp (wrong by days for the DM-backlog cohort); "
        "same-day batch dampening bounds their influence"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
