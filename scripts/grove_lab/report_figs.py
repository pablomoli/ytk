"""Report figures for the grove lab: bucket census + temporal density.

Emits PNGs into docs/grove-lab/. Reproducible from the live corpus:
    uv run --extra dev python -m scripts.grove_lab.report_figs

Palette: dataviz reference categorical slots 1-5 (validated 2026-07-12,
light surface; aqua/yellow < 3:1 relieved by direct labels + report table).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from scripts.grove_lab.buckets import DEFAULT_CONFIG, assign, load_buckets, resolve_notes

OUT = Path(__file__).resolve().parents[2] / "docs" / "grove-lab"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
SLOTS = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7"]
CATS = ["memory", "instagram", "youtube", "project-note", "other"]


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#d8d7d3")
    ax.tick_params(colors=INK2, labelsize=9)


def fold_cat(cat: str) -> str:
    return cat if cat in CATS else "other"


def fig_census(cfg, meta, labels) -> None:
    """Horizontal stacked bars: notes per bucket by source category.
    Linear scale on purpose — the size disparity IS the finding."""
    names = [b.name for b in cfg.buckets]
    counts = {
        i: Counter(fold_cat(meta[k]["cat"]) for k, x in enumerate(labels) if x == i)
        for i in range(len(names))
    }
    fig, ax = plt.subplots(figsize=(8.6, 4.6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    y = np.arange(len(names))[::-1]
    left = np.zeros(len(names))
    for ci, cat in enumerate(CATS):
        widths = np.array([counts[i].get(cat, 0) for i in range(len(names))], float)
        ax.barh(y, widths, left=left, height=0.62, color=SLOTS[ci], label=cat,
                edgecolor=SURFACE, linewidth=1.5)
        left += widths
    for i, total in enumerate(left):
        ax.text(total + 14, y[i], f"{int(total):,}", va="center", fontsize=9,
                color=INK, fontweight="bold")
    ax.set_yticks(y, names, color=INK, fontsize=9.5)
    ax.set_xlim(0, left.max() * 1.09)
    ax.xaxis.set_major_formatter(lambda v, _: f"{int(v):,}")
    ax.set_title("Grove buckets: notes per topic by source category",
                 loc="left", color=INK, fontsize=11, pad=14)
    ax.legend(loc="lower right", frameon=False, fontsize=8.5, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(OUT / "bucket-census.png", facecolor=SURFACE)
    plt.close(fig)


def fig_temporal(cfg, meta, labels) -> None:
    """One strip per bucket, a dot per dated note. Shows instantly which
    trees have a chronology to replay and which are undatable."""
    names = [b.name for b in cfg.buckets]
    fig, ax = plt.subplots(figsize=(8.6, 4.8), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    rng = np.random.default_rng(7)
    rows = []
    for i, nm in enumerate(names):
        idx = [k for k, x in enumerate(labels) if x == i]
        dates = [np.datetime64(meta[k]["date"]) for k in idx if meta[k]["date"]]
        undated = len(idx) - len(dates)
        rows.append((nm, dates, undated, len(idx)))
    for r, (nm, dates, undated, n) in enumerate(reversed(rows)):
        if dates:
            x = mdates.date2num([d.astype("datetime64[D]").astype(object) for d in dates])
            jitter = rng.uniform(-0.18, 0.18, len(x))
            ax.plot(x, np.full(len(x), r) + jitter, ".", color=SLOTS[0],
                    markersize=3.2, alpha=0.35, markeredgewidth=0)
        tag = f"{nm}  (n={n}" + (f", {undated} undated)" if undated else ")")
        ax.text(0.005, (r + 0.38) / len(rows), tag, transform=ax.transAxes,
                fontsize=8.5, color=INK, va="bottom")
    ax.set_yticks([])
    ax.set_ylim(-0.6, len(rows) - 0.2)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(mdates.AutoDateLocator()))
    ax.set_title("When each topic's notes were written (one dot per dated note)",
                 loc="left", color=INK, fontsize=11, pad=14)
    fig.tight_layout()
    fig.savefig(OUT / "bucket-temporal.png", facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_buckets(DEFAULT_CONFIG)
    vecs, meta, notes = resolve_notes()
    labels = assign(notes, cfg)
    fig_census(cfg, meta, labels)
    fig_temporal(cfg, meta, labels)
    print(f"wrote {OUT}/bucket-census.png, {OUT}/bucket-temporal.png")


if __name__ == "__main__":
    main()
