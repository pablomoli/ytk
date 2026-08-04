#!/usr/bin/env python
"""Distill short titles for instagram/tiktok notes whose title is a thesis (#169).

The writers put the full enrichment thesis in frontmatter title (median 254
chars for instagram). The long sentence already lives in the body as
## Thesis, so rewriting the title loses nothing. Batched through one
structured call per BATCH notes.

    uv run python scripts/distill_titles.py [--dry-run] [--limit N]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from ytk.enrich import TITLE_MAX_CHARS, distill_titles
from ytk.vault import _get_brain_path

BATCH = 40
SOURCES = ("instagram", "tiktok")


def main() -> None:
    dry = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    brain = _get_brain_path()
    todo: list[tuple[Path, str]] = []
    for src in SOURCES:
        for f in sorted((brain / "sources" / src).glob("*.md")):
            head = f.read_text(encoding="utf-8")[:2000]
            m = re.search(r"^title: (.+)$", head, re.MULTILINE)
            if m and len(m.group(1).strip()) > TITLE_MAX_CHARS:
                todo.append((f, m.group(1).strip()))
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} notes with titles over {TITLE_MAX_CHARS} chars")
    if dry:
        for f, t in todo[:10]:
            print(f"  {f.name}: {t[:70]}...")
        return
    done = 0
    for at in range(0, len(todo), BATCH):
        batch = todo[at : at + BATCH]
        shorts = distill_titles([t for _, t in batch])
        for (f, old), short in zip(batch, shorts):
            short = " ".join(short.split())
            if not short or len(short) > 120:
                print(f"  SKIP {f.name}: bad distilled title {short!r}")
                continue
            text = f.read_text(encoding="utf-8")
            new = text.replace(f"title: {old}", f"title: {short}", 1)
            if new == text:
                print(f"  SKIP {f.name}: title line not found verbatim")
                continue
            f.write_text(new, encoding="utf-8")
            done += 1
            print(f"  {f.name}\n    {old[:72]}...\n    -> {short}")
    print(f"rewrote {done}/{len(todo)} titles")


if __name__ == "__main__":
    main()
