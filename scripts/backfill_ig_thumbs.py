"""Backfill missing Instagram thumbnails for already-ingested notes.

Notes ingested before image saving (phase 5I) have no image_paths frontmatter,
so the fresh feed and brain map render them imageless. For each such note this
fetches the post's cover via the authenticated instagrapi client, saves it
using the same layout as the ingest pipeline (thumbnails/{shortcode}-thumb.jpg),
and patches image_paths into the frontmatter.

Usage:
    uv run python scripts/backfill_ig_thumbs.py [--dry-run] [--limit N]

Paced at one media fetch per few seconds to stay polite with Instagram.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from ytk import reels, vault
from ytk.instagram import fetch_instagram_auth

PACING_SECONDS = 4.0
IMG_RE = re.compile(r"^image_paths:\n\s+- (.+)$", re.MULTILINE)
URL_RE = re.compile(r"^url:\s*(.+)$", re.MULTILINE)
SC_RE = re.compile(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)")


def broken_notes(ig_dir: Path, brain: Path) -> list[Path]:
    out = []
    for md in sorted(ig_dir.glob("*.md")):
        text = md.read_text(errors="ignore")[:3000]
        m = IMG_RE.search(text)
        if m and (brain / m.group(1).strip()).exists():
            continue
        out.append(md)
    return out


def patch_frontmatter(md: Path, rel_path: str) -> None:
    text = md.read_text()
    if IMG_RE.search(text):
        text = IMG_RE.sub(f"image_paths:\n  - {rel_path}", text, count=1)
    else:
        # insert before the closing frontmatter fence
        head, sep, rest = text.partition("\n---\n")
        text = f"{head}\nimage_paths:\n  - {rel_path}{sep}{rest}"
    md.write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    brain = vault._get_brain_path()
    ig_dir = brain / "sources" / "instagram"
    thumb_dir = ig_dir / "thumbnails"
    notes = broken_notes(ig_dir, brain)
    if args.limit:
        notes = notes[: args.limit]
    print(f"{len(notes)} notes need thumbnails")
    if args.dry_run:
        for md in notes:
            print("  ", md.name)
        return

    sessionid = os.environ.get("INSTAGRAM_SESSIONID", "")
    client = reels.get_client(sessionid)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    fixed = failed = 0
    for i, md in enumerate(notes):
        url_m = URL_RE.search(md.read_text(errors="ignore")[:1000])
        sc_m = SC_RE.search(url_m.group(1)) if url_m else None
        if not sc_m:
            print(f"skip {md.name}: no shortcode in url")
            continue
        shortcode = sc_m.group(1)
        try:
            post = fetch_instagram_auth(url_m.group(1).strip(), client)
            cover = post.thumbnail_url or (post.images[0] if post.images else None)
            if not cover:
                raise ValueError("post has no cover image")
            saved = vault._save_image(cover, thumb_dir / f"{shortcode}-thumb")
            if saved is None:
                raise ValueError("download failed")
            rel = str(saved.relative_to(brain))
            patch_frontmatter(md, rel)
            fixed += 1
            print(f"[{i + 1}/{len(notes)}] {md.name} -> {rel}")
        except Exception as exc:
            failed += 1
            print(f"[{i + 1}/{len(notes)}] FAIL {md.name}: {exc}")
        if i < len(notes) - 1:
            time.sleep(PACING_SECONDS)

    print(f"done: {fixed} fixed, {failed} failed")


if __name__ == "__main__":
    main()
