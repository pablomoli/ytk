"""Figures for the path-dependence report: divergence curves + policy
frontier, from docs/garden-lab/replay-cells/*.json.

Palette: dataviz reference slots (validated 2026-07-12).
    uv run --extra dev --with matplotlib python -m scripts.garden_lab.path_figs
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

LAB = Path(__file__).resolve().parents[2] / "docs" / "garden-lab"
CELLS = LAB / "replay-cells"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
SLOTS = {
    "never": "#e34948",
    "cm": "#4a3aa7",
    "1.0": "#e87ba4",
    "0.5": "#eda100",
    "0.25": "#1baf7a",
    "0.1": "#2a78d6",
}
# intrinsic cross-half triplet floors (shootout-v3): divergence below the
# floor is indistinguishable from the bucket's own instability
FLOORS = {"epicmap": 0.596, "ai-building": 0.752, "visual-craft": 0.738}


def metric_value(cp: dict, metric: str):
    if metric == "triplet_agreement":
        return cp["production"]["triplets"]["agreement"]
    if metric == "assignment_ari":
        return cp["production"]["assignment_ari"]
    if metric == "mass_l1":
        return cp["production"]["mass"]["mass_l1"]
    raise KeyError(metric)


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#d8d7d3")
    ax.tick_params(colors=INK2, labelsize=8.5)


def load_cells() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(CELLS.glob("*.json"))]


def theta_key(cell) -> str:
    if cell.get("policy") == "centroid-maintain":
        return "cm"
    return "never" if cell["theta"] is None else str(cell["theta"])


def fig_divergence(cells, metric: str, fname: str, title: str, floors=False):
    buckets = sorted({c["bucket"] for c in cells})
    fig, axes = plt.subplots(1, len(buckets), figsize=(10.5, 3.6), dpi=160, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, bucket in zip(np.atleast_1d(axes), buckets):
        _style(ax)
        series = defaultdict(list)  # (theta, is_date_arm) -> runs of (frac, value)
        for c in cells:
            # curves use the base-0.5 arms; base-fraction sensitivity is tabular
            if c["bucket"] != bucket or c.get("base_frac", 0.5) != 0.5:
                continue
            pts = [
                (cp["frac"], metric_value(cp, metric))
                for cp in c["checkpoints"]
                if metric_value(cp, metric) is not None
            ]
            if pts:
                series[(theta_key(c), c["order"] == "date")].append(pts)
        for (theta, is_date), runs in sorted(series.items()):
            xs = [p[0] for p in runs[0]]
            ys = np.array([[dict(r).get(x, np.nan) for x in xs] for r in runs], float)
            mean = np.nanmean(ys, axis=0)
            style = {
                "color": SLOTS.get(theta, INK2),
                "linewidth": 2 if is_date else 1,
                "alpha": 1.0 if is_date else 0.45,
                "linestyle": "-" if is_date else "--",
            }
            label = f"{theta}{'' if is_date else ' (rand)'}"
            ax.plot(xs, mean, marker="o", markersize=3, label=label, **style)
        if floors and bucket in FLOORS:
            ax.axhline(FLOORS[bucket], color=INK2, linewidth=0.8, linestyle=":", alpha=0.7)
            ax.text(0.62, FLOORS[bucket], "intrinsic floor", fontsize=7, color=INK2, va="bottom")
        ax.set_title(bucket, loc="left", fontsize=10, color=INK)
        ax.set_xlabel("fraction of notes arrived", fontsize=8.5, color=INK2)
    np.atleast_1d(axes)[0].set_ylabel(metric, fontsize=8.5, color=INK2)
    np.atleast_1d(axes)[-1].legend(
        frameon=False, fontsize=7, labelcolor=INK2, title="rebuild theta", title_fontsize=7
    )
    fig.suptitle(title, x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(LAB / fname, facecolor=SURFACE)
    plt.close(fig)


def fig_frontier(cells):
    """Final divergence vs rebuild count - the policy menu in one plot."""
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    markers = {"epicmap": "o", "ai-building": "s", "visual-craft": "^"}
    for c in cells:
        if c["order"] != "date" or c.get("base_frac", 0.5) != 0.5 or not c["checkpoints"]:
            continue
        y = metric_value(c["checkpoints"][-1], "assignment_ari")
        ax.scatter(
            c["rebuilds"],
            y,
            color=SLOTS.get(theta_key(c), INK2),
            s=70,
            marker=markers.get(c["bucket"], "o"),
            edgecolor=SURFACE,
            linewidth=1.2,
            zorder=3,
        )
        ax.annotate(
            f"{c['bucket'][:4]} {theta_key(c)}",
            (c["rebuilds"], y),
            textcoords="offset points",
            xytext=(7, 4),
            fontsize=7,
            color=INK2,
        )
    ax.set_xlabel("rebuilds incurred (cost)", fontsize=9, color=INK2)
    ax.set_ylabel("final assignment agreement vs fresh rebuild", fontsize=9, color=INK2)
    ax.set_title(
        "Rebuild policy frontier (date-ordered arrival, base 0.5)",
        loc="left",
        fontsize=11,
        color=INK,
        pad=12,
    )
    fig.tight_layout()
    fig.savefig(LAB / "path-policy-frontier.png", facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    cells = load_cells()
    if not cells:
        raise SystemExit("no replay cells found")
    fig_divergence(
        cells,
        "triplet_agreement",
        "path-divergence-triplet.png",
        "Incremental tree vs fresh rebuild: hierarchy agreement",
        floors=True,
    )
    fig_divergence(
        cells,
        "assignment_ari",
        "path-divergence-ari.png",
        "Incremental tree vs fresh rebuild: assignment agreement",
    )
    fig_frontier(cells)
    print(f"wrote 3 figures to {LAB} from {len(cells)} cells")


if __name__ == "__main__":
    main()
