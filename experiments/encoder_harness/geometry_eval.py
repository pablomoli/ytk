"""Gate 2: geometry stability between embedding spaces.

Two metrics over representative vectors, both against a baseline space:
  - knn_jaccard: mean Jaccard overlap of each doc's 10-NN set — how much of
    the local neighborhood structure survives the model change.
  - triplet_agreement: fraction of (anchor, same-bucket, other-bucket)
    triplets where the anchor is closer to its own bucket. Buckets are
    provenance categories (grove discipline: authored/provenance grouping,
    never inferred topics). Reported per space with paired bootstrap deltas
    across 20+ seeds, per the grove-experiments rule.

    uv run python experiments/encoder_harness/geometry_eval.py \
        --spaces gte-small qwen3-0.6b qwen3-0.6b-384d --baseline gte-small
"""

import argparse
import json
from pathlib import Path


def category(doc_id: str, bucket: str) -> str:
    """Provenance category: bucket, refined by vault subdir for memories."""
    if bucket != "memories":
        return bucket
    rel = doc_id.split("::", 1)[1]
    parts = rel.split("/")
    if parts[0] == "sources" and len(parts) > 1:
        return f"src-{parts[1]}"
    if parts[:2] == ["inbox", "memories"] and len(parts) > 3:
        return f"proj-{parts[2]}"  # per-project atom folder
    return parts[0] if len(parts) > 1 else "misc"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="experiments/encoder_harness/data")
    ap.add_argument("--spaces", nargs="+", required=True)
    ap.add_argument("--baseline", default="gte-small")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--seeds", type=int, default=25)
    ap.add_argument("--triplets", type=int, default=4000, help="per seed")
    args = ap.parse_args()

    import numpy as np

    data = Path(args.data)
    spaces = {}
    for key in args.spaces:
        z = np.load(data / f"{key}.npz", allow_pickle=False)
        spaces[key] = {"reps": z["reps"], "ids": list(z["ids"]), "buckets": list(z["buckets"])}

    base = spaces[args.baseline]
    ids = base["ids"]
    cats = [category(i, b) for i, b in zip(ids, base["buckets"])]
    n = len(ids)
    by_cat: dict[str, list[int]] = {}
    for i, c in enumerate(cats):
        by_cat.setdefault(c, []).append(i)
    eligible = {c: idx for c, idx in by_cat.items() if len(idx) >= 5}
    if len(eligible) < 2:
        raise SystemExit(f"need >=2 categories with >=5 docs for triplets, got {list(eligible)}")

    def knn_sets(reps, k):
        sims = reps @ reps.T
        np.fill_diagonal(sims, -2.0)
        nn = np.argpartition(-sims, k, axis=1)[:, :k]
        return [set(row.tolist()) for row in nn]

    base_nn = knn_sets(base["reps"], args.k)

    # one shared triplet sample per seed -> paired comparisons across spaces
    def sample_triplets(rng):
        out = []
        cat_keys = list(eligible)
        for _ in range(args.triplets):
            c = cat_keys[rng.integers(len(cat_keys))]
            a, p = rng.choice(eligible[c], 2, replace=False)
            while True:
                x = int(rng.integers(n))
                if cats[x] != c:
                    break
            out.append((int(a), int(p), x))
        return out

    seeds = [np.random.default_rng(20260716 + s) for s in range(args.seeds)]
    triplet_sets = [sample_triplets(r) for r in seeds]

    report = {
        "n_docs": n,
        "categories": {c: len(v) for c, v in eligible.items()},
        "k": args.k,
        "seeds": args.seeds,
        "spaces": {},
    }

    per_space_scores: dict[str, list[float]] = {}
    ordered = [args.baseline] + [k for k in spaces if k != args.baseline]
    for key in ordered:
        sp = spaces[key]
        reps = sp["reps"]
        assert sp["ids"] == ids, f"{key}: id order mismatch with baseline"
        sims = reps @ reps.T
        scores = []
        for tris in triplet_sets:
            ok = sum(sims[a, p] > sims[a, x] for a, p, x in tris)
            scores.append(ok / len(tris))
        per_space_scores[key] = scores
        entry = {
            "triplet_agreement_mean": float(np.mean(scores)),
            "triplet_agreement_std": float(np.std(scores)),
        }
        if key != args.baseline:
            nn = knn_sets(reps, args.k)
            jac = [len(a & b) / len(a | b) for a, b in zip(base_nn, nn)]
            entry["knn_jaccard_mean"] = float(np.mean(jac))
            deltas = [s - b for s, b in zip(scores, per_space_scores[args.baseline])]
            lo, hi = np.percentile(deltas, [2.5, 97.5])
            entry["delta_triplet_vs_baseline"] = {
                "mean": float(np.mean(deltas)),
                "ci95": [float(lo), float(hi)],
                "significant": bool(lo > 0 or hi < 0),
            }
        report["spaces"][key] = entry

    out = data / "geometry_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
