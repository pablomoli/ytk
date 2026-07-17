"""Derive an MRL-truncated space from an existing npz without re-encoding.

Truncation + renormalize is exactly what embed.py --dims does post-encode,
so the result is bit-identical to a fresh run at a fraction of the cost.

    uv run python experiments/encoder_harness/derive_truncated.py --src qwen3-0.6b --dims 384
"""
import argparse
import json
from pathlib import Path

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--dims", type=int, required=True)
ap.add_argument("--data", default="experiments/encoder_harness/data")
args = ap.parse_args()

data = Path(args.data)
z = np.load(data / f"{args.src}.npz", allow_pickle=False)
key = f"{args.src}-{args.dims}d"


def trunc(a):
    a = a[:, : args.dims].copy()
    a /= np.linalg.norm(a, axis=1, keepdims=True)
    return a


np.savez_compressed(
    data / f"{key}.npz",
    reps=trunc(z["reps"]), parts=trunc(z["parts"]),
    part_doc=z["part_doc"], ids=z["ids"], buckets=z["buckets"],
)
src_bench = json.loads((data / f"{args.src}.bench.json").read_text())
src_bench.update(key=key, dims=args.dims, derived_from=args.src)
(data / f"{key}.bench.json").write_text(json.dumps(src_bench, indent=2))
print(json.dumps({"key": key, "dims": args.dims, "reps": z["reps"].shape[0]}))
