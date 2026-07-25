"""User-authored topic buckets for the grove (~/.ytk/grove_buckets.yaml).

A bucket is a topic, not a directory (see the 2026-07-12 grove recon: the
directory-provenance axis produced hackathon sprints and a 1,491-note
`other`). Buckets declare membership rules; assignment is deterministic,
first bucket wins, and unmatched notes stay unmatched — no catch-all.

Pure logic lives here; the chroma/profile glue that reduces real notes to
`Note` tuples is in `resolve_notes` and reuses the same functions the map
build already trusts (scripts/build_map.py, ytk/mapdomains.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ytk.mapdomains import normalize_slug


@dataclass(frozen=True)
class Note:
    """A note reduced to the axes bucket rules can see."""

    cat: str
    project: str | None
    theme: str | None
    path: str


@dataclass
class Bucket:
    name: str
    palette: str | None = None
    projects: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    seed: str | None = None


@dataclass
class BucketConfig:
    buckets: list[Bucket]
    seed_floor: float
    version: int


def load_buckets(path: str | Path) -> BucketConfig:
    raw = yaml.safe_load(Path(path).read_text())
    buckets = [
        Bucket(
            name=b["name"],
            palette=b.get("palette"),
            projects=list(b.get("projects", [])),
            themes=list(b.get("themes", [])),
            paths=list(b.get("paths", [])),
            seed=b.get("seed"),
        )
        for b in raw.get("buckets", [])
    ]
    return BucketConfig(
        buckets=buckets,
        seed_floor=float(raw.get("seed_floor", 0.62)),
        version=int(raw.get("version", 1)),
    )


def _matches(note: Note, bucket: Bucket, declared: set[str]) -> bool:
    if note.project:
        slug = normalize_slug(note.project, declared)
        if slug in bucket.projects:
            return True
    if note.theme and note.theme in bucket.themes:
        return True
    return any(note.path.startswith(p) for p in bucket.paths)


def assign(notes: list[Note], cfg: BucketConfig) -> list[int]:
    """Bucket index per note, -1 when nothing matches. First bucket wins."""
    declared = {p for b in cfg.buckets for p in b.projects}
    out = []
    for note in notes:
        for i, bucket in enumerate(cfg.buckets):
            if _matches(note, bucket, declared):
                out.append(i)
                break
        else:
            out.append(-1)
    return out


DEFAULT_CONFIG = Path.home() / ".ytk" / "grove_buckets.yaml"


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

    from scripts.build_map import (
        CONTENT_CATS,
        SNAPSHOT,
        _rel_path,
        assign_themes,
        load_points,
    )
    from ytk.mapdomains import project_from_path

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

    notes = []
    for i, m in enumerate(meta):
        ti = theme_of.get(i, -1)
        notes.append(
            Note(
                cat=m["cat"],
                project=project_from_path(m.get("path", "")),
                theme=theme_labels[ti] if ti >= 0 else None,
                path=_rel_path(m.get("path", "")),
            )
        )
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
