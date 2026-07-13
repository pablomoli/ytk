"""Method shootout v2 — the Codex review's settling experiments (F1, F2, F3).

F1: the v1 shootout transferred held-out halves by nearest cluster CENTROID
(2 seeds, no intervals) — an assignment rule that favors compact linkage
clusters over HDBSCAN's density shapes. Here: >= 20 seeds, centroid AND
cosine-kNN transfer, paired per-seed differences with percentile intervals.

F2: flat-partition ARI does not validate a hierarchy. Added: sampled triplet
agreement between half-fit dendrograms (do the two trees agree which pair of
a random triplet is cophenetically closest? chance = 1/3), with a
shuffled-mapping baseline.

F3/Q5: ai-building's temporal non-stationarity gets a composition check —
category mixture per temporal half, since source-mix change is a rival
explanation to semantic drift.

Artifact: docs/grove-lab/shootout-v2.json (versioned, embedding model
stamped). Usage:
    uv run --extra dev --with hdbscan python -m scripts.grove_lab.shootout
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

BUCKETS = ("epicmap", "ai-building", "visual-craft")
SEEDS = 20
TRIPLET_SEEDS = 10
KNN = 5

OUT = Path(__file__).resolve().parents[2] / "docs" / "grove-lab" / "shootout-v2.json"


def _unit(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=1, keepdims=True).clip(1e-12)


# --------------------------------------------------------------------------
# pure functions (tested)
# --------------------------------------------------------------------------

def knn_transfer(src: np.ndarray, src_labels: np.ndarray, dst: np.ndarray, k: int = KNN) -> np.ndarray:
    """Label dst points by majority vote of their k nearest src neighbors
    (cosine). Method-neutral: no centroid-compactness assumption."""
    sims = _unit(dst) @ _unit(src).T
    out = np.empty(len(dst), dtype=src_labels.dtype)
    kk = min(k, sims.shape[1])
    for i, row in enumerate(sims):
        top = np.argpartition(row, -kk)[-kk:]
        votes = Counter(src_labels[top].tolist())
        out[i] = votes.most_common(1)[0][0]
    return out


def triplet_agreement(Za, va, Zb, vb, n_triplets: int = 2000, rng=None) -> float:
    """Hierarchy-aware cross-half agreement. B's points are mapped to their
    nearest A point; for random triplets of B, do both dendrograms pick the
    same cophenetically-closest pair? Chance floor is 1/3."""
    from scipy.cluster.hierarchy import cophenet
    from scipy.spatial.distance import squareform

    rng = rng if rng is not None else np.random.default_rng(0)
    Ca = squareform(cophenet(Za))
    Cb = squareform(cophenet(Zb))
    reps = np.argmax(_unit(vb) @ _unit(va).T, axis=1)
    n = len(vb)
    hits = total = 0
    for _ in range(n_triplets):
        i, j, k = rng.choice(n, 3, replace=False)
        pairs = ((i, j), (i, k), (j, k))
        db = [Cb[p, q] for p, q in pairs]
        if len(set(db)) < 2:
            continue
        da = [Ca[reps[p], reps[q]] for p, q in pairs]
        hits += int(int(np.argmin(db)) == int(np.argmin(da)))
        total += 1
    return hits / max(1, total)


# --------------------------------------------------------------------------
# fitting + scoring
# --------------------------------------------------------------------------

def fit_agglo(v: np.ndarray) -> np.ndarray:
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    Z = linkage(pdist(_unit(v), "cosine"), "average")
    return fcluster(Z, max(3, len(v) // 120), criterion="maxclust")


def fit_hdb(v: np.ndarray) -> np.ndarray:
    import hdbscan

    return hdbscan.HDBSCAN(
        min_cluster_size=max(5, len(v) // 60), min_samples=5
    ).fit_predict(_unit(v).astype(np.float64))


def centroid_transfer(src, src_labels, dst) -> np.ndarray:
    ids = np.array(sorted(set(src_labels.tolist())))
    us = _unit(src)
    cents = _unit(np.array([us[src_labels == i].mean(0) for i in ids]))
    return ids[np.argmax(_unit(dst) @ cents.T, axis=1)]


def transfer_ari(va, vb, fit, transfer) -> float:
    """Cross-half ARI, both directions averaged. Noise points (-1) are
    excluded from voting AND from scoring — identically for every method."""
    from sklearn.metrics import adjusted_rand_score

    scores = []
    for src, dst in ((va, vb), (vb, va)):
        ls, ld = fit(src), fit(dst)
        src_ok, dst_ok = ls != -1, ld != -1
        if len(set(ls[src_ok].tolist())) < 2 or len(set(ld[dst_ok].tolist())) < 2:
            return float("nan")
        inherited = transfer(src[src_ok], ls[src_ok], dst[dst_ok])
        scores.append(adjusted_rand_score(ld[dst_ok], inherited))
    return float(np.mean(scores))


def _halves(idx: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray]:
    perm = rng.permutation(len(idx))
    return idx[perm[: len(perm) // 2]], idx[perm[len(perm) // 2 :]]


def _temporal_halves(idx, meta):
    dated = sorted((meta[k]["date"], k) for k in idx if meta[k]["date"])
    mid = len(dated) // 2
    return (np.array([k for _, k in dated[:mid]]),
            np.array([k for _, k in dated[mid:]]))


def _ci(vals: list[float]) -> dict:
    a = np.array([v for v in vals if not np.isnan(v)])
    if len(a) == 0:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    return {"mean": round(float(a.mean()), 3),
            "lo": round(float(np.percentile(a, 2.5)), 3),
            "hi": round(float(np.percentile(a, 97.5)), 3), "n": int(len(a))}


def main() -> None:
    import warnings

    warnings.filterwarnings("ignore")
    from scripts.grove_lab.buckets import DEFAULT_CONFIG, assign, load_buckets, resolve_notes
    from ytk.store import _TEXT_MODEL

    cfg = load_buckets(DEFAULT_CONFIG)
    vecs, meta, notes = resolve_notes()
    labels = assign(notes, cfg)
    bucket_idx = {
        b.name: np.array([k for k, x in enumerate(labels) if x == i])
        for i, b in enumerate(cfg.buckets) if b.name in BUCKETS
    }

    methods = {"agglo-cos": fit_agglo, "hdb-native": fit_hdb}
    transfers = {"centroid": centroid_transfer, "knn5": knn_transfer}
    results: dict = {"embedding_model": _TEXT_MODEL, "seeds": SEEDS, "cells": {}, "paired_diff": {}}

    print(f"RANDOM-HALF TRANSFER ARI - {SEEDS} seeds, mean [95% interval]")
    header = f"{'bucket':<14}" + "".join(f"{m}/{t:<10}".rjust(22) for m in methods for t in transfers)
    print(header)
    per_seed: dict = {}
    for name, idx in bucket_idx.items():
        row = f"{name:<14}"
        for m, fit in methods.items():
            for t, tr in transfers.items():
                vals = []
                for s in range(SEEDS):
                    a, b = _halves(idx, np.random.default_rng(1000 + s))
                    vals.append(transfer_ari(vecs[a], vecs[b], fit, tr))
                per_seed[(name, m, t)] = vals
                c = _ci(vals)
                results["cells"][f"{name}|{m}|{t}"] = c
                row += f"{c['mean']:>7.3f} [{c['lo']:.2f},{c['hi']:.2f}]"
        print(row)

    print("\nPAIRED per-seed difference agglo - hdbscan (same halves), by transfer rule")
    for name in bucket_idx:
        for t in transfers:
            diffs = [x - y for x, y in zip(per_seed[(name, "agglo-cos", t)],
                                           per_seed[(name, "hdb-native", t)])
                     if not (np.isnan(x) or np.isnan(y))]
            c = _ci(diffs)
            results["paired_diff"][f"{name}|{t}"] = c
            verdict = "agglo wins" if (c["lo"] or 0) > 0 else ("hdb wins" if (c["hi"] or 0) < 0 else "interval spans 0")
            print(f"  {name:<14} {t:<9} diff {c['mean']:>6} [{c['lo']},{c['hi']}]  {verdict}")

    print("\nTEMPORAL split (deterministic), agglo, both transfer rules")
    for name, idx in bucket_idx.items():
        a, b = _temporal_halves(idx, meta)
        for t, tr in transfers.items():
            v = transfer_ari(vecs[a], vecs[b], fit_agglo, tr)
            results["cells"][f"{name}|agglo-cos|{t}|temporal"] = round(v, 3)
            print(f"  {name:<14} {t:<9} {v:.3f}")

    print(f"\nTRIPLET AGREEMENT (hierarchy-aware, chance=0.33) - {TRIPLET_SEEDS} seeds")
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import pdist

    for name, idx in bucket_idx.items():
        agr, base = [], []
        for s in range(TRIPLET_SEEDS):
            rng = np.random.default_rng(2000 + s)
            a, b = _halves(idx, rng)
            va, vb = vecs[a], vecs[b]
            Za = linkage(pdist(_unit(va), "cosine"), "average")
            Zb = linkage(pdist(_unit(vb), "cosine"), "average")
            agr.append(triplet_agreement(Za, va, Zb, vb, rng=rng))
            base.append(triplet_agreement(Za, va, Zb, vb[rng.permutation(len(vb))], rng=rng))
        ca, cb = _ci(agr), _ci(base)
        results["cells"][f"{name}|triplet"] = {"agreement": ca, "shuffled": cb}
        print(f"  {name:<14} agreement {ca['mean']} [{ca['lo']},{ca['hi']}]   shuffled {cb['mean']}")

    print("\nAI-BUILDING temporal-half composition (F3/Q5: mixture vs drift)")
    idx = bucket_idx["ai-building"]
    a, b = _temporal_halves(idx, meta)
    comp = {}
    for tag, half in (("early", a), ("late", b)):
        c = Counter(meta[k]["cat"] for k in half)
        total = sum(c.values())
        comp[tag] = {k: round(v / total, 3) for k, v in c.most_common()}
        print(f"  {tag:<6} n={total}  " + ", ".join(f"{k} {v:.0%}" for k, v in comp[tag].items()))
    results["ai_building_composition"] = comp

    OUT.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
