"""Corpus-shape primer — the three concepts behind the 12/15 figure sets.

Pedagogical companions, one concept per figure, each answering a question
raised while reading the embedding-geometry results:

    01  what "the mean is 11x chance" means: cancellation, and its failure
    02  what the participation ratio counts, and why n=493 caps it at 492
    03  what a null distribution is, and what z = 17 looks like drawn

STRICTLY READ-ONLY: reads the frozen vectors.npz captured by
scripts/tag_coherence.py. Touches neither the vault nor Chroma.

    uv run --with matplotlib python scripts/plot_primer.py
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BLUE,
    CYAN,
    DIM,
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    RED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

SRC = Path(__file__).resolve().parents[1] / "docs" / "assets" / "10-tag-coherence"
OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "16-corpus-primer"
SEED = 20260803
DRAWS = 300
TAG = "ai-coding"


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def _footer(fig, y: float, text: str, width: int = 130) -> None:
    fig.text(MARGIN, y, textwrap.fill(text, width), color=MUTED, fontsize=9.5, linespacing=1.6)


def load():
    X = np.load(SRC / "vectors.npz")["X"].astype(np.float64)
    labels = json.loads((SRC / "tags.json").read_text())["labels"]
    return X, labels


def fig01() -> None:
    """Cancellation: why random arrows average to ~0, and why these don't."""
    X, _ = load()
    rng = np.random.default_rng(SEED)

    fig, top = figure(
        16.5,
        7.4,
        1,
        "why the mean should have been tiny",
        "Random directions cancel when averaged — the vault's do not, and more notes will not fix it",
        f"average of n unit arrows: random directions shrink like 1 / sqrt(n)  ·  "
        f"the vault's average holds at {np.linalg.norm(X.mean(0)):.2f} at every sample size",
    )
    gs = fig.add_gridspec(
        1,
        3,
        width_ratios=[1, 1, 1.5],
        left=0.045,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.185,
        wspace=0.22,
    )

    # 60 flat-random 2D arrows and their mean
    n_toy = 60
    for col, (title, thetas, color) in enumerate(
        [
            ("random directions: they cancel", rng.uniform(0, 2 * np.pi, n_toy), DIM),
            (
                "a shared lean: they cannot cancel",
                rng.normal(np.pi / 4, 0.55, n_toy),
                DIM,
            ),
        ]
    ):
        ax = fig.add_subplot(gs[col])
        vx, vy = np.cos(thetas), np.sin(thetas)
        for x, y in zip(vx, vy):
            ax.plot([0, x], [0, y], color=color, linewidth=0.8, alpha=0.6)
        mx, my = vx.mean(), vy.mean()
        ax.annotate(
            "",
            xy=(mx, my),
            xytext=(0, 0),
            arrowprops={"arrowstyle": "-|>", "color": GOLD, "linewidth": 2.6},
        )
        ax.annotate(
            f"the average arrow\nlength {np.hypot(mx, my):.2f}",
            (mx, my),
            textcoords="offset points",
            xytext=(10, 8),
            color=GOLD,
            fontsize=TICK_SIZE + 0.5,
        )
        ax.set_xlim(-1.15, 1.15)
        ax.set_ylim(-1.15, 1.15)
        ax.set_aspect("equal")
        style_axes(ax)
        ax.set_xticks([])
        ax.set_yticks([])
        panel_title(ax, title, width=34)
        ax.set_xlabel(f"{n_toy} arrows, all length 1")

    # convergence: the user's intuition, drawn
    ax = fig.add_subplot(gs[2])
    ns = np.unique(np.geomspace(5, len(X), 14).astype(int))
    reps = 60
    rand_curve, corp_curve = [], []
    for n in ns:
        vals = []
        for _ in range(reps):
            V = rng.normal(size=(n, 1024))
            V /= np.linalg.norm(V, axis=1, keepdims=True)
            vals.append(float(np.linalg.norm(V.mean(0))))
        rand_curve.append(np.mean(vals))
        vals = [
            float(np.linalg.norm(X[rng.choice(len(X), size=n, replace=False)].mean(0)))
            for _ in range(reps)
        ]
        corp_curve.append(np.mean(vals))
    ax.plot(ns, corp_curve, color=GOLD, linewidth=2.2, label="the vault")
    ax.plot(ns, rand_curve, color=CYAN, linewidth=2.0, label="random directions")
    ax.plot(ns, 1 / np.sqrt(ns), color=RED, linewidth=1.2, linestyle="--", label="1 / sqrt(n)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    style_axes(ax)
    ax.set_xlabel("number of arrows averaged (log)")
    ax.set_ylabel("length of the average arrow (log)")
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="lower left")
    for t in leg.get_texts():
        t.set_color(MUTED)
    ax.annotate(
        "keeps falling forever",
        (ns[-1], rand_curve[-1]),
        textcoords="offset points",
        xytext=(-104, -12),
        color=CYAN,
        fontsize=TICK_SIZE,
    )
    ax.annotate(
        "flattens at 0.51\n= the shared direction",
        (ns[-1], corp_curve[-1]),
        textcoords="offset points",
        xytext=(-118, 10),
        color=GOLD,
        fontsize=TICK_SIZE,
    )
    panel_title(ax, "your intuition, tested: does the average shrink to zero?", width=48)

    _footer(
        fig,
        0.045,
        "The intuition is correct for random arrows: noise cancels, and the average keeps shrinking "
        "like 1/sqrt(n) forever. The vault follows a different law: its average is shared-direction "
        "plus noise. The noise part cancels; the shared part is the same in every note, and no "
        "amount of averaging removes something everyone agrees on. The plateau height IS the "
        "shared component's size. More notes sharpen the 0.51; they do not shrink it.",
    )
    save(fig, "01-cancellation.png")


