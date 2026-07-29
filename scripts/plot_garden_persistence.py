"""Persistence normalisation across epicmap's real clusters.

Limb length ranks by cluster persistence. Dividing by the bucket maximum
compresses the channel when one cluster is an outlier, which is exactly
epicmap's shape: the top value is 0.449 and the next is 0.180. This compares
the candidate normalisations on the real values.

    uv run --with matplotlib python scripts/plot_garden_persistence.py
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from plot_assets import BG, CYAN, DIM, FRAME, GOLD, MUTED, PANEL, RED, TEXT, use_house_font

use_house_font()

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "14-garden-allometry"
DPI = 200
FLOOR = 0.25  # least persistent cluster still yields a visible limb

# epicmap, read 2026-07-29; used when the hub is not up.
FALLBACK = [
    0.031,
    0.031,
    0.031,
    0.036,
    0.037,
    0.058,
    0.058,
    0.060,
    0.066,
    0.066,
    0.068,
    0.071,
    0.075,
    0.082,
    0.090,
    0.094,
    0.096,
    0.103,
    0.104,
    0.143,
    0.180,
    0.449,
]


def persistences(bucket: str = "epicmap") -> list[float]:
    for path in ("garden", "grove"):
        try:
            with urllib.request.urlopen(f"http://localhost:6970/api/{path}", timeout=2) as r:
                data = json.load(r)
            for b in data.get("buckets", []):
                if b["bucket"] == bucket:
                    return sorted(float(n["persistence"]) for n in b["nodes"])
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            continue
    return sorted(FALLBACK)


def by_max(ps: list[float]) -> list[float]:
    hi = max(ps) or 1.0
    return [p / hi for p in ps]


def minmax(ps: list[float]) -> list[float]:
    lo, hi = min(ps), max(ps)
    if hi - lo < 1e-9:
        return [1.0] * len(ps)
    return [(p - lo) / (hi - lo) for p in ps]


def log_minmax(ps: list[float]) -> list[float]:
    safe = [max(p, 1e-6) for p in ps]
    lo, hi = math.log(min(safe)), math.log(max(safe))
    if hi - lo < 1e-9:
        return [1.0] * len(ps)
    return [(math.log(p) - lo) / (hi - lo) for p in safe]


def rank(ps: list[float]) -> list[float]:
    n = len(ps)
    return [i / max(1, n - 1) for i in range(n)]


def remap(vs: list[float]) -> list[float]:
    return [FLOOR + (1 - FLOOR) * v for v in vs]


def spread_stats(vs: list[float]) -> tuple[float, float]:
    """Fraction of the output range used by the middle 80%, and the bulk's ceiling."""
    a = np.array(vs)
    p10, p90 = float(np.percentile(a, 10)), float(np.percentile(a, 90))
    bulk = float(np.percentile(a[:-1], 100)) if len(a) > 1 else float(a[-1])
    return p90 - p10, bulk


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    ps = persistences()
    schemes = [
        ("divide by max\n(shipped)", by_max(ps), RED),
        ("linear min-max", minmax(ps), CYAN),
        ("log min-max\n(proposed)", log_minmax(ps), GOLD),
        ("rank", rank(ps), "#9159ff"),
    ]

    fig = plt.figure(figsize=(15.2, 6.2), facecolor=BG)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.25, 1.0], wspace=0.24)

    ax = fig.add_subplot(gs[0])
    ax.set_facecolor(PANEL)
    x = np.arange(len(ps))
    for label, vs, colour in schemes:
        ax.plot(x, remap(vs), color=colour, linewidth=2.1, marker="o", markersize=3.4, label=label)
    ax.set_xlabel("epicmap's 22 clusters, least to most persistent", color=MUTED, fontsize=10)
    ax.set_ylabel("limb length multiplier", color=MUTED, fontsize=10)
    ax.set_title("A. what each normalisation asks for", color=TEXT, fontsize=12.5, pad=10)
    ax.tick_params(colors=MUTED, labelsize=8.6)
    for s in ax.spines.values():
        s.set_color(FRAME)
    ax.grid(True, color=DIM, linewidth=0.5, alpha=0.42)
    leg = ax.legend(facecolor=PANEL, edgecolor=FRAME, fontsize=9, loc="upper left")
    for t in leg.get_texts():
        t.set_color(TEXT)

    ax2 = fig.add_subplot(gs[1])
    ax2.set_facecolor(PANEL)
    labels = [s[0].replace("\n", " ") for s in schemes]
    spreads = [spread_stats(remap(s[1]))[0] for s in schemes]
    bars = ax2.barh(np.arange(len(schemes)), spreads, color=[s[2] for s in schemes], alpha=0.9)
    ax2.set_yticks(np.arange(len(schemes)))
    ax2.set_yticklabels(labels, fontsize=9)
    ax2.set_xlabel("output range used by the middle 80% of clusters", color=MUTED, fontsize=10)
    ax2.set_title("B. how much of the channel survives", color=TEXT, fontsize=12.5, pad=10)
    ax2.tick_params(colors=MUTED, labelsize=8.6)
    for s in ax2.spines.values():
        s.set_color(FRAME)
    ax2.grid(True, axis="x", color=DIM, linewidth=0.5, alpha=0.42)
    for b, v in zip(bars, spreads, strict=True):
        ax2.text(
            v + 0.012,
            b.get_y() + b.get_height() / 2,
            f"{v:.2f}",
            color=MUTED,
            fontsize=9,
            va="center",
        )
    ax2.set_xlim(0, max(spreads) * 1.22)

    fig.suptitle(
        "Garden persistence: one outlier eats the channel",
        color=TEXT,
        fontsize=16,
        y=0.99,
    )
    fig.text(
        0.5,
        -0.02,
        f"epicmap's top cluster is {max(ps):.3f} against {sorted(ps)[-2]:.3f} for the next, so "
        "dividing by the maximum leaves the other 21 below a third of the range.\n"
        "Linear min-max only shifts that; taking the log first spreads the bulk while keeping "
        "magnitude ordering. Rank spreads perfectly but discards magnitude.",
        color=MUTED,
        fontsize=10.2,
        ha="center",
        linespacing=1.8,
    )

    out = OUTDIR / "07-persistence-normalisation.png"
    fig.savefig(out, dpi=DPI, facecolor=BG, bbox_inches="tight")
    print(f"wrote {out}")
    print(f"{'raw':>8}{'by-max':>10}{'minmax':>10}{'log':>10}{'rank':>10}")
    for i, p in enumerate(ps):
        print(
            f"{p:>8.3f}{remap(by_max(ps))[i]:>10.3f}{remap(minmax(ps))[i]:>10.3f}"
            f"{remap(log_minmax(ps))[i]:>10.3f}{remap(rank(ps))[i]:>10.3f}"
        )
    for label, vs, _ in schemes:
        sp, bulk = spread_stats(remap(vs))
        print(
            f"  {label.replace(chr(10), ' '):<26} middle-80% spread {sp:.3f}   bulk ceiling {bulk:.3f}"
        )


if __name__ == "__main__":
    main()
