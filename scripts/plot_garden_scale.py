"""Height scaling and trunk-to-crown balance, for docs/assets/14-garden-allometry/.

Two observations from the first render: heights look wrong across the buckets,
and epicmap's trunk looks too girthy for the crown it carries. Both are
measurable against the real bucket distribution.

    uv run --with matplotlib python scripts/plot_garden_scale.py

Mirrors web/src/lib/garden/envelope.ts and girth.ts, with the scene's constants
(HEIGHT_PER_REACH 2.4, reach 4, trunkFraction 0.35, spread 0.35-1.1).
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from plot_assets import BG, CYAN, DIM, FRAME, GOLD, MUTED, PANEL, RED, TEXT, use_house_font
from plot_garden_allometry import buckets

use_house_font()

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "14-garden-allometry"
DPI = 200

MAX_HEIGHT = 2.4 * 4.0
TRUNK_FRACTION = 0.35
SPREAD_MIN, SPREAD_MAX = 0.35, 1.1
MIN_HEIGHT_FRACTION = 0.18
TIP_RADIUS = 0.012

# Mature broad-leaved trees run roughly 1:15 to 1:25 trunk diameter to crown
# spread, i.e. this band in trunk-radius over crown-radius.
REAL_LO, REAL_HI = 0.030, 0.070


def t_sqrt(n: float, cap: float) -> float:
    return min(1.0, math.sqrt(min(n, cap) / max(1.0, cap)))


def t_log(n: float, cap: float) -> float:
    return min(1.0, math.log1p(min(n, cap)) / math.log1p(max(1.0, cap)))


def envelope(n: float, cap: float, tf) -> tuple[float, float, float]:
    """Returns (total height, crown half-height, crown radius)."""
    t = tf(n, cap)
    h = MAX_HEIGHT * (MIN_HEIGHT_FRACTION + (1 - MIN_HEIGHT_FRACTION) * t)
    trunk = h * TRUNK_FRACTION
    half = (h - trunk) / 2
    spread = SPREAD_MIN + (SPREAD_MAX - SPREAD_MIN) * t
    return h, half, spread * half


def trunk_radius(tips: float, exponent: float, tip_radius: float = TIP_RADIUS) -> float:
    return tip_radius * tips ** (1.0 / exponent)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    data = sorted(buckets(), key=lambda kv: kv[1])
    cap = max(n for _, n in data)
    ns = [n for _, n in data]
    names = [k for k, _ in data]

    fig = plt.figure(figsize=(16.4, 6.4), facecolor=BG)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.15, 1.0, 0.95], wspace=0.28)

    # --- A: height scaling ------------------------------------------------
    ax = fig.add_subplot(gs[0])
    ax.set_facecolor(PANEL)
    hs_sqrt = [envelope(n, cap, t_sqrt)[0] for n in ns]
    hs_log = [envelope(n, cap, t_log)[0] for n in ns]
    y = np.arange(len(ns))
    ax.barh(y - 0.2, hs_sqrt, height=0.38, color=CYAN, alpha=0.85, label="sqrt (shipped)")
    ax.barh(y + 0.2, hs_log, height=0.38, color=GOLD, alpha=0.9, label="log (proposed)")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{k}  {n}" for k, n in zip(names, ns, strict=True)], fontsize=8.6)
    ax.set_xlabel("tree height, world units", color=MUTED, fontsize=10)
    ax.set_title("A. height across the real buckets", color=TEXT, fontsize=12.5, pad=10)
    ax.tick_params(colors=MUTED, labelsize=8.6)
    for s in ax.spines.values():
        s.set_color(FRAME)
    leg = ax.legend(facecolor=PANEL, edgecolor=FRAME, fontsize=9, loc="lower right")
    for t in leg.get_texts():
        t.set_color(TEXT)
    ax.grid(True, axis="x", color=DIM, linewidth=0.5, alpha=0.4)

    span_sqrt = max(hs_sqrt) / min(hs_sqrt)
    span_log = max(hs_log) / min(hs_log)

    # --- B: trunk-to-crown vs pipe exponent -------------------------------
    ax2 = fig.add_subplot(gs[1])
    ax2.set_facecolor(PANEL)
    _, _, crown_r = envelope(cap, cap, t_log)
    exps = np.linspace(2.0, 4.0, 160)
    for tips, style in ((2000, ":"), (4000, "-"), (8000, "--")):
        ratios = [trunk_radius(tips, e) / crown_r for e in exps]
        ax2.plot(exps, ratios, color=GOLD, linestyle=style, linewidth=2.0, label=f"{tips} tips")
    ax2.axhspan(REAL_LO, REAL_HI, color=CYAN, alpha=0.16)
    ax2.text(3.62, REAL_HI * 1.06, "real trees", color=CYAN, fontsize=9)
    ax2.axvline(2.5, color=RED, linewidth=1.2, alpha=0.75)
    ax2.text(2.54, 0.175, "shipped 2.5", color=RED, fontsize=9)
    ax2.set_xlabel("pipe exponent", color=MUTED, fontsize=10)
    ax2.set_ylabel("trunk radius / crown radius", color=MUTED, fontsize=10)
    ax2.set_title("B. epicmap trunk against its crown", color=TEXT, fontsize=12.5, pad=10)
    ax2.set_ylim(0, 0.20)
    ax2.tick_params(colors=MUTED, labelsize=8.6)
    for s in ax2.spines.values():
        s.set_color(FRAME)
    ax2.grid(True, color=DIM, linewidth=0.5, alpha=0.4)
    leg2 = ax2.legend(facecolor=PANEL, edgecolor=FRAME, fontsize=9, loc="upper right")
    for t in leg2.get_texts():
        t.set_color(TEXT)

    # --- C: epicmap to scale ----------------------------------------------
    ax3 = fig.add_subplot(gs[2])
    ax3.set_facecolor(PANEL)
    h, half, crown = envelope(cap, cap, t_log)
    trunk_h = h * TRUNK_FRACTION
    for i, (exp, colour, label) in enumerate(
        ((2.5, RED, "n 2.5 (shipped)"), (3.3, GOLD, "n 3.3 (proposed)"))
    ):
        r = trunk_radius(4000, exp)
        x0 = i * 9.0
        ax3.add_patch(
            plt.matplotlib.patches.Ellipse(
                (x0, trunk_h + half), crown * 2, half * 2, color="#cdc7bb", alpha=0.20
            )
        )
        ax3.fill(
            [x0 - r, x0 + r, x0 + r * 0.55, x0 - r * 0.55],
            [0, 0, trunk_h + half, trunk_h + half],
            color=colour,
            alpha=0.92,
        )
        ax3.text(
            x0,
            -0.9,
            f"{label}\ntrunk r {r:.2f}   ratio {r / crown:.3f}",
            color=MUTED,
            fontsize=8.8,
            ha="center",
            va="top",
            linespacing=1.5,
        )
    ax3.set_xlim(-5.0, 14.0)
    ax3.set_ylim(-3.4, h * 1.05)
    ax3.set_aspect("equal")
    ax3.axis("off")
    ax3.set_title("C. epicmap, crown to scale", color=TEXT, fontsize=12.5, pad=10)

    fig.suptitle(
        "Garden scale: height spread, and how thick a trunk the pipe model asks for",
        color=TEXT,
        fontsize=16,
        y=1.0,
    )
    fig.text(
        0.5,
        -0.03,
        f"Height spread across the buckets: sqrt {span_sqrt:.2f}x, log {span_log:.2f}x. "
        f"Crown radius at the largest bucket is {crown:.2f}.\n"
        "The pipe exponent is the lever for trunk-to-crown; tip radius scales both "
        "trunk and twigs together and cannot fix the ratio alone.",
        color=MUTED,
        fontsize=10.2,
        ha="center",
        linespacing=1.8,
    )

    out = OUTDIR / "05-scale-and-girth.png"
    fig.savefig(out, dpi=DPI, facecolor=BG, bbox_inches="tight")
    print(f"wrote {out}")
    print(f"height span: sqrt {span_sqrt:.2f}x   log {span_log:.2f}x")
    print(f"crown radius (largest bucket, log): {crown:.2f}")
    for tips in (2000, 4000, 8000):
        for e in (2.5, 3.0, 3.3, 3.6):
            r = trunk_radius(tips, e)
            print(f"  tips {tips:>5}  n {e}  trunk {r:.3f}  ratio {r / crown:.3f}")
    print("\nheights (log) per bucket:")
    for name, n in data:
        hh = envelope(n, cap, t_log)[0]
        hs = envelope(n, cap, t_sqrt)[0]
        print(f"  {n:>6}  {name:<16} sqrt {hs:.2f}  log {hh:.2f}")


if __name__ == "__main__":
    main()
