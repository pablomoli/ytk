"""Bucket quality + dedupe reconciliation tables (Codex review item C).

Publishes what the buckets actually are: coverage, overlap (notes matching
2+ buckets before first-match-wins), within-bucket coherence, nearest-
alternative separation, and the exact dedupe arithmetic (F8's denominator
complaint). Pure reporting; JSON artifact for the morning report.

    uv run --extra dev python -m scripts.grove_lab.quality
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[2] / "docs" / "grove-lab" / "bucket-quality.json"


def main() -> None:
    from scripts.build_map import load_points
    from scripts.grove_lab.buckets import (
        DEFAULT_CONFIG, _matches, assign, dedupe_indices, load_buckets, resolve_notes,
    )
    from scripts.grove_lab.dendro import _unit
    from ytk.store import _TEXT_MODEL

    # dedupe reconciliation with explicit denominators (F8)
    raw_vecs, raw_meta, _docs = load_points()
    keys = [m.get("url") or m.get("path") or m.get("title") or "" for m in raw_meta]
    keep = dedupe_indices(keys)
    dupe_keys = {k for k, n in Counter(k for k in keys if k).items() if n > 1}
    recon = {
        "chroma_rows_after_part_skip": len(raw_meta),
        "identity_rule": "url | source_path | title (first occurrence wins; empty keys never collapse)",
        "keys_with_2plus_rows": len(dupe_keys),
        "rows_removed": len(raw_meta) - len(keep),
        "unique_notes": len(keep),
    }

    cfg = load_buckets(DEFAULT_CONFIG)
    vecs, meta, notes = resolve_notes()
    labels = assign(notes, cfg)
    u = _unit(np.asarray(vecs))
    declared = {p for b in cfg.buckets for p in b.projects}

    # overlap: how many notes match 2+ buckets before first-match-wins
    match_counts = [
        sum(1 for b in cfg.buckets if _matches(note, b, declared)) for note in notes
    ]
    overlap_notes = sum(1 for c in match_counts if c >= 2)

    cents = {}
    per_bucket = {}
    for i, b in enumerate(cfg.buckets):
        idx = np.flatnonzero(np.array(labels) == i)
        if len(idx):
            c = u[idx].mean(axis=0)
            cents[b.name] = c / max(np.linalg.norm(c), 1e-12)
    for i, b in enumerate(cfg.buckets):
        idx = np.flatnonzero(np.array(labels) == i)
        if not len(idx):
            per_bucket[b.name] = {"n": 0}
            continue
        within = float((u[idx] @ cents[b.name]).mean())
        others = {
            name: float((u[idx] @ c).mean()) for name, c in cents.items() if name != b.name
        }
        nearest = max(others, key=others.get) if others else None
        per_bucket[b.name] = {
            "n": int(len(idx)),
            "within_sim": round(within, 3),
            "nearest_other": nearest,
            "nearest_other_sim": round(others[nearest], 3) if nearest else None,
            "separation": round(within - others[nearest], 3) if nearest else None,
        }

    result = {
        "embedding_model": _TEXT_MODEL,
        "dedupe_reconciliation": recon,
        "total_notes": len(notes),
        "matched": int(sum(1 for x in labels if x >= 0)),
        "overlap_notes_matching_2plus_buckets": int(overlap_notes),
        "per_bucket": per_bucket,
    }
    OUT.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
