"""Gate 0/1 prep: export the evaluation corpus to corpus.jsonl.

One line per doc: {"id", "bucket", "text"}. Buckets:
  memories — vault note bodies (full text, frontmatter stripped), the texts
             whose tails #84 was silently dropping
  videos   — representative thesis+summary docs from ytk_videos (no '#' parts)
  segments — a deterministic sample of 60s transcript blocks

Texts come from the same sources production embeds, so every candidate model
sees identical inputs.

    uv run python experiments/encoder_harness/export_corpus.py [--out DIR] [--segments 600]
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="experiments/encoder_harness/data")
    ap.add_argument("--segments", type=int, default=600)
    args = ap.parse_args()

    from ytk.store import strip_frontmatter
    from ytk import vault
    import chromadb

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    brain = vault._get_brain_path()
    scan = ["inbox/memories", "projects", "decisions", "debugging", "tools",
            "sources/instagram", "sources/web", "sources/journal", "inbox/memos"]
    for subdir in scan:
        d = brain / subdir
        if not d.exists():
            continue
        for md in sorted(d.glob("**/*.md")):
            body = strip_frontmatter(md.read_text(encoding="utf-8", errors="ignore"))
            if not body.strip():
                continue
            rel = str(md.relative_to(brain))
            rows.append({"id": f"mem::{rel}", "bucket": "memories", "text": body[:8000]})

    client = chromadb.PersistentClient(path=os.path.expanduser(
        os.environ.get("CHROMA_PATH", "~/.ytk/chroma")))
    vids = client.get_collection("ytk_videos").get(include=["documents"])
    for vid, doc in zip(vids["ids"], vids["documents"]):
        if "#" in vid or not (doc or "").strip():
            continue
        rows.append({"id": f"vid::{vid}", "bucket": "videos", "text": doc})

    segs = client.get_collection("ytk_segments").get(include=["documents", "metadatas"])
    pool = [
        (sid, doc, meta) for sid, doc, meta in
        zip(segs["ids"], segs["documents"], segs["metadatas"])
        if (doc or "").strip()
    ]
    random.Random(20260716).shuffle(pool)
    for sid, doc, meta in pool[: args.segments]:
        rows.append({
            "id": f"seg::{sid}", "bucket": "segments", "text": doc,
        })

    path = out / "corpus.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            # ensure_ascii: note text can contain U+2028/U+2029, which
            # str.splitlines() treats as line breaks — raw they corrupt JSONL
            f.write(json.dumps(r) + "\n")

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    print(json.dumps({"total": len(rows), **counts}))


if __name__ == "__main__":
    main()
