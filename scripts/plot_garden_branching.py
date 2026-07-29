"""Branching geometry of a real garden skeleton, for docs/assets/14-garden-allometry/.

Two observations to settle: limbs leave the trunk at what looks like a right
angle, and every limb stays bare for the first half of its length before twigs
start -- the same proportion at every level, so the tree reads as nested copies
of itself instead of a tree.

Plots the skeleton the renderer actually builds. Dump it first:

    cd web && node .gdump/dump.mjs 6970 epicmap /tmp/skeleton-epicmap.json
    uv run --with matplotlib python scripts/plot_garden_branching.py

The dump imports web/src/lib/garden compiled by tsc, so this cannot drift from
the renderer the way a reimplementation would.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from plot_assets import BG, CYAN, DIM, FRAME, GOLD, MUTED, PANEL, RED, TEXT, use_house_font

use_house_font()

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "14-garden-allometry"
SRC = Path("/tmp/skeleton-epicmap.json")
DPI = 200
ORDER_COLOURS = [TEXT, GOLD, CYAN, RED, "#9159ff", "#7fd4ff"]


def load() -> dict:
    return json.loads(SRC.read_text())


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    data = load()
    nodes = data["nodes"]
    by_id = {n["id"]: n for n in nodes}
    kids = defaultdict(list)
    for n in nodes:
        if n["parent"] >= 0:
            kids[n["parent"]].append(n["id"])

    def radial(n: dict) -> float:
        r = math.hypot(n["x"], n["z"])
        return r if n["x"] >= 0 else -r

    fig = plt.figure(figsize=(17.2, 6.6), facecolor=BG)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.0, 1.05], wspace=0.26)

    # --- A: skeleton in the up/lateral plane ------------------------------
    ax = fig.add_subplot(gs[0])
    ax.set_facecolor(PANEL)
    for n in nodes:
        p = n["parent"]
        if p < 0:
            continue
        par = by_id[p]
        o = min(n["order"], len(ORDER_COLOURS) - 1)
        ax.plot(
            [radial(par), radial(n)],
            [par["y"], n["y"]],
            color=ORDER_COLOURS[o],
            linewidth=max(0.35, 2.6 - 0.5 * o),
            alpha=0.85 if o <= 1 else 0.42,
            solid_capstyle="round",
        )
    env = data["env"]
    ax.add_patch(
        plt.matplotlib.patches.Ellipse(
            (0, env["cy"]),
            env["radius"] * 2,
            env["halfHeight"] * 2,
            fill=False,
            edgecolor=MUTED,
            linestyle=(0, (5, 5)),
            linewidth=0.9,
            alpha=0.5,
        )
    )
    ax.set_xlabel("lateral distance from the trunk axis", color=MUTED, fontsize=10)
    ax.set_ylabel("height (the tree's up axis)", color=MUTED, fontsize=10)
    ax.set_title("A. skeleton, up against lateral", color=TEXT, fontsize=12.5, pad=10)
    ax.set_aspect("equal")
    ax.tick_params(colors=MUTED, labelsize=8.4)
    for s in ax.spines.values():
        s.set_color(FRAME)
    ax.grid(True, color=DIM, linewidth=0.5, alpha=0.35)

    # --- B: departure angle from vertical, at each fork -------------------
    ax2 = fig.add_subplot(gs[1])
    ax2.set_facecolor(PANEL)
    angles: dict[int, list[float]] = defaultdict(list)
    for n in nodes:
        p = n["parent"]
        if p < 0:
            continue
        par = by_id[p]
        if n["order"] <= par["order"]:
            continue  # only measure the lateral child at a fork
        dx, dy, dz = n["x"] - par["x"], n["y"] - par["y"], n["z"] - par["z"]
        horiz = math.hypot(dx, dz)
        angles[n["order"]].append(math.degrees(math.atan2(horiz, dy)))
    orders = sorted(angles)
    parts = ax2.violinplot(
        [angles[o] for o in orders],
        positions=orders,
        widths=0.72,
        showextrema=False,
        showmedians=True,
    )
    for i, b in enumerate(parts["bodies"]):
        b.set_facecolor(ORDER_COLOURS[min(orders[i], len(ORDER_COLOURS) - 1)])
        b.set_alpha(0.55)
    parts["cmedians"].set_color(TEXT)
    ax2.axhline(90, color=RED, linewidth=1.2, alpha=0.8)
    ax2.text(max(orders) + 0.1, 91, "orthogonal", color=RED, fontsize=9, ha="right")
    ax2.set_xlabel("branch order of the departing limb", color=MUTED, fontsize=10)
    ax2.set_ylabel("angle from vertical, degrees", color=MUTED, fontsize=10)
    ax2.set_title("B. how limbs leave their parent", color=TEXT, fontsize=12.5, pad=10)
    ax2.set_xticks(orders)
    ax2.tick_params(colors=MUTED, labelsize=8.6)
    for s in ax2.spines.values():
        s.set_color(FRAME)
    ax2.grid(True, color=DIM, linewidth=0.5, alpha=0.35)

    # --- C: how far along a limb before it carries anything ---------------
    ax3 = fig.add_subplot(gs[2])
    ax3.set_facecolor(PANEL)
    bare: dict[int, list[float]] = defaultdict(list)
    for n in nodes:
        # limb start: a node whose order exceeds its parent's
        p = n["parent"]
        if p < 0 or n["order"] <= by_id[p]["order"]:
            continue
        order = n["order"]
        start_path = n["path"]
        cur, end_path, first_child = n, n["path"], None
        while True:
            same = [c for c in kids[cur["id"]] if by_id[c]["order"] == order]
            higher = [c for c in kids[cur["id"]] if by_id[c]["order"] > order]
            if higher and first_child is None:
                first_child = cur["path"]
            if not same:
                end_path = cur["path"]
                break
            cur = by_id[same[0]]
        span = end_path - start_path
        if span > 1e-6 and first_child is not None:
            bare[order].append((first_child - start_path) / span)
    orders3 = sorted(k for k in bare if len(bare[k]) >= 3)
    if orders3:
        parts3 = ax3.violinplot(
            [bare[o] for o in orders3],
            positions=orders3,
            widths=0.72,
            showextrema=False,
            showmedians=True,
        )
        for i, b in enumerate(parts3["bodies"]):
            b.set_facecolor(ORDER_COLOURS[min(orders3[i], len(ORDER_COLOURS) - 1)])
            b.set_alpha(0.55)
        parts3["cmedians"].set_color(TEXT)
    ax3.set_ylim(0, 1)
    ax3.set_xlabel("branch order", color=MUTED, fontsize=10)
    ax3.set_ylabel("fraction of the limb that is bare", color=MUTED, fontsize=10)
    ax3.set_title("C. bare length before the first branch", color=TEXT, fontsize=12.5, pad=10)
    ax3.set_xticks(orders3)
    ax3.tick_params(colors=MUTED, labelsize=8.6)
    for s in ax3.spines.values():
        s.set_color(FRAME)
    ax3.grid(True, color=DIM, linewidth=0.5, alpha=0.35)

    fig.suptitle(
        f"Garden branching geometry: {data['bucket']}, {len(nodes)} real nodes",
        color=TEXT,
        fontsize=16,
        y=1.0,
    )
    med = {o: float(np.median(angles[o])) for o in orders}
    medbare = {o: float(np.median(bare[o])) for o in orders3}
    fig.text(
        0.5,
        -0.04,
        "Median departure angle by order: "
        + ",  ".join(f"{o}: {v:.0f} deg" for o, v in med.items())
        + "\nMedian bare fraction by order: "
        + ",  ".join(f"{o}: {v:.2f}" for o, v in medbare.items())
        + "  -- a flat profile means every level repeats the same proportion.",
        color=MUTED,
        fontsize=10.2,
        ha="center",
        linespacing=1.8,
    )

    out = OUTDIR / "09-branching-geometry.png"
    fig.savefig(out, dpi=DPI, facecolor=BG, bbox_inches="tight")
    print(f"wrote {out}")
    for o in orders:
        a = np.array(angles[o])
        print(
            f"  order {o}: n={len(a):>5}  angle median {np.median(a):6.1f}  "
            f"p10 {np.percentile(a, 10):6.1f}  p90 {np.percentile(a, 90):6.1f}"
        )
    for o in orders3:
        b = np.array(bare[o])
        print(
            f"  order {o}: n={len(b):>5}  bare median {np.median(b):.3f}  "
            f"p10 {np.percentile(b, 10):.3f}  p90 {np.percentile(b, 90):.3f}"
        )


if __name__ == "__main__":
    main()
