"""Branching geometry before and after, from two real skeleton dumps.

    scripts/dump_skeleton.sh 6970 epicmap /tmp/skeleton-epicmap-BEFORE.json   # pre-change
    scripts/dump_skeleton.sh 6970 epicmap /tmp/skeleton-epicmap-AFTER.json    # post-change
    uv run --with matplotlib python scripts/plot_garden_branching_compare.py

Both panels read the skeleton the renderer builds, so the comparison measures
the change rather than illustrating it.
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
BEFORE = Path("/tmp/skeleton-epicmap-BEFORE.json")
AFTER = Path("/tmp/skeleton-epicmap-AFTER.json")
DPI = 200
ORDER_COLOURS = [TEXT, GOLD, CYAN, RED, "#9159ff", "#7fd4ff"]


def radial(n: dict) -> float:
    r = math.hypot(n["x"], n["z"])
    return r if n["x"] >= 0 else -r


def metrics(data: dict) -> tuple[dict[int, list[float]], dict[int, list[float]]]:
    nodes = data["nodes"]
    by_id = {n["id"]: n for n in nodes}
    kids = defaultdict(list)
    for n in nodes:
        if n["parent"] >= 0:
            kids[n["parent"]].append(n["id"])

    angles: dict[int, list[float]] = defaultdict(list)
    bare: dict[int, list[float]] = defaultdict(list)
    for n in nodes:
        p = n["parent"]
        if p < 0:
            continue
        par = by_id[p]
        if n["order"] <= par["order"]:
            continue
        dx, dy, dz = n["x"] - par["x"], n["y"] - par["y"], n["z"] - par["z"]
        angles[n["order"]].append(math.degrees(math.atan2(math.hypot(dx, dz), dy)))

        order = n["order"]
        cur, first_child = n, None
        while True:
            same = [c for c in kids[cur["id"]] if by_id[c]["order"] == order]
            higher = [c for c in kids[cur["id"]] if by_id[c]["order"] > order]
            if higher and first_child is None:
                first_child = cur["path"]
            if not same:
                break
            cur = by_id[same[0]]
        span = cur["path"] - n["path"]
        if span > 1e-6 and first_child is not None:
            bare[order].append((first_child - n["path"]) / span)
    return angles, bare


def draw_skeleton(ax, data: dict, title: str) -> None:
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
            linewidth=max(0.35, 2.6 - 0.5 * o),
            alpha=0.85 if o <= 1 else 0.4,
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
            alpha=0.45,
        )
    )
    ax.set_title(title, color=TEXT, fontsize=12.5, pad=10)
    ax.set_xlabel("lateral distance from the trunk axis", color=MUTED, fontsize=9.6)
    ax.set_ylabel("height", color=MUTED, fontsize=9.6)
    ax.set_aspect("equal")
    ax.tick_params(colors=MUTED, labelsize=8.2)
    for s in ax.spines.values():
        s.set_color(FRAME)
    ax.grid(True, color=DIM, linewidth=0.5, alpha=0.3)


def profile(ax, before: dict, after: dict, title: str, ylabel: str, target=None) -> None:
    ax.set_facecolor(PANEL)
    keys = sorted(set(before) | set(after))
    keys = [k for k in keys if len(before.get(k, [])) >= 3 or len(after.get(k, [])) >= 3]
    bm = [float(np.median(before[k])) if len(before.get(k, [])) else np.nan for k in keys]
    am = [float(np.median(after[k])) if len(after.get(k, [])) else np.nan for k in keys]
    ax.plot(keys, bm, color=RED, linewidth=2.2, marker="o", markersize=5, label="before")
    ax.plot(keys, am, color=GOLD, linewidth=2.2, marker="o", markersize=5, label="after")
    if target is not None:
        lo, hi = target
        ax.axhspan(lo, hi, color=CYAN, alpha=0.14)
        ax.text(keys[-1], hi, " target", color=CYAN, fontsize=8.8, va="bottom", ha="right")
    ax.set_title(title, color=TEXT, fontsize=12.5, pad=10)
    ax.set_xlabel("branch order", color=MUTED, fontsize=9.6)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=9.6)
    ax.set_xticks(keys)
    ax.tick_params(colors=MUTED, labelsize=8.4)
    for s in ax.spines.values():
        s.set_color(FRAME)
    ax.grid(True, color=DIM, linewidth=0.5, alpha=0.35)
    leg = ax.legend(facecolor=PANEL, edgecolor=FRAME, fontsize=9)
    for t in leg.get_texts():
        t.set_color(TEXT)
    return keys, bm, am


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    before, after = json.loads(BEFORE.read_text()), json.loads(AFTER.read_text())
    ab, bb = metrics(before)
    aa, ba = metrics(after)

    fig = plt.figure(figsize=(15.6, 11.4), facecolor=BG)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.35, 1.0], hspace=0.24, wspace=0.2)

    ax0 = fig.add_subplot(gs[0, 0])
    ax0.set_facecolor(PANEL)
    draw_skeleton(ax0, before, f"A. before, {len(before['nodes'])} nodes")
    ax1 = fig.add_subplot(gs[0, 1], sharex=ax0, sharey=ax0)
    ax1.set_facecolor(PANEL)
    draw_skeleton(ax1, after, f"B. after, {len(after['nodes'])} nodes")

    k1, b1, a1 = profile(
        fig.add_subplot(gs[1, 0]),
        ab,
        aa,
        "C. departure angle from vertical",
        "degrees",
        target=(35, 55),
    )
    k2, b2, a2 = profile(
        fig.add_subplot(gs[1, 1]),
        bb,
        ba,
        "D. bare fraction before the first branch",
        "fraction",
        target=None,
    )

    fig.suptitle("Garden branching geometry: before and after", color=TEXT, fontsize=16.5, y=0.97)
    fig.text(
        0.5,
        0.045,
        "Angle medians  before "
        + ", ".join(f"{k}:{v:.0f}" for k, v in zip(k1, b1, strict=True))
        + "   after "
        + ", ".join(f"{k}:{v:.0f}" for k, v in zip(k1, a1, strict=True))
        + "\nBare medians  before "
        + ", ".join(f"{k}:{v:.2f}" for k, v in zip(k2, b2, strict=True))
        + "   after "
        + ", ".join(f"{k}:{v:.2f}" for k, v in zip(k2, a2, strict=True))
        + "\nBare should fall with order: a rising profile means the finest twigs are the barest.",
        color=MUTED,
        fontsize=10,
        ha="center",
        linespacing=1.8,
    )

    out = OUTDIR / "10-branching-before-after.png"
    fig.savefig(out, dpi=DPI, facecolor=BG, bbox_inches="tight")
    print(f"wrote {out}")
    print("order  angle_before  angle_after   bare_before  bare_after")
    for k in sorted(set(k1) | set(k2)):
        ab_ = f"{np.median(ab[k]):.1f}" if len(ab.get(k, [])) else "-"
        aa_ = f"{np.median(aa[k]):.1f}" if len(aa.get(k, [])) else "-"
        bb_ = f"{np.median(bb[k]):.3f}" if len(bb.get(k, [])) else "-"
        ba_ = f"{np.median(ba[k]):.3f}" if len(ba.get(k, [])) else "-"
        print(f"{k:>5}{ab_:>14}{aa_:>13}{bb_:>14}{ba_:>12}")


if __name__ == "__main__":
    main()
