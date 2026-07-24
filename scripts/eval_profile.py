"""Leave-out retrieval eval for the taste profile (issue #16, E3).

Protocol: 5-fold CV over deliberate saves (r >= 1). Each fold holds out its
test saves AND a fold of passive decoys (decoys must not be in the trained
profile — leaving them in biases the eval against multi-centroid profiles,
since every decoy then sits near its own theme centroid). The profile built
from the remaining notes ranks the held-out pool by max cosine to any theme
centroid; metrics are mean rank percentile (lower better) and top-5 hit-rate.

Run: uv run python scripts/eval_profile.py [--alphas 0,1,3,7,15,31,63]

Known confound (2026-07-05): saves are almost all Instagram, passives all
YouTube, so part of the signal may be source style. Re-run once cross-source
saves (hub-ingested YouTube with thoughts) exist.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from ytk import signals
from ytk.config import load_config
from ytk.store import get_all_videos, get_content_memories
from ytk.synthesis import choose_k, cluster_embeddings, weighted_centroid

FOLDS = 5
TOP_N = 5


def run(alphas: list[float]) -> list[dict]:
    cfg = load_config()
    notes = [
        n
        for n in get_all_videos() + get_content_memories(cfg.interest.content_sources)
        if n.get("embedding")
    ]
    emb = np.array([n["embedding"] for n in notes], dtype=float)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    levels = signals.signal_levels(notes)
    saves = [i for i, r in enumerate(levels) if r >= 1]
    passive = [i for i, r in enumerate(levels) if r == 0]
    print(f"notes={len(notes)} saves={len(saves)} passive={len(passive)}")

    rng = np.random.default_rng(0)
    sfolds = np.array_split(rng.permutation(saves), FOLDS)
    pfolds = np.array_split(rng.permutation(passive), FOLDS)

    def condition(alpha: float, multi: bool) -> dict:
        pct, hits, total = [], 0, 0
        for sf, pf in zip(sfolds, pfolds):
            test, decoys = [int(x) for x in sf], [int(x) for x in pf]
            held = set(test) | set(decoys)
            train = [i for i in range(len(notes)) if i not in held]
            w = [1.0 + alpha * levels[i] for i in train]
            k = choose_k(len(train), cfg.interest) if multi else 1
            labels = (
                cluster_embeddings(emb[train], k, sample_weight=w) if multi else [0] * len(train)
            )
            cents = []
            for c in set(labels):
                idx = [train[j] for j, l in enumerate(labels) if l == c]
                cents.append(weighted_centroid(emb[idx], [1.0 + alpha * levels[i] for i in idx]))
            pool = test + decoys
            scores = (emb[pool] @ np.array(cents).T).max(axis=1)
            order = np.argsort(-scores)
            pos = {int(p): r for r, p in enumerate(order)}
            for t in range(len(test)):
                pct.append(pos[t] / len(pool))
                hits += pos[t] < TOP_N
                total += 1
        return {"mean_pct": float(np.mean(pct)), f"top{TOP_N}": hits / total}

    results = []
    for alpha in alphas:
        for multi in (False, True):
            r = condition(alpha, multi)
            results.append({"alpha": alpha, "multi": multi, **r})
            print(
                f"alpha={alpha:>5} {'multi ' if multi else 'single'}: "
                f"mean_pct={r['mean_pct']:.3f} top{TOP_N}={r[f'top{TOP_N}']:.2f}"
            )
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alphas", default="0,1,3,7,15,31,63")
    ap.add_argument("--out", default=None, help="optional JSON output path")
    args = ap.parse_args()
    res = run([float(a) for a in args.alphas.split(",")])
    if args.out:
        json.dump(res, open(args.out, "w"), indent=2)
