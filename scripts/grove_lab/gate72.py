"""Triplet-gate numbers for every bucket snapshot (issue #72 groundwork).

v2 per Codex v5 K7: Monte Carlo over 10 triplet-sampling seeds on the
FIXED temporal halves (mean/min/max + used/tie/collision stats), and two
explicitly named gates so they cannot be conflated:

  full_linkage_triplet - shootout construct: full scipy dendrogram
                         cophenetic triplets, cross-half 1-NN leaf mapping
  fit_nodes_triplet    - the truncated node topology snapshots actually
                         store and render: LCA-depth ultrametric over
                         fit_nodes trees, cross-half 1-NN note mapping

Buckets below the clustering floor are saplings (gate null).

    uv run --extra dev python -m scripts.grove_lab.gate72
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from scripts.grove_lab.dendro import MIN_CLUSTER_NOTES, MIN_SPAN_DAYS, _unit
from scripts.grove_lab.replay import _triplets, fit_nodes_capacity, lca_distance_table
from scripts.grove_lab.shootout import structure_null, triplet_agreement

OUT = Path(__file__).resolve().parents[2] / "docs" / "grove-lab" / "gate72.json"
TRIPLET_SEEDS = 10
N_TRIPLETS = 2000


def _summary(vals: list[float]) -> dict:
    a = np.array([v for v in vals if v is not None], float)
    if not len(a):
        return {"mean": None, "min": None, "max": None, "n_seeds": 0}
    return {
        "mean": round(float(a.mean()), 3),
        "min": round(float(a.min()), 3),
        "max": round(float(a.max()), 3),
        "n_seeds": len(a),
    }


def _fit_nodes_gate(va: np.ndarray, vb: np.ndarray, seed: int):
    """Cross-half triplet agreement on the truncated fit_nodes topology.
    Each side's notes are labeled by its own tree; the other side's
    opinion comes via 1-NN note mapping. Symmetric mean."""
    rng = np.random.default_rng(seed)
    na, ma, _ = fit_nodes_capacity(va)
    nb, mb, _ = fit_nodes_capacity(vb)
    ta, tb = lca_distance_table(na), lca_distance_table(nb)
    ua, ub = _unit(va), _unit(vb)
    lab_a = np.array([ma[i] for i in range(len(va))])
    lab_b = np.array([mb[i] for i in range(len(vb))])
    scores, stats = [], []
    for src_lab, src_t, dst_lab, dst_t, src_u, dst_u in (
        (lab_a, ta, lab_b, tb, ua, ub),
        (lab_b, tb, lab_a, ta, ub, ua),
    ):
        reps = np.argmax(dst_u @ src_u.T, axis=1)
        inherited = src_lab[reps]
        samples = np.array([rng.choice(len(dst_lab), 3, replace=False) for _ in range(N_TRIPLETS)])
        r = _triplets(inherited, src_t, dst_lab, dst_t, samples)
        scores.append(r["agreement"])
        stats.append(r)
    ok = [s for s in scores if s is not None]
    return (
        float(np.mean(ok)) if ok else None,
        {"usable": sum(s["usable"] for s in stats), "ties": sum(s["ties"] for s in stats)},
    )


def main() -> None:
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import pdist

    from scripts.grove_lab.buckets import DEFAULT_CONFIG, assign, load_buckets, resolve_notes
    from ytk.store import _TEXT_MODEL

    cfg = load_buckets(DEFAULT_CONFIG)
    vecs, meta, notes = resolve_notes()
    labels = assign(notes, cfg)
    vecs = np.asarray(vecs)
    out = {"embedding_model": _TEXT_MODEL, "triplet_seeds": TRIPLET_SEEDS, "buckets": {}}

    for i, b in enumerate(cfg.buckets):
        idx = np.flatnonzero(np.array(labels) == i)
        if len(idx) < 2 * MIN_CLUSTER_NOTES:
            out["buckets"][b.name] = {"n": len(idx), "kind": "sapling", "gate": None}
            continue
        dated = sorted((meta[k]["date"], k) for k in idx if meta[k]["date"])
        span = 0
        if len(dated) >= 2:
            span = int(
                (np.datetime64(dated[-1][0]) - np.datetime64(dated[0][0]))
                .astype("timedelta64[D]")
                .astype(int)
            )
        if span >= MIN_SPAN_DAYS:
            kind = "temporal"
            mid = len(dated) // 2
            a = np.array([k for _, k in dated[:mid]])
            bb = np.array([k for _, k in dated[mid:]])
        else:
            kind = "bootstrap"
            perm = np.random.default_rng(3000).permutation(idx)
            a, bb = perm[: len(perm) // 2], perm[len(perm) // 2 :]
        va, vb = vecs[a], vecs[bb]
        Za = linkage(pdist(_unit(va), "cosine"), "average")
        Zb = linkage(pdist(_unit(vb), "cosine"), "average")

        full, nulls, fitn = [], [], []
        used = ties = coll = 0
        fit_stats = {"usable": 0, "ties": 0}
        for s in range(TRIPLET_SEEDS):
            rng = np.random.default_rng(5000 + s)
            score, st = triplet_agreement(Za, va, Zb, vb, rng=rng, return_stats=True)
            full.append(score)
            used += st["used"]
            ties += st["tie_skipped"]
            coll = st["collision_rate"]
            nulls.append(structure_null(Za, va, Zb, vb, rng=rng))
            f_score, f_st = _fit_nodes_gate(va, vb, 6000 + s)
            fitn.append(f_score)
            fit_stats["usable"] += f_st["usable"]
            fit_stats["ties"] += f_st["ties"]
        out["buckets"][b.name] = {
            "n": len(idx),
            "kind": kind,
            "span_days": span,
            "gate": {
                "full_linkage_triplet": _summary(full),
                "structure_null": _summary(nulls),
                "fit_nodes_triplet": _summary(fitn),
                "full_linkage_stats": {
                    "used_total": used,
                    "ties_total": ties,
                    "collision_rate": coll,
                },
                "fit_nodes_stats": fit_stats,
            },
        }
        print(b.name, json.dumps(out["buckets"][b.name]["gate"]))
    OUT.write_text(json.dumps(out, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
