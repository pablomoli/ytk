"""Section 53, figures 03-05: drawn from the sidecars and the call ledger only.

uv run --with matplotlib python scripts/plot_jev_second_look.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ on path
from jev_client import LEDGER
from jev_rung0 import OUTDIR, ROOT, SIDECAR, SIDECAR2, order_rows
from plot_assets import (
    BG,
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
    verdict,
)

RUN1 = OUTDIR / "rung0-run1.json"
BENCH30 = ROOT / "experiments" / "rerank_bench_results.json"
BENCH10 = ROOT / "experiments" / "rerank_bench_10x512_results.json"
BUDGET_S = 1.0  # the +1 s per search that #86 set and the local reranker missed


def save(fig, name: str) -> None:
    frame_panels(fig)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size // 1024}KB)")


def fig03_stability(a: dict, b: dict, run1: dict) -> None:
    rows_a, rows_1 = a["rows"], run1["rows"]
    dp = np.abs(
        np.array([x for r in rows_a for x in r["noul"]])
        - np.array([x for r in rows_1 for x in r["noul"]])
    )
    p50, p90, mx = float(np.median(dp)), float(np.quantile(dp, 0.9)), float(dp.max())

    def pairs(rows):
        xs, ys = [], []
        for r in rows:
            for k, v in r["choice"].items():
                xs.append(v)
                ys.append(r["choice_rev"].get(k, 0.0))
        return np.array(xs), np.array(ys)

    xa, ya = pairs(rows_a)
    xb, yb = pairs(b["rows"])
    same_a = sum(r["winner"] == r["winner_rev"] for r in rows_a)
    same_b = sum(r["winner"] == r["winner_rev"] for r in b["rows"])

    fig, top = figure(
        15,
        7.6,
        3,
        "jev, second look",
        "Is the number stable? The same request twice, and the options in reverse",
        meta=(
            f"left: {len(dp)} Nouls from two identical runs of round one, |dP| median {p50:.3f}, p90 {p90:.3f}, "
            f"max {mx:.2f} | right: every Choice option's probability in served order against reversed order, "
            f"{len(xa)} points per round | winner unchanged {same_a}/{len(rows_a)} (snippet), {same_b}/{len(b['rows'])} "
            f"(stored text) | {a['model']} {a['commit']}"
        ),
    )
    h = top - 0.17
    ax = fig.add_axes([0.07, 0.12, 0.40, h])
    style_axes(ax)
    edges = np.arange(0, 0.105, 0.005)
    ax.hist(dp, bins=edges, color=GOLD, edgecolor=BG, linewidth=0.4)
    ax.set_yscale("log")
    for v, lab in ((p90, "p90"), (mx, "max")):
        ax.axvline(v, color=TEXT, linewidth=1.0, linestyle=":")
        ax.text(v, ax.get_ylim()[1] * 0.6, f" {lab} {v:.2f}", color=TEXT, fontsize=9)
    ax.set_xlabel("|P(yes) run 1 - P(yes) run 2|")
    ax.set_ylabel("Nouls (log)")
    panel_title(ax, "Identical requests, 560 Nouls: how far the number moves", width=60)

    ax2 = fig.add_axes([0.56, 0.12, 0.40, h])
    style_axes(ax2)
    ax2.plot([0, 1], [0, 1], color=RED, linewidth=1.0)
    ax2.scatter(xa, ya, s=16, color=GOLD, alpha=0.75, label="snippet (round one)")
    ax2.scatter(xb, yb, s=16, color=BLUE, alpha=0.75, label="stored text (round two)")
    ax2.set_xlim(-0.02, 1.02)
    ax2.set_ylim(-0.02, 1.02)
    ax2.set_xlabel("P(option), served order")
    ax2.set_ylabel("P(option), reversed order")
    leg = ax2.legend(loc="upper left", frameon=False, fontsize=9)
    for t in leg.get_texts():
        t.set_color(MUTED)
    panel_title(ax2, "Choice under option reversal: one point per option per search", width=60)
    verdict(
        fig,
        f"two runs agree to |dP| {p50:.3f} median, {p90:.2f} p90 · reversing the options keeps the winner "
        f"{same_a + same_b}/{len(rows_a) + len(b['rows'])}",
    )
    save(fig, "03-stability.png")


def fig04_wetness(a: dict, b: dict) -> None:
    order_a, n_open = order_rows(a["rows"])
    by_case = {r["case"]: r for r in b["rows"]}
    order_b = [by_case[r["case"]] for r in order_a]
    thr = 0.5
    wet_a = np.array([sum(p >= thr for p in r["noul"]) for r in order_a])
    wet_b = np.array([sum(p >= thr for p in r["noul"]) for r in order_b])
    opened = [
        (i, r) for i, r in enumerate(order_a) if r["group"] == "opened" and r["opened_rank_today"]
    ]
    own_a = np.array([r["noul"][r["opened_rank_today"] - 1] for _, r in opened])
    own_b = np.array([order_b[i]["noul"][r["opened_rank_today"] - 1] for i, r in opened])
    # everyone else in the same rows, for the crowd's median
    crowd_a = np.array(
        [
            np.median([p for j, p in enumerate(r["noul"]) if j != r["opened_rank_today"] - 1])
            for _, r in opened
        ]
    )
    crowd_b = np.array(
        [
            np.median(
                [p for j, p in enumerate(order_b[i]["noul"]) if j != r["opened_rank_today"] - 1]
            )
            for i, r in opened
        ]
    )
    # Where the opened note ranks by Noul inside its own row: the lift matters
    # only if it changes this.
    rank_a = np.array(
        [1 + sum(p > r["noul"][r["opened_rank_today"] - 1] for p in r["noul"]) for _, r in opened]
    )
    rank_b = np.array(
        [
            1 + sum(p > order_b[i]["noul"][r["opened_rank_today"] - 1] for p in order_b[i]["noul"])
            for i, r in opened
        ]
    )

    fig, top = figure(
        15,
        7.8,
        4,
        "jev, second look",
        "Full text lifts the opened note more than its neighbours, and barely moves its rank among them",
        meta=(
            f"left: per search, candidates with P(yes) >= {thr} out of 20, snippet -> stored text, median "
            f"{np.median(wet_a):.0f} -> {np.median(wet_b):.0f} | right: in the {len(opened)} opened rows, the opened note's "
            f"own P(yes) (cyan) median {np.median(own_a):.2f} -> {np.median(own_b):.2f}, against the median of its 19 "
            f"neighbours (grey) {np.median(crowd_a):.2f} -> {np.median(crowd_b):.2f} | the opened note's Noul rank inside "
            f"its row, median {np.median(rank_a):.0f} -> {np.median(rank_b):.0f}, first in {int((rank_a == 1).sum())} -> "
            f"{int((rank_b == 1).sum())} rows | {a['model']} {a['commit']}"
        ),
    )
    h = top - 0.17
    ax = fig.add_axes([0.07, 0.12, 0.40, h])
    style_axes(ax)
    for i, (x, y) in enumerate(zip(wet_a, wet_b)):
        col = GOLD if i < n_open else MUTED
        ax.plot([0, 1], [x, y], color=col, linewidth=1.2, alpha=0.8)
        ax.scatter([0, 1], [x, y], s=14, color=col, zorder=3)
    ax.set_xlim(-0.25, 1.25)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["200-char snippet", "full stored text"])
    ax.set_ylabel(f"candidates with P(yes) >= {thr}  (of 20)")
    ax.text(
        1.05,
        np.median(wet_b),
        f" median {np.median(wet_b):.0f}",
        color=TEXT,
        fontsize=9,
        va="center",
    )
    ax.text(
        -0.05,
        np.median(wet_a),
        f"median {np.median(wet_a):.0f} ",
        color=TEXT,
        fontsize=9,
        va="center",
        ha="right",
    )
    panel_title(
        ax,
        "How many candidates the Noul admits per search (gold: opened rows, grey: id lookups)",
        width=70,
    )

    ax2 = fig.add_axes([0.56, 0.12, 0.40, h])
    style_axes(ax2)
    for x, y in zip(crowd_a, crowd_b):
        ax2.plot([0, 1], [x, y], color=DIM, linewidth=1.0)
    for x, y in zip(own_a, own_b):
        ax2.plot([0, 1], [x, y], color=CYAN, linewidth=1.2, alpha=0.9)
        ax2.scatter([0, 1], [x, y], s=14, color=CYAN, zorder=3)
    ax2.axhline(thr, color=RED, linewidth=0.8, linestyle=":")
    ax2.set_xlim(-0.25, 1.25)
    ax2.set_ylim(0, 1)
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(["200-char snippet", "full stored text"])
    ax2.set_ylabel("P(yes)")
    panel_title(
        ax2,
        "The opened note's own P(yes) (cyan) against its row's median neighbour (grey)",
        width=70,
    )
    verdict(
        fig,
        f"opened note {np.median(own_a):.2f} -> {np.median(own_b):.2f} · its neighbours {np.median(crowd_a):.2f} -> "
        f"{np.median(crowd_b):.2f} · its rank in the row {np.median(rank_a):.0f} -> {np.median(rank_b):.0f} · "
        f"admitted per search {np.median(wet_a):.0f} -> {np.median(wet_b):.0f}",
    )
    save(fig, "04-wetness.png")


def fig05_latency(a: dict) -> None:
    calls = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
    r0 = [c for c in calls if c["tag"].startswith("rung0-")]
    r0b = [c for c in calls if c["tag"].startswith("rung0b")]
    q30 = json.load(BENCH30.open())
    q10 = json.load(BENCH10.open())
    q30_p50 = statistics.median(r["latency_s"] for r in q30["rows"])
    q10_p50 = q10["summary"]["latency_s"]["p50"]
    med0 = statistics.median(c["latency_s"] for c in r0)
    medb = statistics.median(c["latency_s"] for c in r0b)

    fig, top = figure(
        15,
        7.6,
        5,
        "jev, second look",
        "Every Jev call this section made, against the budget that kept the local reranker off",
        meta=(
            f"{len(r0)} round-one calls over two identical runs (median {med0 * 1000:.0f} ms) and {len(r0b)} round-two calls "
            f"(median {medb * 1000:.0f} ms), x = input tokens | red: the +1 s per search budget from #86 | grey: "
            f"Qwen3-Reranker-0.6B on this machine, p50 {q10_p50:.1f} s at depth 10 / 512 tokens and {q30_p50:.1f} s at "
            f"depth 30 (experiments/rerank_bench*.json) | {a['model']} {a['commit']}"
        ),
    )
    ax = fig.add_axes([0.08, 0.13, 0.88, top - 0.19])
    style_axes(ax)
    ax.set_yscale("log")
    ax.set_xscale("log")
    ax.scatter(
        [c["input_tokens"] for c in r0],
        [c["latency_s"] for c in r0],
        s=22,
        color=GOLD,
        alpha=0.8,
        label="round one, snippet",
    )
    ax.scatter(
        [c["input_tokens"] for c in r0b],
        [c["latency_s"] for c in r0b],
        s=22,
        color=BLUE,
        alpha=0.8,
        label="round two, stored text",
    )
    ax.axhline(BUDGET_S, color=RED, linewidth=1.0)
    ax.text(
        ax.get_xlim()[0] * 1.05,
        BUDGET_S * 1.12,
        "budget: +1 s per search (#86)",
        color=RED,
        fontsize=9,
    )
    for v, lab in (
        (q10_p50, "Qwen3 reranker, depth 10 / 512 tok, p50"),
        (q30_p50, "Qwen3 reranker, depth 30, p50"),
    ):
        ax.axhline(v, color=DIM, linewidth=6, alpha=0.9)
        ax.text(ax.get_xlim()[0] * 1.05, v * 1.12, lab, color=MUTED, fontsize=9)
    # Plain tick text: the serif face has no glyph for the minus in 10^-1.
    ax.set_yticks([0.1, 0.3, 1, 3, 10, 30])
    ax.set_yticklabels(["0.1 s", "0.3 s", "1 s", "3 s", "10 s", "30 s"])
    ax.set_xticks([2000, 5000, 10000, 20000])
    ax.set_xticklabels(["2k", "5k", "10k", "20k"])
    ax.minorticks_off()
    ax.set_xlabel("input tokens per request (log)")
    ax.set_ylabel("latency (log)")
    leg = ax.legend(loc="lower right", frameon=False, fontsize=9)
    for t in leg.get_texts():
        t.set_color(MUTED)
    panel_title(ax, "Latency against request size, one point per API call", width=80)
    verdict(
        fig,
        f"Jev median {med0 * 1000:.0f} ms and {medb * 1000:.0f} ms, max {max(c['latency_s'] for c in r0 + r0b) * 1000:.0f} ms · "
        f"local reranker {q10_p50:.1f} s and {q30_p50:.1f} s · budget 1 s",
    )
    save(fig, "05-latency.png")


if __name__ == "__main__":
    a = json.loads(SIDECAR.read_text())
    b = json.loads(SIDECAR2.read_text())
    run1 = json.loads(RUN1.read_text())
    fig03_stability(a, b, run1)
    fig04_wetness(a, b)
    fig05_latency(a)
