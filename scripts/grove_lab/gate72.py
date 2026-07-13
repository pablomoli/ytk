"""Triplet-gate numbers for every bucket snapshot (issue #72 groundwork).

Computes the repaired hierarchy gate (symmetric triplet agreement +
structure null) per bucket on temporal halves where the span allows,
bootstrap halves otherwise (labeled). Buckets below the clustering floor
are reported as saplings. Output feeds the morning decision on swapping
dendro.stability from centroid-ARI to this gate.

    uv run --extra dev python -m scripts.grove_lab.gate72
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from scripts.grove_lab.dendro import MIN_CLUSTER_NOTES, MIN_SPAN_DAYS, _unit
from scripts.grove_lab.shootout import structure_null, triplet_agreement

OUT = Path(__file__).resolve().parents[2] / "docs" / "grove-lab" / "gate72.json"
SEEDS = 10


def main() -> None:
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import pdist

    from scripts.grove_lab.buckets import DEFAULT_CONFIG, assign, load_buckets, resolve_notes
    from ytk.store import _TEXT_MODEL

    cfg = load_buckets(DEFAULT_CONFIG)
    vecs, meta, notes = resolve_notes()
    labels = assign(notes, cfg)
    vecs = np.asarray(vecs)
    out = {"embedding_model": _TEXT_MODEL, "seeds": SEEDS, "buckets": {}}

    for i, b in enumerate(cfg.buckets):
        idx = np.flatnonzero(np.array(labels) == i)
        if len(idx) < 2 * MIN_CLUSTER_NOTES:
            out["buckets"][b.name] = {"n": int(len(idx)), "kind": "sapling",
                                      "gate": None}
            continue
        dated = sorted((meta[k]["date"], k) for k in idx if meta[k]["date"])
        span = 0
        if len(dated) >= 2:
            span = int((np.datetime64(dated[-1][0]) - np.datetime64(dated[0][0]))
                       .astype("timedelta64[D]").astype(int))
        agr, nulls = [], []
        if span >= MIN_SPAN_DAYS:
            kind = "temporal"
            mid = len(dated) // 2
            a = np.array([k for _, k in dated[:mid]])
            bb = np.array([k for _, k in dated[mid:]])
            halves = [(a, bb)]
        else:
            kind = "bootstrap"
            halves = []
            for s in range(SEEDS):
                perm = np.random.default_rng(3000 + s).permutation(idx)
                halves.append((perm[: len(perm) // 2], perm[len(perm) // 2:]))
        for a, bb in halves:
            va, vb = vecs[a], vecs[bb]
            Za = linkage(pdist(_unit(va), "cosine"), "average")
            Zb = linkage(pdist(_unit(vb), "cosine"), "average")
            rng = np.random.default_rng(4000 + len(agr))
            agr.append(triplet_agreement(Za, va, Zb, vb, rng=rng))
            nulls.append(structure_null(Za, va, Zb, vb, rng=rng))
        out["buckets"][b.name] = {
            "n": int(len(idx)), "kind": kind, "span_days": span,
            "gate": {"triplet": round(float(np.mean(agr)), 3),
                     "structure_null": round(float(np.mean(nulls)), 3),
                     "halves": len(agr)},
        }
        print(b.name, out["buckets"][b.name])
    OUT.write_text(json.dumps(out, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
