"""User-authored topic buckets for the grove (~/.ytk/grove_buckets.yaml).

A bucket is a topic, not a directory (see the 2026-07-12 grove recon: the
directory-provenance axis produced hackathon sprints and a 1,491-note
`other`). Buckets declare membership rules; assignment is deterministic,
first bucket wins, and unmatched notes stay unmatched — no catch-all.

The matcher itself moved to `ytk.mapdomains` when the map became the second
consumer of this axis (#106) — one implementation, and no cycle with
normalize_slug. It is re-exported here so every grove_lab caller keeps its
import. What stays is the chroma/profile glue that reduces real notes to
`Note` tuples, which reuses the same functions the map build already trusts
(scripts/build_map.py).
"""

from __future__ import annotations

from ytk.mapdomains import (
    DEFAULT_CONFIG,
    Bucket,
    BucketConfig,
    Note,
    assign,
    load_buckets,
    normalize_slug,
)

__all__ = [
    "DEFAULT_CONFIG",
    "Bucket",
    "BucketConfig",
    "Note",
    "assign",
    "dedupe_indices",
    "load_buckets",
    "normalize_slug",
    "resolve_notes",
]


def dedupe_indices(keys: list[str]) -> list[int]:
    """Indices to keep, first occurrence of each non-empty key wins.

    Chroma double-indexes some notes (2026-07-12 audit: 168 extra copies,
    3.6% of corpus, instagram worst-hit) — identity is the note key, so
    duplicates would inflate bucket masses and every downstream stat.
    Empty keys are anonymous, never collapsed.
    """
    seen: set[str] = set()
    keep = []
    for i, k in enumerate(keys):
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        keep.append(i)
    return keep


def resolve_notes():
    """Real corpus reduced to Note tuples, plus the vectors and raw meta.

    Reuses the map build's loading contract verbatim: part-vector skipping,
    theme assignment with its confidence floor, project parsing.
    Returns (vecs, meta, notes).
    """
    import json
    import os
    from pathlib import Path

    from scripts.build_map import (
        CONTENT_CATS,
        SNAPSHOT,
        _rel_path,
        assign_themes,
        load_points,
    )
    from ytk.mapdomains import notes_from_metas

    snapshot = json.loads(Path(os.path.expanduser(SNAPSHOT)).read_text())
    theme_labels = [t["label"] for t in snapshot["themes"]]
    vecs, meta, _docs = load_points()
    keep = dedupe_indices([m.get("url") or m.get("path") or m.get("title") or "" for m in meta])
    if len(keep) < len(meta):
        print(f"deduped {len(meta) - len(keep)} double-indexed notes")
    vecs = vecs[keep]
    meta = [meta[i] for i in keep]
    cidx = [i for i, m in enumerate(meta) if m["cat"] in CONTENT_CATS]
    cthemes = assign_themes(vecs[cidx], snapshot)
    theme_of = {g: cthemes[k] for k, g in enumerate(cidx)}

    notes = notes_from_metas(meta, theme_of, theme_labels, _rel_path)
    return vecs, meta, notes


def main() -> None:
    from collections import Counter

    cfg = load_buckets(DEFAULT_CONFIG)
    vecs, meta, notes = resolve_notes()
    labels = assign(notes, cfg)

    total = len(notes)
    matched = sum(1 for x in labels if x >= 0)
    print(
        f"{total} notes, {matched} matched ({100 * matched / total:.0f}%), "
        f"{total - matched} unmatched (render nothing)\n"
    )
    print(f"{'bucket':<18} {'n':>5}  categories")
    print("-" * 60)
    for i, b in enumerate(cfg.buckets):
        idx = [k for k, x in enumerate(labels) if x == i]
        cats = Counter(meta[k]["cat"] for k in idx)
        catstr = ", ".join(f"{c}:{n}" for c, n in cats.most_common(4))
        print(f"{b.name:<18} {len(idx):>5}  {catstr}")
    un = Counter()
    for k, x in enumerate(labels):
        if x < 0:
            un[notes[k].project or notes[k].cat] += 1
    print("\nunmatched mass (top 10): " + ", ".join(f"{s}:{n}" for s, n in un.most_common(10)))


if __name__ == "__main__":
    main()
