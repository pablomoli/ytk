"""Section 53 disclosed metrics that need no model call: sampler separations
under 20 seeds, with paired intervals, written as a sidecar next to the figures.

    uv run python scripts/lsd_seeds.py --out docs/assets/53-lsd/seeds.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ytk import lsd

SEEDS = 20


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()
    notes, X = lsd.load_notes()
    Xc, mean_norm = lsd.centre(X)
    rows = []
    for seed in range(SEEDS):
        rng = np.random.default_rng(1000 + seed)
        bg = lsd.background_cosines(Xc, rng)
        sd = float(bg.std())
        tail = float(np.percentile(bg, lsd.TAIL_PCT))
        med = {}
        hubmax = {}
        for pool in lsd.POOLS:
            pairs = lsd.sample_pairs(X, Xc, pool, args.n, rng, tail)
            med[pool] = float(np.median([p.cos_c for p in pairs]))
            counts = np.bincount([p.i for p in pairs] + [p.j for p in pairs], minlength=len(notes))
            hubmax[pool] = int(counts.max())
        floor = float(np.percentile(bg, 0.5))
        keep = rng.random(len(bg)) < lsd.tilt_acceptance(bg, floor, sd)
        rows.append(
            {
                "seed": 1000 + seed,
                "background_std": sd,
                "tail": tail,
                "ortho_below_rand_std": (med["rand"] - med["ortho"]) / sd,
                "near_above_rand_std": (med["near"] - med["rand"]) / sd,
                "tilt_shift_std": (float(np.median(bg)) - float(np.median(bg[keep]))) / sd,
                "tail_shift_std": (float(np.median(bg)) - float(np.median(bg[bg <= tail]))) / sd,
                "max_draws": hubmax,
            }
        )
    keys = [
        "ortho_below_rand_std",
        "near_above_rand_std",
        "tilt_shift_std",
        "tail_shift_std",
        "background_std",
        "tail",
    ]
    summary = {
        k: {
            "mean": float(np.mean([r[k] for r in rows])),
            "p2.5": float(np.percentile([r[k] for r in rows], 2.5)),
            "p97.5": float(np.percentile([r[k] for r in rows], 97.5)),
        }
        for k in keys
    }
    summary["max_draws_any_pool"] = max(max(r["max_draws"].values()) for r in rows)
    out = Path(args.out)
    out.write_text(
        json.dumps(
            {
                "n_notes": len(notes),
                "mean_norm": mean_norm,
                "seeds": SEEDS,
                "summary": summary,
                "rows": rows,
            },
            indent=1,
        )
    )
    for k, v in summary.items():
        print(k, v)


if __name__ == "__main__":
    main()
