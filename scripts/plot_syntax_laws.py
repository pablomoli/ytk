"""Section 53 figures: which branching laws the repo's syntax trees obey.

  01  depth — real trees against random trees with identical degrees
  02  zipf — every file's subtree rank-size curve, and the null's
  03  horton — bifurcation and length ratios by Strahler order

Reads docs/assets/53-syntax-laws/measured.json (scripts/measure_syntax_laws.py)
and re-parses the corpus for the rank-size curves the sidecar does not carry.

uv run --extra dev --with matplotlib python scripts/plot_syntax_laws.py
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_syntax_laws import OUT as MEASURED
from measure_syntax_laws import corpus, flatten, measure, parser_for, random_tree_same_degrees
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
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

OUTDIR = MEASURED.parent
LANG_COLOR = {"python": GOLD, "typescript": BLUE, "tsx": CYAN}
LANG_LABEL = {"python": "Python", "typescript": "TypeScript", "tsx": "TSX"}


def save(fig, name: str) -> None:
    frame_panels(fig)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def legend(ax, **kw):
    return ax.legend(fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT, **kw)


def loglog_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    lx, ly = np.log(x), np.log(y)
    b, a = np.polyfit(lx, ly, 1)
    return float(b), float(math.exp(a))


def fig01(data: dict) -> None:
    files = data["files"]
    n = np.array([f["n"] for f in files], dtype=float)
    depth = np.array([f["max_depth"] for f in files], dtype=float)
    null_n = np.repeat(n, data["null_draws"])
    null_depth = np.array([d for f in files for d in f["null"]["max_depth"]], dtype=float)
    b_real, a_real = loglog_slope(n, depth)
    b_null, a_null = loglog_slope(null_n, null_depth)
    z = np.array(
        [
            (f["max_depth"] - np.mean(f["null"]["max_depth"]))
            / (np.std(f["null"]["max_depth"]) or 1e-9)
            for f in files
        ]
    )
    shallower = int((z < 0).sum())

    fig, top = figure(
        15,
        8.2,
        1,
        "syntax laws · depth",
        "The grammar builds bushes where chance builds spines",
        meta=(
            f"{len(files)} files, {int(n.sum()):,} named nodes · null: {data['null_draws']} uniform random plane trees "
            f"per file with the identical out-degree multiset (seed {data['seed']}) · "
            f"depth ~ n^{b_real:.2f} real vs n^{b_null:.2f} null · {shallower}/{len(files)} files shallower than every "
            f"null draw's mean · commit {data['commit']}"
        ),
    )
    gs = fig.add_gridspec(
        1, 2, left=0.055, right=0.975, top=top, bottom=0.10, wspace=0.16, width_ratios=[1.45, 1]
    )

    ax = fig.add_subplot(gs[0, 0])
    style_axes(ax)
    ax.scatter(null_n, null_depth, s=6, color=DIM, alpha=0.55, linewidths=0, label="null draws")
    for lang, color in LANG_COLOR.items():
        m = np.array([f["lang"] == lang for f in files])
        ax.scatter(n[m], depth[m], s=22, color=color, linewidths=0, label=LANG_LABEL[lang])
    xs = np.geomspace(n.min(), n.max(), 50)
    ax.plot(xs, a_null * xs**b_null, color=MUTED, lw=1.0, ls="--")
    ax.plot(xs, a_real * xs**b_real, color=TEXT, lw=1.0, ls="--")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("named nodes in file")
    ax.set_ylabel("max depth")
    panel_title(ax, "max depth against size, every file and its twenty nulls")
    legend(ax, loc="upper left")

    ax = fig.add_subplot(gs[0, 1])
    style_axes(ax)
    bins = np.linspace(min(z.min(), -8), max(z.max(), 2), 36)
    ax.hist(z, bins=bins, color=GOLD, alpha=0.9)
    ax.axvspan(-2, 2, color=DIM, alpha=0.6, zorder=0)
    ax.axvline(0, color=MUTED, lw=1.0)
    ax.set_xlabel("depth z-score against the file's own null")
    ax.set_ylabel("files")
    panel_title(ax, "per-file z; grey band is the null's ±2σ")

    verdict(
        fig,
        f"{shallower} of {len(files)} files shallower than their degree-matched null: depth grows like n^{b_real:.2f}, not n^{b_null:.2f}",
    )
    save(fig, "01-depth.png")


def curves(sample_nulls: int, seed: int) -> list[tuple[str, np.ndarray, list[np.ndarray]]]:
    """Per file: language, real rank-size curve, a few null rank-size curves."""
    rng = random.Random(seed)
    out = []
    for path, lang in corpus():
        parent, _ = flatten(parser_for(lang).parse(path.read_bytes()).root_node)
        if len(parent) < 20:
            continue
        real = np.sort(np.array(measure(parent)["sizes"]))[::-1]
        nulls = [
            np.sort(np.array(measure(random_tree_same_degrees(parent, rng))["sizes"]))[::-1]
            for _ in range(sample_nulls)
        ]
        out.append((lang, real, nulls))
    return out


def fig02(data: dict) -> None:
    files = data["files"]
    real_slopes = {
        lang: np.array([f["zipf_slope"] for f in files if f["lang"] == lang]) for lang in LANG_COLOR
    }
    null_slopes = np.array([s for f in files for s in f["null"]["zipf_slope"]])
    all_real = np.concatenate(list(real_slopes.values()))
    cs = curves(sample_nulls=2, seed=data["seed"])

    fig, top = figure(
        15,
        8.2,
        2,
        "syntax laws · zipf",
        "Subtree sizes are Zipfian at slope -1, and -1 belongs to the grammar",
        meta=(
            f"rank-size OLS slope over subtrees of size 2 and up · real median {np.median(all_real):.2f} "
            f"(Python {np.median(real_slopes['python']):.2f}, TypeScript {np.median(real_slopes['typescript']):.2f}, "
            f"TSX {np.median(real_slopes['tsx']):.2f}) · degree-matched null median {np.median(null_slopes):.2f} · "
            f"{len(files)} files, {data['null_draws']} nulls each · commit {data['commit']}"
        ),
    )
    gs = fig.add_gridspec(
        1, 2, left=0.055, right=0.975, top=top, bottom=0.10, wspace=0.16, width_ratios=[1.45, 1]
    )

    ax = fig.add_subplot(gs[0, 0])
    style_axes(ax)
    for _, _, nulls in cs:
        for c in nulls:
            ax.plot(np.arange(1, len(c) + 1), c, color=DIM, lw=0.5, alpha=0.5)
    for lang, real, _ in cs:
        ax.plot(np.arange(1, len(real) + 1), real, color=LANG_COLOR[lang], lw=0.6, alpha=0.75)
    ref = np.geomspace(1, 3e4, 20)
    ax.plot(ref, 3e4 / ref, color=TEXT, lw=1.0, ls="--")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("rank of subtree by size")
    ax.set_ylabel("subtree size (named nodes)")
    panel_title(ax, "every file's rank-size curve; grey are its nulls; dashed is slope -1")
    from matplotlib.lines import Line2D

    handles = [Line2D([], [], color=c, lw=1.5, label=LANG_LABEL[k]) for k, c in LANG_COLOR.items()]
    handles.append(Line2D([], [], color=DIM, lw=1.5, label="degree-matched null"))
    legend(ax, handles=handles, loc="upper right")

    ax = fig.add_subplot(gs[0, 1])
    style_axes(ax)
    bins = np.linspace(-2.0, -0.7, 40)
    ax.hist(null_slopes, bins=bins, color=DIM, alpha=0.95, label="null", density=True)
    for lang, color in LANG_COLOR.items():
        ax.hist(
            real_slopes[lang],
            bins=bins,
            color=color,
            alpha=0.75,
            label=LANG_LABEL[lang],
            density=True,
        )
    ax.axvline(-1.0, color=RED, lw=1.0, ls="--")
    ax.set_xlabel("rank-size slope")
    ax.set_ylabel("density")
    panel_title(ax, "slope per file against the null; red is -1")
    legend(ax, loc="upper left")

    verdict(
        fig,
        f"real {np.median(all_real):.2f} vs null {np.median(null_slopes):.2f}: same degrees, different law",
    )
    save(fig, "02-zipf.png")


def ratio_by_order(files: list[dict], key: str, orders: int, null: bool) -> list[np.ndarray]:
    cols = []
    for k in range(orders):
        if null:
            vals = [x for f in files if len(f["null"][key]) > k for x in f["null"][key][k]]
        else:
            vals = [f[key][k] for f in files if len(f[key]) > k]
        cols.append(np.array([v for v in vals if v == v], dtype=float))
    return cols


def band(ax, cols: list[np.ndarray], color: str, label: str, x0: float = 1.0) -> None:
    xs = np.arange(len(cols)) + x0
    med = np.array([np.median(c) for c in cols])
    lo = np.array([np.quantile(c, 0.25) for c in cols])
    hi = np.array([np.quantile(c, 0.75) for c in cols])
    ax.fill_between(xs, lo, hi, color=color, alpha=0.25 if color != DIM else 0.7, linewidths=0)
    ax.plot(xs, med, color=color, lw=1.8, marker="o", ms=4, label=label)


def fig03(data: dict) -> None:
    files = [f for f in data["files"] if f["strahler"] >= 5]
    orders = 4  # ratios 1-2 through 4-5, where every kept file has a value
    fig, top = figure(
        15,
        8.2,
        3,
        "syntax laws · horton",
        "Horton's ratios are not constant: branching rises with order, stream length falls",
        meta=(
            f"{len(files)} files with Strahler order 5 and up · ratio between consecutive orders, median with interquartile band · "
            f"R_B real order 1-2 {np.median(ratio_by_order(files, 'r_b', 1, False)[0]):.2f} to "
            f"4-5 {np.median(ratio_by_order(files, 'r_b', 4, False)[3]):.2f}; null "
            f"{np.median(ratio_by_order(files, 'r_b', 1, True)[0]):.2f} to {np.median(ratio_by_order(files, 'r_b', 4, True)[3]):.2f} · "
            f"R_L real {np.median(ratio_by_order(files, 'r_l', 1, False)[0]):.2f} to "
            f"{np.median(ratio_by_order(files, 'r_l', 4, False)[3]):.2f} · river networks sit near R_B 4, R_L 2 at every order · "
            f"commit {data['commit']}"
        ),
    )
    gs = fig.add_gridspec(1, 2, left=0.055, right=0.975, top=top, bottom=0.10, wspace=0.16)

    ax = fig.add_subplot(gs[0, 0])
    style_axes(ax)
    band(ax, ratio_by_order(files, "r_b", orders, True), DIM, "degree-matched null")
    for lang, color in LANG_COLOR.items():
        sub = [f for f in files if f["lang"] == lang]
        if len(sub) >= 5:
            band(ax, ratio_by_order(sub, "r_b", orders, False), color, LANG_LABEL[lang])
    ax.axhline(4.0, color=RED, lw=1.0, ls="--")
    ax.set_xticks(range(1, orders + 1))
    ax.set_xticklabels([f"{k}-{k + 1}" for k in range(1, orders + 1)])
    ax.set_xlabel("Strahler order pair")
    ax.set_ylabel("bifurcation ratio  N_k / N_k+1")
    panel_title(ax, "bifurcation ratio by order; red is Horton's river constant")
    legend(ax, loc="upper left")

    ax = fig.add_subplot(gs[0, 1])
    style_axes(ax)
    band(ax, ratio_by_order(files, "r_l", orders, True), DIM, "degree-matched null")
    for lang, color in LANG_COLOR.items():
        sub = [f for f in files if f["lang"] == lang]
        if len(sub) >= 5:
            band(ax, ratio_by_order(sub, "r_l", orders, False), color, LANG_LABEL[lang])
    ax.axhline(2.0, color=RED, lw=1.0, ls="--")
    ax.axhline(1.0, color=MUTED, lw=0.8)
    ax.set_xticks(range(1, orders + 1))
    ax.set_xticklabels([f"{k}-{k + 1}" for k in range(1, orders + 1)])
    ax.set_xlabel("Strahler order pair")
    ax.set_ylabel("length ratio  L_k+1 / L_k")
    panel_title(ax, "stream length ratio by order; below the grey line, higher orders are shorter")
    legend(ax, loc="upper right")

    verdict(
        fig,
        "branching rises with order while the null falls; stream length drops below 1 by order 3",
    )
    save(fig, "03-horton.png")


def main() -> None:
    data = json.loads(MEASURED.read_text())
    fig01(data)
    fig02(data)
    fig03(data)


if __name__ == "__main__":
    main()
