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
    ap.add_argument(
        "--shell",
        action="store_true",
        help="rung-09 witness: thickened level sets |den - level| < eps instead of the threshold sweep",
    )
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
            xyz[mask, 0],
            xyz[mask, 1],
            xyz[mask, 2],
            c=den[mask],
            cmap="magma",
            vmin=0,
            vmax=1,
            s=6 + 40 * den[mask],
            alpha=0.35,
            linewidths=0,
        )
        ax.set_title(f"{title}  ({int(mask.sum())} splats)", fontsize=10)
        ax.set_xlim(-1, 1)
        ax.set_ylim(-1, 1)
        ax.set_zlim(-1, 1)
        ax.set_axis_off()

    if args.shell:
        # Rung 09: pseudo-isosurface shells. The band |den - level| < eps is
        # the thickened level set f^-1(level) +/- eps, i.e. the Monte-Carlo
        # preview of the marching-cubes isosurface. eps must match the
        # shader's band half-width in mapRenderer.ts (fogFragment).
        eps, level = 0.06, 0.35
        scatter(fig.add_subplot(2, 2, 1, projection="3d"), den >= level, f"fill: den >= {level}")
        scatter(
            fig.add_subplot(2, 2, 2, projection="3d"),
            np.abs(den - level) < eps,
            f"shell: |den - {level}| < {eps}",
        )
        # onion nesting: three shells, one hue each, painted flat (not by den)
        ax = fig.add_subplot(2, 2, 3, projection="3d")
        for lvl, color in [(0.15, "#4a7de2"), (0.35, "#e2b04a"), (0.6, "#e24a6b")]:
            mask = np.abs(den - lvl) < eps
            ax.scatter(
                xyz[mask, 0],
                xyz[mask, 1],
                xyz[mask, 2],
                color=color,
                s=5,
                alpha=0.3,
                linewidths=0,
                label=f"level {lvl}",
            )
        ax.set_title("nested shells (onion layers)", fontsize=10)
        ax.set_xlim(-1, 1)
        ax.set_ylim(-1, 1)
        ax.set_zlim(-1, 1)
        ax.set_axis_off()
        ax.legend(loc="upper left", fontsize=8)
        # cross-section slab: hollowness shows as rings around the density cores
        ax = fig.add_subplot(2, 2, 4)
        slab = np.abs(xyz[:, 2]) < 0.12
        ring = slab & (np.abs(den - level) < eps)
        core = slab & (den >= level + eps)
        ax.scatter(xyz[slab, 0], xyz[slab, 1], color="#333", s=3, alpha=0.25, linewidths=0)
        ax.scatter(
            xyz[core, 0],
            xyz[core, 1],
            color="#7a4ae2",
            s=5,
            alpha=0.5,
            linewidths=0,
            label="interior (den > level+eps)",
        )
        ax.scatter(
            xyz[ring, 0],
            xyz[ring, 1],
            color="#e2b04a",
            s=7,
            alpha=0.7,
            linewidths=0,
            label="shell band",
        )
        ax.set_title("cross-section |z| < 0.12: shells ring the cores", fontsize=10)
        ax.set_xlim(-1, 1)
        ax.set_ylim(-1, 1)
        ax.set_aspect("equal")
        ax.set_axis_off()
        ax.legend(loc="upper left", fontsize=8)
    else:
        # 1: the whole cloud; 2-3: the threshold sweep (nucleation story)
        for k, (level, title) in enumerate(
            [
                (0.0, "full fog"),
                (0.25, "level 0.25 - haze gone"),
                (0.5, "level 0.5 - cores nucleate"),
            ]
        ):
            scatter(fig.add_subplot(2, 2, k + 1, projection="3d"), den >= level, title)

        # 4: fog thinned + filament web overlay
        ax = fig.add_subplot(2, 2, 4, projection="3d")
        scatter(ax, den >= 0.15, "fog + filament web")
        for fil in filaments:
            ax.plot(fil[:, 0], fil[:, 1], fil[:, 2], color="#e2b04a", linewidth=1.4, alpha=0.9)

    out = args.out or f"fog-{'shell-' if args.shell else ''}{args.view}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=110, facecolor="#0b0b0b")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
