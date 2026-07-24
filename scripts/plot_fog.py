"""Ground-truth matplotlib view of the map's 3D density artifacts.

Reads ~/.ytk/map.json (the exact payload the hub serves) and renders the
fog splats, the threshold sweep, and the filament web — independent of the
WebGL renderer, so data bugs and shader bugs can be told apart.

Run:  uv run --with matplotlib python scripts/plot_fog.py [--view all]
Writes fog-<view>.png next to the repo (or --out).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", choices=("all", "content"), default="all")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = json.loads(Path(os.path.expanduser("~/.ytk/map.json")).read_text())
    layer = data[args.view]
    splats = np.asarray(layer["fog"]["splats"])
    filaments = [np.asarray(f) for f in layer.get("web", {}).get("filaments", [])]
    xyz, den = splats[:, :3], splats[:, 3]

    plt.style.use("dark_background")
    fig = plt.figure(figsize=(16, 12))
    fig.suptitle(
        f"{args.view} view - {len(splats)} fog splats, {len(filaments)} filaments "
        f"(h={layer['fog']['h']})",
        fontsize=11,
    )

    def scatter(ax, mask, title):
        ax.scatter(
            xyz[mask, 0], xyz[mask, 1], xyz[mask, 2],
            c=den[mask], cmap="magma", vmin=0, vmax=1,
            s=6 + 40 * den[mask], alpha=0.35, linewidths=0,
        )
        ax.set_title(f"{title}  ({int(mask.sum())} splats)", fontsize=10)
        ax.set_xlim(-1, 1); ax.set_ylim(-1, 1); ax.set_zlim(-1, 1)
        ax.set_axis_off()

    # 1: the whole cloud; 2-3: the threshold sweep (nucleation story)
    for k, (level, title) in enumerate(
        [(0.0, "full fog"), (0.25, "level 0.25 - haze gone"), (0.5, "level 0.5 - cores nucleate")]
    ):
        scatter(fig.add_subplot(2, 2, k + 1, projection="3d"), den >= level, title)

    # 4: fog thinned + filament web overlay
    ax = fig.add_subplot(2, 2, 4, projection="3d")
    scatter(ax, den >= 0.15, "fog + filament web")
    for fil in filaments:
        ax.plot(fil[:, 0], fil[:, 1], fil[:, 2], color="#e2b04a", linewidth=1.4, alpha=0.9)

    out = args.out or f"fog-{args.view}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=110, facecolor="#0b0b0b")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
