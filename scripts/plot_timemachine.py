"""Ground-truth figures for the time machine (#107 feature D).

Feature D sweeps notes in by birth date instead of by the intro's fixed
timer. Before writing a shader against the dates, this asks what the dates
actually look like — because a scrubber is a mapping from slider position to
corpus, and that mapping is only as good as the distribution underneath it.

Rung 01 is the answer, and it vetoed the obvious design: the dates are not
spread across the vault's life, they are piled at one end of it.

House style is imported from plot_assets rather than restated, so these can
never drift from docs/assets/01-fog/.

Usage: uv run --with matplotlib --with numpy python scripts/plot_timemachine.py
Figures land in docs/assets/07-time-machine/.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from plot_assets import BG as FIG_BG
from plot_assets import (
    BLUE,
    DIM,
    DPI,
    GOLD,
    MUTED,
    RED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

OUTDIR = ROOT / "docs" / "assets" / "07-time-machine"
MAP = Path(os.path.expanduser("~/.ytk/map.json"))


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=FIG_BG)
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def load() -> tuple[list[dict], np.ndarray]:
    points = json.loads(MAP.read_text())["points"]
    days = np.array(
        sorted(
            np.datetime64(p["d"]).astype("datetime64[D]").astype(int) for p in points if p.get("d")
        ),
        dtype=float,
    )
    return points, days


def fig01() -> None:
    points, days = load()
    total, dated = len(points), len(days)

    fig, top = figure(
        16.2,
        6.8,
        1,
        "time machine",
        "The dates are piled at one end of the vault's life — a linear "
        "scrubber would be empty for 99% of its travel",
        f"{total} points, {dated} dated ({100 * dated / total:.1f}%)  ·  "
        f"span {np.datetime64(int(days.min()), 'D')} to "
        f"{np.datetime64(int(days.max()), 'D')}",
    )
    axes = fig.subplots(1, 3)
    fig.subplots_adjust(left=0.075, right=0.975, top=top - 0.055, bottom=0.13, wspace=0.30)

    # 1. the distribution itself
    ax = axes[0]
    ax.hist(days, bins=80, color=GOLD)
    ax.set_yscale("log")
    ax.set_xlabel("note date")
    ax.set_ylabel("notes per bin (log)")
    ticks = np.linspace(days.min(), days.max(), 5)
    ax.set_xticks(ticks)
    ax.set_xticklabels(
        [str(np.datetime64(int(t), "D"))[:7] for t in ticks], rotation=30, ha="right"
    )
    style_axes(ax)
    panel_title(ax, "when notes were born — log y, or the tail is invisible")

    # 2. the scrubber's actual job: fraction revealed vs slider position
    ax = axes[1]
    lin = np.linspace(days.min(), days.max(), 400)
    revealed = np.searchsorted(days, lin) / dated
    ax.plot(
        (lin - days.min()) / (days.max() - days.min()),
        revealed,
        color=RED,
        linewidth=2,
        label="linear time",
    )
    ax.plot(
        np.linspace(0, 1, 400),
        np.linspace(0, 1, 400),
        color=BLUE,
        linewidth=2,
        label="by rank (quantile)",
    )
    ax.fill_between(
        (lin - days.min()) / (days.max() - days.min()), revealed, 0, color=RED, alpha=0.12
    )
    ax.set_xlabel("scrubber position")
    ax.set_ylabel("fraction of notes visible")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    style_axes(ax)
    leg = ax.legend(frameon=False, fontsize=8, loc="upper left")
    for t in leg.get_texts():
        t.set_color(MUTED)
    half = float(np.interp(0.5, revealed, (lin - days.min()) / (days.max() - days.min())))
    ax.annotate(
        f"half the corpus arrives\nafter {100 * half:.1f}% of the travel",
        xy=(half, 0.5),
        xytext=(0.12, 0.62),
        color=TEXT,
        fontsize=8,
        arrowprops={"arrowstyle": "->", "color": MUTED, "linewidth": 1},
    )
    panel_title(ax, "why linear time fails: the reveal curve is a cliff")

    # 3. coverage is structurally biased, not uniformly sparse
    ax = axes[2]
    by_cat = Counter(p["c"] for p in points)
    with_d = Counter(p["c"] for p in points if p.get("d"))
    cats = [c for c, _ in by_cat.most_common()]
    frac = [100 * with_d.get(c, 0) / by_cat[c] for c in cats]
    ys = range(len(cats))
    ax.barh(
        list(ys),
        frac,
        color=[GOLD if f > 90 else (DIM if f == 0 else BLUE) for f in frac],
        height=0.68,
    )
    ax.set_yticks(list(ys))
    ax.set_yticklabels([f"{c}  ({by_cat[c]})" for c in cats], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("% of that category carrying a date")
    ax.set_xlim(0, 118)
    for y, f in zip(ys, frac):
        ax.text(f + 2, y, f"{f:.0f}%", color=TEXT if f else MUTED, fontsize=8, va="center")
    style_axes(ax)
    panel_title(ax, "undated notes are whole categories, not a random 4%")

    save(fig, "01-date-distribution.png")


if __name__ == "__main__":
    fig01()
