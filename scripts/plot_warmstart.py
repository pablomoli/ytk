"""Figure for section 38 — the warm-start trade (#83).

Reads experiments/warmstart_identity_results.json and renders the one claim:
warm-starting the daily KMeans refit removes identity churn at a measured,
bounded quality cost. Three panels, one claim from three sides: the paired
per-seed effect, where the churn lived in time, and what it costs in inertia.

Run: uv run --with matplotlib python scripts/plot_warmstart.py [--out DIR]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    BLUE,
    DPI,
    GOLD,
    MARGIN,
    RED,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "warmstart_identity_results.json"
OUT = (
    Path(sys.argv[sys.argv.index("--out") + 1])
    if "--out" in sys.argv
    else (ROOT / "docs" / "assets" / "38-warmstart-identity")
)


def per_seed(R: dict, cond: str, key: str) -> np.ndarray:
    return np.array([[t[key] for t in run["transitions"]] for run in R["results"][cond]])


def main() -> None:
    R = json.loads(RESULTS.read_text())
    days = [f"{d[4:6]}-{d[6:]}" for d in R["days"][1:]]
    x = np.arange(len(days))

    ev_c, ev_w = per_seed(R, "cold", "events"), per_seed(R, "warm", "events")
    ch_c, ch_w = per_seed(R, "cold", "churn"), per_seed(R, "warm", "churn")
    in_c, in_w = per_seed(R, "cold", "inertia"), per_seed(R, "warm", "inertia")
    gap = 100 * (in_w - in_c) / in_c

    meta = (
        f"{R['seeds']} paired seeds x 9 daily transitions ({R['days'][0][4:6]}-{R['days'][0][6:]} "
        f"to {days[-1]}, n {R['n_per_day'][0]}-{R['n_per_day'][-1]}, k {R['k_per_day'][0]}-"
        f"{R['k_per_day'][-1]})  |  events/transition {ev_c.mean():.1f} -> {ev_w.mean():.2f}  |  "
        f"note churn {100 * ch_c.mean():.0f}% -> {100 * ch_w.mean():.1f}%  |  inertia "
        f"+{gap.mean():.1f}% (day-10 +{gap[:, -1].mean():.1f}%)  |  commit {R['commit']}"
    )
    fig, top = figure(
        16,
        6.4,
        1,
        "the warm-start trade",
        "One lineage, ten days: seeding the daily refit with yesterday's centroids",
        meta,
    )
    axes = fig.subplots(1, 3)
    fig.subplots_adjust(
        left=MARGIN + 0.012, right=1 - MARGIN, top=top - 0.05, bottom=0.14, wspace=0.24
    )

    # (a) paired slopegraph: each seed's chain-mean events, cold -> warm
    ax = axes[0]
    for c, w in zip(ev_c.mean(axis=1), ev_w.mean(axis=1)):
        ax.plot([0, 1], [c, w], color=GOLD, linewidth=0.9, alpha=0.55, zorder=2)
    ax.scatter(np.zeros(len(ev_c)), ev_c.mean(axis=1), color=GOLD, s=26, zorder=3)
    ax.scatter(np.ones(len(ev_w)), ev_w.mean(axis=1), color=BLUE, s=26, zorder=3)
    ax.set_xlim(-0.35, 1.35)
    ax.set_ylim(0, ev_c.mean(axis=1).max() * 1.12)
    ax.set_xticks([0, 1], ["cold\n(production)", "warm"])
    ax.set_ylabel("lifecycle events / transition")
    panel_title(ax, "20 seeds, paired: events per transition")

    # (b) where the churn lived: note-lineage churn per transition
    ax = axes[1]
    for row in ch_c:
        ax.plot(x, 100 * row, color=GOLD, linewidth=0.7, alpha=0.35)
    for row in ch_w:
        ax.plot(x, 100 * row, color=BLUE, linewidth=0.7, alpha=0.35)
    ax.plot(x, 100 * ch_c.mean(axis=0), color=GOLD, linewidth=2.2)
    ax.plot(x, 100 * ch_w.mean(axis=0), color=BLUE, linewidth=2.2)
    ax.set_xticks(x, days, rotation=45)
    ax.set_ylabel("notes changing lineage (%)")
    ax.set_ylim(0, None)
    panel_title(ax, "daily lineage churn: every day vs almost never")

    # (c) the price: inertia gap vs the cold optimum
    ax = axes[2]
    ax.axhline(0, color=RED, linewidth=1.2)
    ax.text(x[-1], 0.06, "cold parity", color=RED, fontsize=8, ha="right", va="bottom")
    for row in gap:
        ax.plot(x, row, color=BLUE, linewidth=0.7, alpha=0.35)
    ax.plot(x, gap.mean(axis=0), color=BLUE, linewidth=2.2)
    ax.set_xticks(x, days, rotation=45)
    ax.set_ylabel("inertia vs cold (%)")
    ax.set_ylim(-0.25, gap.max() * 1.12)
    panel_title(ax, "the cost: inertia creep, +1.4% to +1.9%")

    for ax in axes:
        style_axes(ax)
    verdict(
        fig,
        "12x fewer identity events for under 2% inertia — the refit was the noise, and a warm init silences it",
    )
    frame_panels(fig)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "01-warmstart-trade.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out}  ({out.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
