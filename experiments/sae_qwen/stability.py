"""Are the learned directions the same features across seeds?

For each decoder direction in seed A, the best cosine match in seed B.
A dictionary that reproduces has most directions matching near 1.0; one that
is a convenience basis for a small dataset does not.

    uv run --with torch python experiments/sae_qwen/stability.py
"""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import torch
from paths import CKPT

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def dec(path: Path) -> np.ndarray:
    blob = torch.load(path, map_location="cpu")
    W = blob["state"]["W_dec"].numpy()
    return W / np.maximum(np.linalg.norm(W, axis=1, keepdims=True), 1e-9)


def main() -> None:
    groups = {
        "seed_and_split": (
            "3 seeds, each with its own note-level split",
            [CKPT / f"final_d2048_k32_s{s}.pt" for s in (0, 1, 2)],
        ),
        "init_only": (
            "3 inits on one fixed split (split seed 0)",
            [
                CKPT / "final_d2048_k32_s0.pt",
                CKPT / "fixsplit_d2048_k32_s10.pt",
                CKPT / "fixsplit_d2048_k32_s11.pt",
            ],
        ),
    }
    out = {}
    for prefix, (label, paths) in groups.items():
        Ws = [dec(p) for p in paths]
        pair = []
        for a, b in combinations(range(3), 2):
            M = Ws[a] @ Ws[b].T
            best = M.max(1)
            pair.append(
                {
                    "seeds": f"{a}v{b}",
                    "mean_max_cos": float(best.mean()),
                    "median_max_cos": float(np.median(best)),
                    "frac_above_0.8": float((best > 0.8).mean()),
                    "frac_above_0.5": float((best > 0.5).mean()),
                }
            )
        rng = np.random.default_rng(0)
        R = rng.normal(size=Ws[0].shape).astype(np.float32)
        R /= np.linalg.norm(R, axis=1, keepdims=True)
        null = (Ws[0] @ R.T).max(1)
        out[prefix] = {
            "label": label,
            "pairs": pair,
            "random_null_mean_max_cos": float(null.mean()),
        }

    # do the latents that got named (top-100 by firing frequency) reproduce
    # better than the dictionary as a whole?
    feats = json.loads((HERE / "features.json").read_text())["features"]
    named = [f["feature"] for f in feats][:100]
    Ws = [dec(p) for p in groups["init_only"][1]]
    best01 = (Ws[0] @ Ws[1].T).max(1)
    best02 = (Ws[0] @ Ws[2].T).max(1)
    both = np.minimum(best01, best02)
    out["named_subset"] = {
        "label": "top-100 by firing frequency vs the whole dictionary, init_only pair set",
        "n_named": len(named),
        "named_mean_max_cos": float(both[named].mean()),
        "named_frac_above_0.8": float((both[named] > 0.8).mean()),
        "all_mean_max_cos": float(both.mean()),
        "all_frac_above_0.8": float((both > 0.8).mean()),
        "note": "match must hold against BOTH other inits",
    }
    (HERE / "stability.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
