"""Backfill stable theme ids + lifecycle events into stored snapshots (#83).

Replays every ~/.ytk/interest/snapshot-*.json chronologically through
identity.reconcile, so the whole history carries one id lineage before any
chart reads it. Dry-run by default; --write patches the files in place after
copying the directory to ~/.ytk/interest.pre-83-identity/.

Centroids for the cosine fallback are recomputed from note_ids against the
LIVE store, never taken from the stored snapshots: the history crosses two
encoder swaps, and stored vectors from different epochs are incomparable.
Requires the chroma server (just chroma-status).

Usage: uv run python scripts/replay_identity.py [--write]
"""

from __future__ import annotations

import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from ytk import identity
from ytk.interest import InterestSnapshot, _atomic_write
from ytk.synthesis import _embeddings_by_id

INTEREST_DIR = Path.home() / ".ytk" / "interest"
BACKUP_DIR = Path.home() / ".ytk" / "interest.pre-83-identity"


def live_centroids(
    snap: InterestSnapshot, emb: dict[str, list[float]]
) -> tuple[list[np.ndarray | None], float]:
    """Per-theme unit centroid from live embeddings only, plus member hit rate."""
    out: list[np.ndarray | None] = []
    hits = total = 0
    for t in snap.themes:
        vecs = [emb[i] for i in t.note_ids if i in emb]
        hits += len(vecs)
        total += len(t.note_ids)
        if not vecs:
            out.append(None)
            continue
        c = np.asarray(vecs, dtype=float).mean(axis=0)
        n = np.linalg.norm(c)
        out.append(c / n if n else c)
    return out, (hits / total if total else 0.0)


def main() -> None:
    write = "--write" in sys.argv
    paths = sorted(INTEREST_DIR.glob("snapshot-*.json"))
    if not paths:
        sys.exit("no snapshots found")
    if write:
        if BACKUP_DIR.exists():
            sys.exit(f"{BACKUP_DIR} already exists; refusing to overwrite the backup")
        shutil.copytree(INTEREST_DIR, BACKUP_DIR)
        print(f"backed up {len(paths)} snapshots -> {BACKUP_DIR}")

    emb = _embeddings_by_id()
    print(f"live store: {len(emb)} embedded records\n")

    prev: InterestSnapshot | None = None
    prev_centroids: list[np.ndarray | None] | None = None
    for path in paths:
        snap = InterestSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        # Idempotence: a re-run must re-derive the lineage, not extend stale ids.
        for t in snap.themes:
            t.theme_id = None
        snap.events = []
        snap.reconciled_from = None

        centroids, hit_rate = live_centroids(snap, emb)
        pairs = identity.reconcile(
            prev, snap, old_centroids=prev_centroids, new_centroids=centroids
        )

        kinds = Counter(e.kind for e in snap.events)
        scores = [s for _, _, s in pairs]
        stats = f"score min/mean={min(scores):.2f}/{np.mean(scores):.2f}" if scores else ""
        event_summary = ", ".join(f"{k}:{n}" for k, n in sorted(kinds.items()))
        print(
            f"{path.name[9:17]}  themes={len(snap.themes):2d}  matched={len(pairs):2d}"
            f"  live-hit={hit_rate:.0%}  {stats}  {event_summary}"
        )
        for e in snap.events:
            extra = f" ({e.detail})" if e.detail else ""
            others = f" {e.others}" if e.others else ""
            print(f"    {e.kind:8s} {e.theme_id} {e.label}{others}{extra}")

        if write:
            _atomic_write(path, snap.model_dump_json(indent=2))
        prev, prev_centroids = snap, centroids

    if write and prev is not None:
        _atomic_write(INTEREST_DIR / "latest.json", prev.model_dump_json(indent=2))
        print(f"\nwrote {len(paths)} snapshots + latest.json")
    elif not write:
        print("\ndry run — pass --write to patch snapshots")


if __name__ == "__main__":
    main()
