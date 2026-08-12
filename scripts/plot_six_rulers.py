#!/usr/bin/env python
"""36 — six rulers, one note (remix of 19 through the individual lens).

Section 19 scored six similarity metrics in aggregate and the null models
won. Here we hand the six rulers one concrete note — the corpus's biggest
hub — and watch what each ruler does to it; then we look at all six
568x568 matrices as images under one shared seriation, so metric
disagreement becomes texture.

    uv run --with matplotlib --with scipy python scripts/plot_six_rulers.py [1|2]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    DIM,
    DPI,
    FRAME,
    GOLD,
    MARGIN,
    MUTED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    saturated_magma,
    style_axes,
    verdict,
)
from rank_metrics import sim_matrices

ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"
OUTDIR = ASSETS / "36-six-rulers"
K = 10


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.name}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 2].rstrip() + ".."


def load():
    X = np.load(ASSETS / "17-corpus-growth" / "vectors-fresh.npz")["X"].astype(np.float32)
    man = json.loads((ASSETS / "18-sae-fingerprints" / "manifest.json").read_text())
    names = [n["name"] for n in man["notes"]]
    return X, names


def topk(sims: np.ndarray, i: int, k: int = K) -> list[int]:
    row = sims[i].copy()
    row[i] = -np.inf
    return list(np.argsort(-row)[:k])


def indegree(sims: np.ndarray, k: int = K) -> np.ndarray:
    n = len(sims)
    deg = np.zeros(n, dtype=int)
    for i in range(n):
        for j in topk(sims, i, k):
            deg[j] += 1
    return deg


# ---------------------------------------------------------------- figure 01


def fig01(X, names, mats):
    deg_cos = indegree(mats["cosine"])
    hub = int(np.argmax(deg_cos))
    base = set(topk(mats["cosine"], hub))

    meta = (
        f'the hub: "{short(names[hub], 52)}" — it sits in {deg_cos[hub]} of the 568 top-10 lists under cosine  ·  '
        "gold = neighbour shared with the cosine list  ·  n=568, k=10"
    )
    fig, top = figure(16.5, 8.6, 1, "six rulers", "One note, measured six ways", meta)

    order = ["cosine", "cosine-centred", "L1", "spearman", "spearman-centred", "csls"]
    degs = {m: indegree(mats[m]) for m in order}
    colw = (1 - 2 * MARGIN) / 6
    y0 = top - 0.075
    for j, m in enumerate(order):
        x = MARGIN + j * colw
        nb = topk(mats[m], hub)
        shared = len(set(nb) & base)
        fig.text(x, y0, m, color=TEXT, fontsize=9.5)
        fig.text(
            x,
            y0 - 0.032,
            f"keeps {shared}/10 of cosine's list" if m != "cosine" else "the reference list",
            color=GOLD if shared < 8 and m != "cosine" else MUTED,
            fontsize=7,
        )
        for r, i in enumerate(nb):
            col = GOLD if i in base else TEXT
            fig.text(x, y0 - 0.075 - r * 0.035, short(names[i], 24), color=col, fontsize=6.6)

    axb = fig.add_axes([MARGIN, 0.085, 1 - 2 * MARGIN, 0.16])
    style_axes(axb)
    xs = np.arange(6)
    vals = [degs[m][hub] for m in order]
    axb.bar(xs, vals, width=0.5, color=[DIM if m == "cosine" else GOLD for m in order])
    for x, v in zip(xs, vals):
        axb.text(x, v + 1.2, str(v), color=TEXT, fontsize=8, ha="center")
    axb.set_xticks(xs)
    axb.set_xticklabels(order, color=MUTED, fontsize=8)
    axb.set_ylabel("lists containing the hub", color=MUTED, fontsize=8)
    panel_title(axb, "how many of the 568 top-10 lists contain this one note, per ruler", 90)

    verdict(
        fig,
        f"centring halves the hub ({deg_cos[hub]} -> {degs['cosine-centred'][hub]}), CSLS cuts it to a third — hubness rides on the cone",
    )
    save(fig, "01-one-note-six-ways.png")


# ---------------------------------------------------------------- figure 02


def fig02(X, names, mats):
    from scipy.cluster.hierarchy import leaves_list, linkage

    order_keys = ["cosine", "cosine-centred", "L1", "spearman", "spearman-centred", "csls"]
    Z = linkage(1 - mats["cosine"], method="average")
    perm = leaves_list(Z)

    meta = (
        "each panel: the full 568x568 similarity matrix under one ruler, rows and columns in ONE shared order "
        "(cosine dendrogram leaves), 2x mean-pooled for print  ·  brightness = similarity, per-panel 1-99% limits"
    )
    fig, top = figure(16.5, 8.4, 2, "six rulers", "Six textures of the same corpus", meta)

    y_top = top - 0.06
    w = 0.145
    cmap = saturated_magma()
    for j, m in enumerate(order_keys):
        M = mats[m][np.ix_(perm, perm)]
        n2 = (M.shape[0] // 2) * 2
        M = M[:n2, :n2].reshape(n2 // 2, 2, n2 // 2, 2).mean(axis=(1, 3))
        lo, hi = np.percentile(M, [1, 99])
        W, H = fig.get_figwidth(), fig.get_figheight()
        h = w * W / H
        row, col = divmod(j, 3)
        ax = fig.add_axes([MARGIN + col * 0.17, y_top - row * (h + 0.115) - h, w, h])
        ax.imshow(M, cmap=cmap, vmin=lo, vmax=hi, interpolation="nearest")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(FRAME)
        panel_title(ax, m, 24)

    fig.text(
        MARGIN + 0.55,
        y_top - 0.05,
        "the same blocks appear in every panel — the map is the map,\n"
        "whichever ruler draws it. what changes is the background:\n"
        "centring and rank-transforms kill the cone's uniform glow\n"
        "(the top-left-to-everywhere brightness cosine carries), and\n"
        "CSLS dims the rows of notes that were close to everything.\n"
        "section 19 said the null models won; the textures say why —\n"
        "the six rulers were always measuring the same geometry.",
        color=MUTED,
        fontsize=9.5,
        linespacing=1.7,
        va="top",
    )

    verdict(fig, "same blocks in all six — the rulers disagree about the background, not the map")
    save(fig, "02-six-textures.png")


def main() -> None:
    which = set(sys.argv[1:]) or {"1", "2"}
    X, names = load()
    mats = sim_matrices(X)
    if "1" in which:
        fig01(X, names, mats)
    if "2" in which:
        fig02(X, names, mats)


if __name__ == "__main__":
    main()
