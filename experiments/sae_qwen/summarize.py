"""Condense the sweep into the reported table and pick the best config."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def main() -> None:
    runs = json.loads((HERE / "results_sweep.json").read_text())
    by = defaultdict(list)
    for r in runs:
        by[(r["d_sae"], r["k"])].append(r)

    table = []
    print(
        f"{'dict':>5} {'k':>3} {'seed':>4} {'val cos':>8} {'train cos':>9} "
        f"{'gap':>6} {'dead%':>6} {'L0':>5} {'FVU':>6} {'best@':>6} {'in-d':>6} {'ood':>6}"
    )
    for cfg in sorted(by):
        for r in sorted(by[cfg], key=lambda x: x["seed"]):
            v, t = r["val"], r["train"]
            print(
                f"{cfg[0]:>5} {cfg[1]:>3} {r['seed']:>4} {v['recon_cos']:>8.4f} "
                f"{t['recon_cos']:>9.4f} {t['recon_cos'] - v['recon_cos']:>6.4f} "
                f"{100 * r['dead_frac_on_train']:>6.2f} {v['l0']:>5.1f} {v['fvu']:>6.4f} "
                f"{r['best_step']:>6} {r['val_in_dist']['recon_cos']:>6.4f} "
                f"{r['val_out_dist']['recon_cos']:>6.4f}"
            )
        vals = [x["val"]["recon_cos"] for x in by[cfg]]
        dead = [x["dead_frac_on_train"] for x in by[cfg]]
        table.append(
            {
                "d_sae": cfg[0],
                "k": cfg[1],
                "recon_cos_mean": float(np.mean(vals)),
                "recon_cos_sd": float(np.std(vals)),
                "recon_cos_seeds": [round(v, 4) for v in vals],
                "dead_pct_mean": float(100 * np.mean(dead)),
                "dead_pct_seeds": [round(100 * d, 2) for d in dead],
                "l0_mean": float(np.mean([x["val"]["l0"] for x in by[cfg]])),
                "fvu_mean": float(np.mean([x["val"]["fvu"] for x in by[cfg]])),
                "train_val_gap": float(
                    np.mean([x["train"]["recon_cos"] - x["val"]["recon_cos"] for x in by[cfg]])
                ),
                "best_step_mean": float(np.mean([x["best_step"] for x in by[cfg]])),
                "val_in_dist": float(np.mean([x["val_in_dist"]["recon_cos"] for x in by[cfg]])),
                "val_out_dist": float(np.mean([x["val_out_dist"]["recon_cos"] for x in by[cfg]])),
            }
        )
        print(
            f"  -> mean {np.mean(vals):.4f} +- {np.std(vals):.4f}  "
            f"dead {100 * np.mean(dead):.2f}%\n"
        )

    best = max(table, key=lambda r: r["recon_cos_mean"])
    best["checkpoint"] = f"checkpoints/sae_d{best['d_sae']}_k{best['k']}_s0.pt"
    (HERE / "sweep_table.json").write_text(json.dumps(table, indent=1))
    (HERE / "best.json").write_text(json.dumps(best, indent=1))
    print("best:", best["d_sae"], "k", best["k"], f"{best['recon_cos_mean']:.4f}")


if __name__ == "__main__":
    main()
