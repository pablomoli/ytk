"""Figures for the retrieval-gate corpus freeze (#111) -> docs/assets/08-eval-gate-freeze/.

House style is imported from plot_assets rather than restated, so these sit in
the same visual system as the fog, domain and time-machine figures.

Every number is measured against the live store; nothing here is illustrative.
The two payloads are committed next to the figures so they regenerate without
a store or an encoder:

    drift.json     retrospective pool sweep — historical corpus states rebuilt
                   from ingested_at, same embeddings and same code, only the
                   distractor pool varied
    verdicts.json  the green/red acceptance run: frozen scoring on the grown
                   corpus, and the same run with a deliberate regression
                   injected into the searchers

    uv run --with matplotlib python scripts/plot_eval_gate.py
    uv run --with matplotlib python scripts/plot_eval_gate.py --only 2
"""

from __future__ import annotations

import argparse
import json
import sys
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
    CYAN,
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

OUTDIR = ROOT / "docs" / "assets" / "08-eval-gate-freeze"
DRIFT = OUTDIR / "drift.json"
VERDICTS = OUTDIR / "verdicts.json"

# Collection sizes when the pre-#111 baseline was stamped (2026-07-24) against
# the live store one day later — the drift that kept the fingerprint red.
BASELINE_COUNTS = {"videos": 170, "memories": 3932, "segments": 5053}
LIVE_COUNTS = {"videos": 200, "memories": 4527, "segments": 5656}

# hit@1 needs a third line colour: GOLD and BLUE are taken, and house PURPLE
# reads nearly black against this background at 2px.
LILAC = "#8f8ad6"


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=FIG_BG)
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def legend(ax, **kw):
    leg = ax.legend(frameon=False, fontsize=8, **kw)
    for t in leg.get_texts():
        t.set_color(MUTED)
    return leg


def load_drift() -> dict:
    return json.loads(DRIFT.read_text())


def load_verdicts() -> dict:
    return json.loads(VERDICTS.read_text())


def fig01() -> None:
    """Why strict equality on a corpus hash could never hold."""
    drift = load_drift()
    by_date = drift["ingest_by_date"]
    dates = sorted(by_date)
    cum = np.cumsum([by_date[d] for d in dates]).astype(float)
    xs = np.array(
        [np.datetime64(d).astype("datetime64[D]").astype(int) for d in dates], dtype=float
    )

    fig, top = figure(
        14.6,
        6.4,
        1,
        "eval gate",
        "The corpus keeps growing by design, so a gate keyed to a hash of the "
        "whole corpus went red on ingest rather than on quality",
        f"{int(cum[-1]):,} dated documents across {len(dates)} distinct ingest days  ·  "
        f"baseline stamped 2026-07-24, "
        f"{sum(LIVE_COUNTS.values()) - sum(BASELINE_COUNTS.values()):+,} documents one day later",
    )
    axes = fig.subplots(1, 2)
    fig.subplots_adjust(left=0.075, right=0.975, top=top - 0.055, bottom=0.14, wspace=0.24)

    ax = axes[0]
    ax.fill_between(xs, cum, color=GOLD, alpha=0.13)
    ax.plot(xs, cum, color=GOLD, linewidth=2)
    ticks = np.linspace(xs.min(), xs.max(), 5)
    ax.set_xticks(ticks)
    ax.set_xticklabels(
        [str(np.datetime64(int(t), "D"))[5:] for t in ticks], rotation=30, ha="right"
    )
    ax.set_xlabel("ingest date (month-day)")
    ax.set_ylabel("documents in store (cumulative)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
    style_axes(ax)
    panel_title(
        ax,
        f"quiet stretches exist, but {len(dates)} days moved the hash — "
        "and the gate only needs one",
    )

    ax = axes[1]
    names = ["videos", "memories", "segments"]
    y = np.arange(len(names))
    base = [BASELINE_COUNTS[n] for n in names]
    live = [LIVE_COUNTS[n] for n in names]
    ax.barh(y + 0.19, base, height=0.34, color=DIM, label="at baseline stamp")
    ax.barh(y - 0.19, live, height=0.34, color=BLUE, label="one day later")
    for i, (b, live_n) in enumerate(zip(base, live)):
        ax.text(
            live_n * 1.02,
            i - 0.19,
            f"+{live_n - b}",
            color=CYAN,
            fontsize=8,
            va="center",
        )
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xscale("log")
    ax.set_xlabel("documents (log)")
    ax.set_xlim(100, 12000)
    style_axes(ax)
    legend(ax, loc="lower right")
    panel_title(ax, "every collection moved — the hash covers all three")

    save(fig, "01-corpus-growth.png")


def fig02() -> None:
    """What growth actually costs the metric, isolated."""
    drift = load_drift()
    rows = drift["rows"]
    pools = np.array([r["pool_size"] for r in rows], dtype=float)
    n = drift["n_queries_fixed"]

    fig, top = figure(
        14.6,
        6.4,
        2,
        "eval gate",
        "Growth alone moves hit@10 and nothing else — the tolerance-budget "
        "story the issue assumed is not what the data shows",
        f"same {n} queries, same embeddings, same code — only the distractor "
        f"pool varies  ·  pools rebuilt from ingested_at  ·  "
        f"each query is worth {100 / n:.1f} points",
    )
    axes = fig.subplots(1, 2)
    fig.subplots_adjust(left=0.075, right=0.975, top=top - 0.055, bottom=0.14, wspace=0.24)

    ax = axes[0]
    for metric, color, marker in (
        ("hit@10", BLUE, "o"),
        ("hit@5", GOLD, "s"),
        ("hit@1", LILAC, "^"),
    ):
        ax.plot(
            pools,
            [r[metric] for r in rows],
            color=color,
            marker=marker,
            markersize=5,
            linewidth=2,
            label=metric,
        )
    ax.set_xscale("log")
    ax.set_xlabel("distractor pool size (documents scored against, log)")
    ax.set_ylabel("hit rate")
    ax.set_ylim(0.60, 1.04)
    style_axes(ax)
    legend(ax, loc="lower left")
    ax.annotate(
        f"{pools[-1] / pools[0]:.0f}x pool growth\nhit@10 {rows[0]['hit@10']:.3f} -> {rows[-1]['hit@10']:.3f}",
        xy=(pools[-1], rows[-1]["hit@10"]),
        xytext=(-140, -46),
        textcoords="offset points",
        color=MUTED,
        fontsize=8,
        arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 0.9},
    )
    panel_title(ax, "hit@5 and hit@1 are flat across a 12x pool increase")

    ax = axes[1]
    metrics = ["hit@1", "hit@5", "hit@10"]
    deltas = [rows[-1][m] - rows[0][m] for m in metrics]
    colors = [RED if d < -0.001 else DIM for d in deltas]
    bars = ax.bar(metrics, deltas, color=colors, width=0.5)
    ax.axhline(0, color=MUTED, linewidth=1)
    for bar, d in zip(bars, deltas):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            d - 0.006 if d < 0 else d + 0.004,
            f"{d:+.3f}",
            ha="center",
            va="top" if d < 0 else "bottom",
            color=TEXT,
            fontsize=9,
        )
    ax.set_ylabel("change from smallest pool to largest")
    ax.set_ylim(-0.13, 0.05)
    style_axes(ax)
    panel_title(ax, "the whole effect of 12x growth sits in one metric")

    save(fig, "02-growth-drift-curve.png")


