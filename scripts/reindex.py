#!/usr/bin/env python3
"""
Re-process all ingested videos through the current enrichment pipeline.

Fetches fresh transcripts and metadata, re-runs Claude Haiku enrichment,
overwrites vault notes, and re-upserts ChromaDB embeddings.

Usage:
    uv run scripts/reindex.py               # reindex all processed videos
    uv run scripts/reindex.py --dry-run     # show what would be reindexed
    uv run scripts/reindex.py <video_id>    # reindex a single video
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sure ytk package is importable from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from ytk import db
from ytk.metadata import fetch_metadata
from ytk.transcript import fetch_transcript, segments_to_text
from ytk.enrich import enrich
from ytk.vault import write_note, NoteAlreadyExists, _get_vault_path, _slug
from ytk.store import upsert


def reindex_video(video_id: str, title: str, *, dry_run: bool = False) -> bool:
    """
    Re-run the enrichment pipeline for a single video.
    Returns True on success, False on failure.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"  {title[:70]}")

    if dry_run:
        print(f"    [dry-run] would reindex {video_id}")
        return True

    try:
        meta = fetch_metadata(url)
    except Exception as exc:
        print(f"    ERROR fetching metadata: {exc}", file=sys.stderr)
        return False

    try:
        segments, source = fetch_transcript(url)
        print(f"    transcript: {len(segments)} segments via {source}")
    except Exception as exc:
        print(f"    ERROR fetching transcript: {exc}", file=sys.stderr)
        return False

    full_text = segments_to_text(segments)

    try:
        enrichment = enrich(full_text, meta)
        print(f"    thesis: {enrichment.thesis[:80]}...")
    except Exception as exc:
        print(f"    ERROR enriching: {exc}", file=sys.stderr)
        return False

    # Overwrite vault note — delete existing file first if present.
    try:
        vault_path = _get_vault_path()
        existing_note = vault_path / "sources" / "youtube" / f"{_slug(meta['title'])}.md"
        if existing_note.exists():
            existing_note.unlink()
            print(f"    deleted existing note: {existing_note.name}")
        note_path = write_note(meta, enrichment, segments)
        print(f"    note written: {note_path.name}")
    except EnvironmentError:
        print("    WARNING: vault not configured, skipping note", file=sys.stderr)
    except Exception as exc:
        print(f"    ERROR writing note: {exc}", file=sys.stderr)
        return False

    try:
        upsert(meta, enrichment, segments)
        print(f"    embeddings upserted")
    except Exception as exc:
        print(f"    ERROR upserting embeddings: {exc}", file=sys.stderr)
        return False

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "video_id",
        nargs="?",
        help="Reindex a specific video ID only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be reindexed without running the pipeline.",
    )
    args = parser.parse_args()

    if args.video_id:
        # Single video mode — look up title from DB.
        all_videos = db.get_all()
        match = next((v for v in all_videos if v["video_id"] == args.video_id), None)
        title = match["title"] if match else args.video_id
        videos = [{"video_id": args.video_id, "title": title}]
    else:
        # All processed videos.
        all_videos = db.get_all()
        videos = [v for v in all_videos if v["status"] == "processed"]

    if not videos:
        print("Nothing to reindex.")
        return

    print(f"Reindexing {len(videos)} video(s){' [dry-run]' if args.dry_run else ''}...\n")

    succeeded = 0
    failed = 0
    for v in videos:
        ok = reindex_video(v["video_id"], v["title"], dry_run=args.dry_run)
        if ok:
            succeeded += 1
        else:
            failed += 1
        print()

    print(f"Done. {succeeded} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()
