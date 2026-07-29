"""Root system before and after, from two real skeleton dumps.

    scripts/dump_skeleton.sh 6970 epicmap /tmp/roots-BEFORE.json "" roots
    scripts/dump_skeleton.sh 6970 epicmap /tmp/roots-AFTER.json  "" roots
    uv run --with matplotlib python scripts/plot_garden_roots.py

Roots are largely hidden under the ground disc, so the measurements that matter
are the collar (where they meet the trunk), the lateral spread of the plate, and
how shallow it stays.
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
BEFORE = Path("/tmp/roots-BEFORE.json")
AFTER = Path("/tmp/roots-AFTER.json")
DPI = 200
ORDER_COLOURS = [TEXT, GOLD, CYAN, RED, "#9159ff", "#7fd4ff"]


def radial(n: dict) -> float:
    r = math.hypot(n["x"], n["z"])
    return r if n["x"] >= 0 else -r


def stats(data: dict) -> dict:
    nodes = data["nodes"]
    ys = [n["y"] for n in nodes]
    rs = [abs(radial(n)) for n in nodes]
    root = next(n for n in nodes if n["parent"] < 0)
    depth = -min(ys)
    spread = max(rs)
    return {
        "nodes": len(nodes),
        "collar": root["radius"],
        "depth": depth,
        "spread": spread,
        "plate_ratio": spread / depth if depth > 1e-6 else float("nan"),
        "max_order": max(n["order"] for n in nodes),
        "tips": sum(1 for n in nodes if n["kids"] == 0),
    }


def draw(ax, data: dict, title: str, lim: float) -> None:
    by_id = {n["id"]: n for n in data["nodes"]}
    for n in data["nodes"]:
        if n["parent"] < 0:
            continue
        par = by_id[n["parent"]]
        o = min(n["order"], len(ORDER_COLOURS) - 1)
        ax.plot(
            [radial(par), radial(n)],
            [par["y"], n["y"]],
            color=ORDER_COLOURS[o],
            linewidth=max(0.3, 2.4 - 0.45 * o),
            alpha=0.85 if o <= 1 else 0.4,
            solid_capstyle="round",
        )
    ax.axhline(0, color=MUTED, linewidth=1.0, alpha=0.6, linestyle=(0, (6, 4)))
    ax.text(-lim * 0.97, 0.06, "ground", color=MUTED, fontsize=8.6, va="bottom")
    ax.set_title(title, color=TEXT, fontsize=12.5, pad=10)
    ax.set_xlabel("lateral distance from the trunk axis", color=MUTED, fontsize=9.6)
    ax.set_ylabel("depth", color=MUTED, fontsize=9.6)
    ax.set_xlim(-lim, lim)
    ax.set_aspect("equal")
    ax.tick_params(colors=MUTED, labelsize=8.2)
    for s in ax.spines.values():
        s.set_color(FRAME)
    ax.grid(True, color=DIM, linewidth=0.5, alpha=0.3)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    before = json.loads(BEFORE.read_text())
    after = json.loads(AFTER.read_text())
    sb, sa = stats(before), stats(after)
    lim = max(sb["spread"], sa["spread"]) * 1.12

    fig = plt.figure(figsize=(15.4, 9.6), facecolor=BG)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1.0], hspace=0.3, wspace=0.2)

    ax0 = fig.add_subplot(gs[0, 0])
    ax0.set_facecolor(PANEL)
    draw(ax0, before, f"A. before, {sb['nodes']} nodes", lim)
    ax1 = fig.add_subplot(gs[0, 1], sharey=ax0)
    ax1.set_facecolor(PANEL)
    draw(ax1, after, f"B. after, {sa['nodes']} nodes", lim)

    ax2 = fig.add_subplot(gs[1, 0])
    ax2.set_facecolor(PANEL)
    keys = ["spread", "depth", "plate_ratio", "collar"]
    labels = ["lateral spread", "depth", "spread / depth", "collar radius"]
    x = np.arange(len(keys))
    ax2.bar(x - 0.2, [sb[k] for k in keys], 0.38, color=RED, alpha=0.9, label="before")
    ax2.bar(x + 0.2, [sa[k] for k in keys], 0.38, color=GOLD, alpha=0.9, label="after")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, fontsize=9)
    ax2.set_yscale("log")
    ax2.set_ylabel("world units (log)", color=MUTED, fontsize=9.6)
    ax2.set_title("C. plate geometry", color=TEXT, fontsize=12.5, pad=10)
    ax2.tick_params(colors=MUTED, labelsize=8.4)
    for s in ax2.spines.values():
        s.set_color(FRAME)
    ax2.grid(True, axis="y", color=DIM, linewidth=0.5, alpha=0.35)
    leg = ax2.legend(facecolor=PANEL, edgecolor=FRAME, fontsize=9)
    for t in leg.get_texts():
        t.set_color(TEXT)

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.set_facecolor(PANEL)
    for data, colour, label in ((before, RED, "before"), (after, GOLD, "after")):
        depth_by_r = defaultdict(list)
        for n in data["nodes"]:
            depth_by_r[round(abs(radial(n)), 1)].append(n["y"])
        xs = sorted(depth_by_r)
        ys = [float(np.mean(depth_by_r[k])) for k in xs]
        ax3.plot(xs, ys, color=colour, linewidth=2.1, label=label)
    ax3.set_xlabel("distance from the trunk", color=MUTED, fontsize=9.6)
    ax3.set_ylabel("mean depth", color=MUTED, fontsize=9.6)
    ax3.set_title("D. how the plate flattens outward", color=TEXT, fontsize=12.5, pad=10)
    ax3.tick_params(colors=MUTED, labelsize=8.4)
    for s in ax3.spines.values():
        s.set_color(FRAME)
    ax3.grid(True, color=DIM, linewidth=0.5, alpha=0.35)
    leg3 = ax3.legend(facecolor=PANEL, edgecolor=FRAME, fontsize=9)
    for t in leg3.get_texts():
        t.set_color(TEXT)

    fig.suptitle("Garden root system: before and after", color=TEXT, fontsize=16.5, y=0.97)
    fig.text(
        0.5,
        0.03,
        f"nodes {sb['nodes']} to {sa['nodes']},  spread {sb['spread']:.2f} to {sa['spread']:.2f},  "
        f"depth {sb['depth']:.2f} to {sa['depth']:.2f},  "
        f"spread/depth {sb['plate_ratio']:.2f} to {sa['plate_ratio']:.2f},  "
        f"collar {sb['collar']:.3f} to {sa['collar']:.3f}\n"
        "A root plate spreads far wider than it descends, and its collar should carry the "
        "same cross-section as the trunk above it.",
        color=MUTED,
        fontsize=10,
        ha="center",
        linespacing=1.8,
    )

    out = OUTDIR / "12-roots-before-after.png"
    fig.savefig(out, dpi=DPI, facecolor=BG, bbox_inches="tight")
    print(f"wrote {out}")
    for k in ("nodes", "tips", "max_order", "collar", "depth", "spread", "plate_ratio"):
        print(f"  {k:<12} before {sb[k]:>10.3f}   after {sa[k]:>10.3f}")


if __name__ == "__main__":
    main()