def fig02() -> None:
    """What the participation ratio counts, and the n-1 ceiling."""
    X, _ = load()
    # the canonical spectrum from 12-embedding-geometry: centred raw corpus
    ev = np.linalg.svd(X - X.mean(0), compute_uv=False) ** 2
    ev = ev / ev.sum()
    pr = float(1.0 / (ev**2).sum())
    ev = ev[ev > ev.max() * 1e-9]  # drop the numerically-zero tail beyond rank n-1

    fig, top = figure(
        16.5,
        7.4,
        2,
        "counting directions that matter",
        "The participation ratio asks: this uneven spread behaves like an even spread over how many?",
        "same formula as the effective number of parties in an election  ·  "
        "PR = 1 / sum(share^2)  ·  computed on the centred corpus",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.15, 1.3],
        left=0.05,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.27,
        wspace=0.2,
    )

    # three toy parliaments
    ax = fig.add_subplot(gs[0])
    toys = [
        ("one direction\nhas everything", np.array([1.0]), 0),
        ("spread evenly\nover ten", np.full(10, 0.1), 3),
        ("halving shares\n(0.5, 0.25, ...)", (lambda p: p / p.sum())(0.5 ** np.arange(1, 9)), 16),
    ]
    for label, shares, x0 in toys:
        prt = 1.0 / float((shares**2).sum())
        xs = x0 + np.arange(len(shares))
        ax.bar(xs, shares, width=0.85, color=BLUE, alpha=0.92)
        ax.text(
            x0 + len(shares) / 2 - 0.5,
            max(shares) + 0.06,
            f"PR = {prt:.0f}",
            ha="center",
            color=GOLD,
            fontsize=12,
            fontweight="bold",
        )
        ax.text(
            x0 + len(shares) / 2 - 0.5, -0.16, label, ha="center", color=MUTED, fontsize=TICK_SIZE
        )
    ax.set_ylim(0, 1.12)
    ax.set_xticks([])
    style_axes(ax)
    ax.spines["bottom"].set_visible(False)
    panel_title(ax, "the formula on three toy spreads", width=40)
    ax.set_ylabel("share of total spread")

    # the real spectrum
    ax = fig.add_subplot(gs[1])
    ks = np.arange(1, len(ev) + 1)
    ax.plot(ks, ev, color=GOLD, linewidth=1.8)
    ax.axvline(pr, color=CYAN, linewidth=1.4, linestyle="--")
    ax.text(pr * 1.15, ev.max() * 0.5, f"PR = {pr:.0f}", color=CYAN, fontsize=11)
    ax.axvline(len(ev), color=RED, linewidth=1.4, linestyle=":")
    ax.text(
        len(ev) * 0.62,
        ev.max() * 0.12,
        f"hard stop at {len(ev)}\n= n - 1",
        color=RED,
        fontsize=TICK_SIZE,
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    style_axes(ax)
    ax.set_xlabel("direction, sorted widest first (log)")
    ax.set_ylabel("share of spread (log)")
    panel_title(ax, f"the vault's 493 notes: {len(ev)} visible directions, PR {pr:.0f}", width=52)

    _footer(
        fig,
        0.038,
        "Why the hard stop: 2 points can only show 1 direction (the line through them), 3 points at "
        "most 2 (their plane), n points at most n - 1. The room has 1024 axes but 493 notes can "
        "only ever witness 492 of them — the spectrum literally ends there. So '104 of 1024' really "
        "means '104 of the 492 measurable': a fifth of what the sample could show, spread thin, no "
        "dominant few. The estimate can grow as the vault grows; re-measure, don't assume.",
    )
    save(fig, "02-participation-ratio.png")


def fig03() -> None:
    """The null distribution: what fake tags score, and where the real one sits."""
    X, labels = load()
    rng = np.random.default_rng(SEED)
    idx = [i for i, ts in enumerate(labels) if TAG in ts]
    k = len(idx)

    def tightness(members: np.ndarray) -> float:
        S = X[members] @ X[members].T
        return float((S.sum() - np.trace(S)) / (len(members) * (len(members) - 1)))

    obs = tightness(np.array(idx))
    fakes = np.array([tightness(rng.choice(len(X), size=k, replace=False)) for _ in range(DRAWS)])
    mu, sd = float(fakes.mean()), float(fakes.std())
    z = (obs - mu) / sd

    fig, top = figure(
        16.5,
        7.6,
        3,
        "the null distribution, drawn",
        f"z = {z:.0f} means: fake tags never get anywhere near what {TAG} actually scores",
        f"{DRAWS} fake tags, each {k} notes drawn at random  ·  tightness = average pairwise "
        "similarity within the group  ·  raw (uncentred) space, matching the quoted numbers",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1, 1.55],
        left=0.045,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.185,
        wspace=0.18,
    )

    # one real tag vs one fake tag, on the map
    Xc = X - X.mean(0)
    Xc /= np.linalg.norm(Xc, axis=1, keepdims=True)
    B = np.linalg.svd(Xc - Xc.mean(0), full_matrices=False)[2][:2]
    P = Xc @ B.T
    fake = rng.choice(len(X), size=k, replace=False)
    ax = fig.add_subplot(gs[0])
    ax.scatter(P[:, 0], P[:, 1], s=8, c=DIM, alpha=0.6, linewidths=0)
    ax.scatter(P[idx, 0], P[idx, 1], s=26, c=GOLD, linewidths=0, label=f"{TAG} ({k} notes)")
    ax.scatter(
        P[fake, 0],
        P[fake, 1],
        s=34,
        facecolors="none",
        edgecolors=CYAN,
        linewidths=1.1,
        label=f"one fake tag ({k} random)",
    )
    ax.set_aspect("equal")
    style_axes(ax)
    ax.set_xticks([])
    ax.set_yticks([])
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="upper left")
    for t in leg.get_texts():
        t.set_color(MUTED)
    panel_title(ax, "a real tag huddles; a fake tag is confetti", width=40)
    ax.set_xlabel("2D view for orientation only — tightness is measured in 1024-d")

    # the histogram that defines z
    ax = fig.add_subplot(gs[1])
    ax.hist(fakes, bins=32, color=CYAN, alpha=0.9)
    ax.axvline(obs, color=GOLD, linewidth=2.2)
    ax.annotate(
        f"the real tag\n{obs:+.3f}",
        (obs, 10.0),
        textcoords="offset points",
        xytext=(-8, 30),
        color=GOLD,
        fontsize=11,
        ha="right",
    )
    ax.annotate(
        "",
        xy=(mu + sd, 11.0),
        xytext=(mu, 11.0),
        arrowprops={"arrowstyle": "<->", "color": RED, "linewidth": 1.4},
    )
    ax.text(
        mu + sd / 2,
        12.2,
        f"one yardstick\n(sd = {sd:.4f})",
        ha="center",
        color=RED,
        fontsize=TICK_SIZE,
    )
    ax.annotate(
        f"fakes average {mu:+.3f} — the glow\ngives every group this for free",
        (mu, 5.0),
        textcoords="offset points",
        xytext=(12, 58),
        color=TEXT,
        fontsize=TICK_SIZE,
    )
    style_axes(ax)
    ax.set_xlim(min(fakes.min(), mu - 2 * sd), obs * 1.08)
    ax.set_xlabel("tightness of the group (average pairwise similarity)")
    ax.set_ylabel(f"how many of the {DRAWS} fakes scored this")
    panel_title(
        ax, f"{DRAWS} fakes pile up on the left; the real tag is {z:.0f} yardsticks away", width=54
    )

    _footer(
        fig,
        0.045,
        f"This is everything z is. Tightness itself: {obs:+.3f}. The null: fake same-size groups "
        f"score {mu:+.3f} give or take {sd:.4f}. z = (observed - fake average) / fake scatter = "
        f"{z:.0f}: the distance to the pile, measured in units of the pile's own width. 'Sits "
        "tight' and 'z is huge' are one fact — z is how sure you are the huddle is not luck.",
    )
    print(f"{TAG}: k={k}  obs={obs:+.4f}  null={mu:+.4f} sd={sd:.4f}  z={z:.1f}")
    save(fig, "03-null-and-z.png")


if __name__ == "__main__":
    plt.style.use("dark_background")
    fig01()
    fig02()
    fig03()
