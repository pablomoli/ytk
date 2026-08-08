"""Encode the frozen 156-query eval set with the production Qwen query encoder.

Read-only: nothing is written to the store. Caches
experiments/sae_qwen/data/queries.npz so the faithfulness gate never reloads
the 2.8GB model.

    YTK_VISUAL_INDEX=off uv run python experiments/sae_qwen/encode_queries.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

QUERIES = REPO / "eval" / "retrieval" / "queries.jsonl"


def main() -> None:
    from ytk import store

    rows = [json.loads(x) for x in QUERIES.read_text().splitlines() if x.strip()]
    out = HERE / "data" / "queries.npz"
    Q = np.stack([np.asarray(store._embed_query(r["query"]), dtype=np.float32) for r in rows])
    Q /= np.maximum(np.linalg.norm(Q, axis=1, keepdims=True), 1e-9)
    np.savez_compressed(
        out,
        Q=Q,
        query=np.array([r["query"] for r in rows]),
        gold=np.array([r["gold_id"] for r in rows]),
        bucket=np.array([r["bucket"] for r in rows]),
    )
    print("wrote", out, Q.shape)


if __name__ == "__main__":
    main()
