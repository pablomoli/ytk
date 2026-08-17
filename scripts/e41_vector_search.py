"""E41 — vector search from first principles (#184).

Step 1 (baseline): brute-force exact top-k over the production vectors
vs the same queries through Chroma, per-query p50/p99.

Usage:
    uv run python scripts/e41_vector_search.py baseline
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytk import store

ASSETS = Path(__file__).resolve().parent.parent / "docs" / "assets" / "41-vector-search"
K = 10
N_QUERIES = 200
SEED = 41

BASES = {
    "videos": store._videos_collection,
    "segments": store._segments_collection,
    "memories": store._memories_collection,
}


def _pull_vectors() -> tuple[np.ndarray, list[str], dict[str, int]]:
    mats, ids, counts = [], [], {}
    for name, getter in BASES.items():
        coll = getter()
        got = coll.get(include=["embeddings"])
        emb = np.asarray(got["embeddings"], dtype=np.float32)
        mats.append(emb)
        ids.extend(got["ids"])
        counts[name] = len(got["ids"])
    return np.vstack(mats), ids, counts


def _pctl(samples_ms: list[float]) -> dict[str, float]:
    a = np.asarray(samples_ms)
    return {
        "p50_ms": float(np.percentile(a, 50)),
        "p99_ms": float(np.percentile(a, 99)),
        "mean_ms": float(a.mean()),
    }


def baseline() -> None:
    t0 = time.perf_counter()
    matrix, ids, counts = _pull_vectors()
    pull_s = time.perf_counter() - t0
    n, dim = matrix.shape

    # Cosine space: normalize once so the query loop is a pure dot product.
    normed = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)

    rng = np.random.default_rng(SEED)
    q_idx = rng.choice(n, size=N_QUERIES, replace=False)

    brute_ms: list[float] = []
    for qi in q_idx:
        q = normed[qi]
        t = time.perf_counter()
        scores = normed @ q
        # argpartition beats full sort; k+1 because the query matches itself.
        top = np.argpartition(scores, -(K + 1))[-(K + 1) :]
        top[np.argsort(scores[top])[::-1]]
        brute_ms.append((time.perf_counter() - t) * 1000)

    chroma_ms: list[float] = []
    colls = {name: getter() for name, getter in BASES.items()}
    for qi in q_idx:
        q = matrix[qi].tolist()
        t = time.perf_counter()
        for coll in colls.values():
            coll.query(query_embeddings=[q], n_results=K, include=["distances"])
        chroma_ms.append((time.perf_counter() - t) * 1000)

    out = {
        "stamp": time.strftime("%Y-%m-%d"),
        "step": "baseline",
        "n_vectors": int(n),
        "dim": int(dim),
        "per_collection": counts,
        "matrix_mb": round(matrix.nbytes / 2**20, 1),
        "pull_seconds": round(pull_s, 2),
        "n_queries": N_QUERIES,
        "k": K,
        "brute_force": _pctl(brute_ms),
        "chroma_three_collections": _pctl(chroma_ms),
    }
    ASSETS.mkdir(parents=True, exist_ok=True)
    path = ASSETS / "baseline.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "baseline":
        sys.exit(__doc__)
    baseline()
