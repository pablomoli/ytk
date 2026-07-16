"""Gate 1: known-item retrieval eval.

Scores each embedding space on queries.jsonl ({"query", "gold_id", "bucket"}):
a doc's score is the max cosine over its part vectors (production's collapse
rule), metric is hit@1/5/10 overall and per bucket, with a paired bootstrap
delta against the baseline space per query set.

    uv run python experiments/encoder_harness/retrieval_eval.py \
        --spaces gte-small bge-small qwen3-0.6b qwen3-0.6b-384d --baseline gte-small
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from embed import MODELS  # noqa: E402  (same directory)


def hit_ranks(space: dict, queries: list[dict], model_cache: dict) -> list[int]:
    """Rank of the gold doc for each query (0-based; large number = miss)."""
    import numpy as np
    from sentence_transformers import SentenceTransformer

    model_key = space["model_key"]
    cfg = MODELS[model_key]
    if model_key not in model_cache:
        model_cache[model_key] = SentenceTransformer(cfg["hf"])
    model = model_cache[model_key]

    q_texts = [cfg["query_prefix"] + q["query"] for q in queries]
    q = np.asarray(model.encode(q_texts, normalize_embeddings=True), dtype=np.float32)
    if space["dims"] < q.shape[1]:
        q = q[:, : space["dims"]]
        q /= np.linalg.norm(q, axis=1, keepdims=True)

    sims = q @ space["parts"].T  # queries x parts
    id_index = {i: n for n, i in enumerate(space["ids"])}
    ranks: list[int] = []
    part_doc = space["part_doc"]
    n_docs = len(space["ids"])
    for qi, qrow in enumerate(sims):
        doc_best = {}
        for pi, s in enumerate(qrow):
            d = part_doc[pi]
            if s > doc_best.get(d, -2.0):
                doc_best[d] = float(s)
        order = sorted(doc_best, key=doc_best.get, reverse=True)
        gold = id_index.get(queries[qi]["gold_id"], -1)
        ranks.append(order.index(gold) if gold in doc_best else n_docs)
    return ranks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="experiments/encoder_harness/data")
    ap.add_argument("--spaces", nargs="+", required=True)
    ap.add_argument("--baseline", default="gte-small")
    ap.add_argument("--seeds", type=int, default=1000, help="bootstrap resamples")
    args = ap.parse_args()

    import numpy as np

    data = Path(args.data)
    # newline-only iteration: splitlines() would also split on U+2028/U+2029
    with (data / "queries.jsonl").open(encoding="utf-8") as f:
        queries = [json.loads(l) for l in f if l.strip()]

    spaces = {}
    for key in args.spaces:
        z = np.load(data / f"{key}.npz", allow_pickle=False)
        model_key = next(m for m in sorted(MODELS, key=len, reverse=True) if key.startswith(m))
        spaces[key] = {
            "key": key, "model_key": model_key, "parts": z["parts"],
            "part_doc": z["part_doc"], "ids": list(z["ids"]),
            "buckets": list(z["buckets"]), "dims": z["parts"].shape[1],
        }

    cache: dict = {}
    ranks = {key: hit_ranks(sp, queries, cache) for key, sp in spaces.items()}

    def hits(rk: list[int], idx: list[int], k: int) -> float:
        return sum(rk[i] < k for i in idx) / max(len(idx), 1)

    all_idx = list(range(len(queries)))
    bucket_idx = {}
    for i, q in enumerate(queries):
        bucket_idx.setdefault(q["bucket"], []).append(i)

    report = {"n_queries": len(queries), "spaces": {}}
    rng = np.random.default_rng(20260716)
    base = ranks.get(args.baseline)
    for key, rk in ranks.items():
        entry = {
            "hit@1": hits(rk, all_idx, 1), "hit@5": hits(rk, all_idx, 5),
            "hit@10": hits(rk, all_idx, 10),
            "per_bucket": {
                b: {"hit@5": hits(rk, idx, 5), "n": len(idx)}
                for b, idx in bucket_idx.items()
            },
        }
        if base is not None and key != args.baseline:
            deltas = []
            for _ in range(args.seeds):
                sample = rng.integers(0, len(all_idx), len(all_idx))
                deltas.append(hits(rk, list(sample), 5) - hits(base, list(sample), 5))
            lo, hi = np.percentile(deltas, [2.5, 97.5])
            entry["delta_hit@5_vs_baseline"] = {
                "mean": float(np.mean(deltas)), "ci95": [float(lo), float(hi)],
                "significant": bool(lo > 0 or hi < 0),
            }
        report["spaces"][key] = entry

    out = data / "retrieval_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