def fig03() -> None:
    """The gate can now tell the two cases apart."""
    v = load_verdicts()
    fig, top = figure(
        14.6,
        6.4,
        3,
        "eval gate",
        "Before the freeze the gate said FAIL either way; now it passes growth "
        "and still catches a real regression",
        f"verified live  ·  {v['frozen_size']:,} frozen ids  ·  "
        f"{v['starved']} starved queries  ·  both gated metrics catch the "
        "injected regression  ·  full pre-commit chain exits 0",
    )
    axes = fig.subplots(1, 2)
    fig.subplots_adjust(left=0.075, right=0.975, top=top - 0.055, bottom=0.16, wspace=0.24)

    # verdict matrix
    ax = axes[0]
    cases = ["clean tree,\ngrown corpus", "genuine retrieval\nregression"]
    rows_spec = [
        ("before", ["FAIL", "FAIL"], [DIM, RED]),
        ("after", ["PASS", "FAIL"], [CYAN, RED]),
    ]
    for r, (label, verdicts, colors) in enumerate(rows_spec):
        yy = 1 - r
        for c, (verdict, color) in enumerate(zip(verdicts, colors)):
            ax.add_patch(
                plt.Rectangle(
                    (c - 0.40, yy - 0.28),
                    0.80,
                    0.56,
                    facecolor=color,
                    edgecolor="none",
                    alpha=0.90,
                )
            )
            ax.text(
                c,
                yy,
                verdict,
                ha="center",
                va="center",
                color="#0b0b0d" if color is not RED else TEXT,
                fontsize=13,
                fontweight="bold",
            )
        ax.text(-0.78, yy, label, ha="right", va="center", color=MUTED, fontsize=9)
    ax.text(
        0,
        -0.52,
        "carried no information:\nFAIL regardless of quality",
        ha="center",
        va="center",
        color=MUTED,
        fontsize=8,
    )
    for c, case in enumerate(cases):
        ax.text(c, -0.95, case, ha="center", va="top", color=MUTED, fontsize=9)
    ax.set_xlim(-1.25, 1.62)
    ax.set_ylim(-1.45, 1.55)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_facecolor("#000000")
    for spine in ax.spines.values():
        spine.set_color("none")
    panel_title(ax, "the pale cell is the bug #111 was filed about")

    # the teeth: scores under the injected regression
    ax = axes[1]
    metrics = ["hit@5", "hit@10"]
    x = np.arange(len(metrics))
    baseline = [v["baseline"][m] for m in metrics]
    frozen = [v["frozen"][m] for m in metrics]
    injected = [v["injected_regression"][m] for m in metrics]
    ax.bar(x - 0.26, baseline, width=0.25, color=DIM, label="baseline")
    ax.bar(x, frozen, width=0.25, color=CYAN, label="frozen scoring (pass)")
    ax.bar(x + 0.26, injected, width=0.25, color=RED, label="injected regression (fail)")
    for xi, (f, inj) in enumerate(zip(frozen, injected)):
        ax.text(xi, f + 0.02, f"{f:.3f}", ha="center", color=TEXT, fontsize=8)
        ax.text(xi + 0.26, inj + 0.02, f"{inj:.3f}", ha="center", color=TEXT, fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylabel("hit rate")
    ax.set_ylim(0, 1.42)
    style_axes(ax)
    legend(ax, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.02))
    panel_title(ax, "a regression inside the frozen set still collapses the score")

    save(fig, "03-gate-verdicts.png")


FIGS = {1: fig01, 2: fig02, 3: fig03}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, help="regenerate a single figure")
    args = ap.parse_args()
    for number, fn in FIGS.items():
        if args.only and args.only != number:
            continue
        fn()


if __name__ == "__main__":
    main()
