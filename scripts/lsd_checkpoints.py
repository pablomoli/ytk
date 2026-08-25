"""Section 53 checkpoints C0-C4 for `ytk lsd`, drawn from one frozen run.

    uv run --with matplotlib python scripts/lsd_checkpoints.py --seed 53 --out <dir> [--run RUN_ID]

Without --run a new run is sampled and saved under ~/.ytk/lsd/runs/. Each
figure is one claim; the math is in the section README, not here.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DIM,
    DPI,
    GOLD,
    MUTED,
    PURPLE,
    RED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ytk import lsd

POOL_COLOR = {"ortho": GOLD, "near": BLUE, "rand": CYAN}
SECTION = 53


def sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "?"


def save(fig, out: Path, name: str) -> None:
    frame_panels(fig)
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / name, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out / name)


def hist(ax, a, color, bins, label=None, alpha=0.85):
    ax.hist(
        a, bins=bins, color=color, alpha=alpha, density=True, label=label, histtype="stepfilled"
    )


def c0(run: lsd.Run, X, Xc, out: Path) -> None:
    rng = np.random.default_rng(run.seed)
    i = rng.integers(0, len(X), 200_000)
    j = rng.integers(0, len(X), 200_000)
    k = i != j
    raw = np.einsum("ij,ij->i", X[i[k]], X[j[k]])
    cen = np.einsum("ij,ij->i", Xc[i[k]], Xc[j[k]])
    strip = 0.1
    f_raw = float((np.abs(raw) < strip).mean())
    f_cen = float((np.abs(cen) < strip).mean())
    mu2 = run.mean_norm**2
    fig, top = figure(
        13,
        7.2,
        SECTION,
        "C0 · THE CONE, DRAWN",
        "Random note pairs: where 'orthogonal' lives before and after removing the shared direction",
        f"{run.n_notes} source notes · {k.sum():,} uniform pairs · |mu| = {run.mean_norm:.3f}, "
        f"|mu|^2 = {mu2:.3f} · raw median {np.median(raw):.3f} · centred median {np.median(cen):.3f} · "
        f"|cos| < {strip}: raw {100 * f_raw:.1f}%, centred {100 * f_cen:.1f}% · {sha()}",
    )
    axes = fig.subplots(
        1, 2, gridspec_kw={"top": top, "bottom": 0.10, "left": 0.06, "right": 0.98, "wspace": 0.16}
    )
    bins = np.linspace(-0.35, 0.75, 160)
    for ax, a, color, title in (
        (axes[0], raw, GOLD, "as stored: every pair floats on $|\\mu|^2$"),
        (axes[1], cen, BLUE, "centred: the same pairs straddle zero"),
    ):
        ax.axvspan(-strip, strip, color=DIM, alpha=0.9, zorder=0)
        hist(ax, a, color, bins)
        ax.axvline(0, color=MUTED, lw=0.8)
        panel_title(ax, title)
        style_axes(ax)
        ax.set_xlabel("cosine between two random notes", color=MUTED)
        ax.set_xlim(bins[0], bins[-1])
        ax.set_yticks([])
    axes[0].axvline(mu2, color=RED, lw=1.2, ls="--")
    axes[0].text(mu2 + 0.01, axes[0].get_ylim()[1] * 0.92, "$|\\mu|^2$", color=RED, fontsize=9)
    axes[0].text(
        0,
        axes[0].get_ylim()[1] * 0.5,
        f"{100 * f_raw:.1f}% of pairs",
        color=TEXT,
        ha="center",
        fontsize=9,
    )
    axes[1].text(
        0,
        axes[1].get_ylim()[1] * 0.5,
        f"{100 * f_cen:.1f}% of pairs",
        color=TEXT,
        ha="center",
        fontsize=9,
    )
    verdict(
        fig,
        f"the orthogonal strip holds {100 * f_raw:.1f}% of pairs raw and {100 * f_cen:.1f}% centred: Tan's rule is a centred rule",
    )
    save(fig, out, "c0-the-cone.png")


def c1(run: lsd.Run, Xc, out: Path) -> None:
    rng = np.random.default_rng(run.seed + 1)
    bg = lsd.background_cosines(Xc, rng)
    sd = bg.std()
    floor = float(np.percentile(bg, 0.5))
    keep = rng.random(len(bg)) < lsd.tilt_acceptance(bg, floor, sd)
    tilt = bg[keep]
    tailpool = bg[bg <= run.tail]
    ortho = np.array([p.cos_c for p in run.pairs if p.pool == "ortho"])
    rand = np.array([p.cos_c for p in run.pairs if p.pool == "rand"])
    med = float(np.median(bg))
    shift_tilt = (med - np.median(tilt)) / sd
    shift_tail = (med - np.median(tailpool)) / sd
    shift_drawn = (np.median(rand) - np.median(ortho)) / sd
    fig, top = figure(
        13,
        7.2,
        SECTION,
        "C1 · TEMPERATURE VS TAIL",
        "Two ways to leave the cone: a Boltzmann tilt exp(-cos / T) at T = background std, or the p10 tail",
        f"background std {sd:.3f} (the unit) · tilt accepts {100 * keep.mean():.0f}%, median shift {shift_tilt:.2f} std · "
        f"tail p{lsd.TAIL_PCT:.0f} = {run.tail:.3f}, shift {shift_tail:.2f} std · drawn ORTHO {np.median(ortho):.3f} vs RAND "
        f"{np.median(rand):.3f}, {shift_drawn:.2f} std · n = {len(ortho)} + {len(rand)} · {sha()}",
    )
    axes = fig.subplots(
        1, 2, gridspec_kw={"top": top, "bottom": 0.10, "left": 0.06, "right": 0.98, "wspace": 0.16}
    )
    bins = np.linspace(-0.35, 0.45, 120)
    ax = axes[0]
    hist(ax, bg, DIM, bins, alpha=1.0)
    hist(ax, tilt, BLUE, bins, alpha=0.55)
    hist(ax, tailpool, GOLD, bins, alpha=0.75)
    for a, c in ((bg, MUTED), (tilt, BLUE), (tailpool, GOLD)):
        ax.axvline(float(np.median(a)), color=c, lw=1)
    ax2 = ax.twinx()
    xs = np.linspace(bins[0], bins[-1], 400)
    ax2.plot(xs, np.minimum(1, lsd.tilt_acceptance(xs, floor, sd)), color=BLUE, lw=1.4, ls="--")
    ax2.set_ylim(0, 1.05)
    ax2.set_yticks([])
    for sp in ax2.spines.values():
        sp.set_visible(False)
    ax.axvline(run.tail, color=RED, ls="--", lw=1.2)
    ax.text(run.tail + 0.01, ax.get_ylim()[1] * 0.9, "tail", color=RED, fontsize=9)
    panel_title(ax, "the null (grey), the tilt it becomes (blue), the tail it keeps (gold)")
    style_axes(ax)
    ax.set_yticks([])
    ax.set_xlim(bins[0], bins[-1])
    ax.set_xlabel("centred cosine of uniform pairs", color=MUTED)
    ax = axes[1]
    hist(ax, rand, CYAN, bins, alpha=0.6)
    hist(ax, ortho, GOLD, bins, alpha=0.75)
    ax.axvline(float(np.median(rand)), color=CYAN, lw=1)
    ax.axvline(float(np.median(ortho)), color=GOLD, lw=1)
    ax.axvline(run.tail, color=RED, ls="--", lw=1.2)
    panel_title(ax, "what the sampler drew: ORTHO (gold) against RAND (cyan)")
    style_axes(ax)
    ax.set_yticks([])
    ax.set_xlim(bins[0], bins[-1])
    ax.set_xlabel("centred cosine of sampled pairs", color=MUTED)
    verdict(
        fig,
        f"the temperature knob moves the median {shift_tilt:.2f} std, the tail rule {shift_tail:.2f}; ORTHO as drawn sits {shift_drawn:.2f} std left of RAND",
    )
    save(fig, out, "c1-temperature-vs-tail.png")


def c2(run: lsd.Run, Xc, out: Path) -> None:
    n = run.n_notes
    counts = {
        p: np.bincount(
            [q.i for q in run.pairs if q.pool == p] + [q.j for q in run.pairs if q.pool == p],
            minlength=n,
        )
        for p in lsd.POOLS
    }
    S = Xc @ Xc.T
    np.fill_diagonal(S, -np.inf)
    top10 = np.argpartition(-S, 10, axis=1)[:, :10]
    hub = np.bincount(top10.ravel(), minlength=n)
    fig, top = figure(
        13,
        6.8,
        SECTION,
        "C2 · HUBS AT THE GATE",
        "How often each note is drawn, per pool, against how often it is a top-10 neighbour",
        " · ".join(
            f"{p.upper()} max {counts[p].max()} / distinct {int((counts[p] > 0).sum())}"
            for p in lsd.POOLS
        )
        + f" · top-10 hub max {hub.max()} of {n} lists · {sha()}",
    )
    axes = fig.subplots(
        1, 4, gridspec_kw={"top": top, "bottom": 0.12, "left": 0.05, "right": 0.99, "wspace": 0.12}
    )
    ymax = max(max(c.max() for c in counts.values()), 1)
    for ax, p in zip(axes[:3], lsd.POOLS):
        c = np.sort(counts[p])[::-1][:80]
        ax.bar(np.arange(len(c)), c, color=POOL_COLOR[p], width=1.0)
        ax.set_ylim(0, ymax * 1.05)
        panel_title(ax, f"{p.upper()}: draws per note, top 80")
        style_axes(ax)
        ax.set_xlabel("notes, sorted", color=MUTED)
    ax = axes[3]
    h = np.sort(hub)[::-1][:80]
    ax.bar(np.arange(len(h)), h, color=DIM, width=1.0)
    panel_title(ax, "top-10 neighbour lists per note (section 36's hubs)")
    style_axes(ax)
    ax.set_xlabel("notes, sorted", color=MUTED)
    rho = {p: float(np.corrcoef(counts[p], hub)[0, 1]) for p in lsd.POOLS}
    verdict(
        fig,
        "draw count vs hubness r: "
        + ", ".join(f"{p} {rho[p]:+.2f}" for p in lsd.POOLS)
        + " — only NEAR should lean on hubs",
    )
    save(fig, out, "c2-hubs.png")


def c3(run: lsd.Run, out: Path) -> None:
    fig, top = figure(
        13,
        6.4,
        SECTION,
        "C3 · THREE POOLS, ONE AXIS",
        "The frozen pairs: centred cosine per pool, raw cosine in the meta line",
        " · ".join(
            f"{p.upper()} centred {np.median([q.cos_c for q in run.pairs if q.pool == p]):.3f} / raw {np.median([q.cos_raw for q in run.pairs if q.pool == p]):.3f}"
            for p in lsd.POOLS
        )
        + f" · seed {run.seed} · run {run.run_id} · {sha()}",
    )
    ax = fig.subplots(1, 1, gridspec_kw={"top": top, "bottom": 0.12, "left": 0.05, "right": 0.99})
    bins = np.linspace(-0.35, 0.9, 150)
    for p in lsd.POOLS:
        a = np.array([q.cos_c for q in run.pairs if q.pool == p])
        hist(ax, a, POOL_COLOR[p], bins, alpha=0.6, label=p.upper())
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.axvline(run.tail, color=RED, ls="--", lw=1)
    panel_title(ax, "ORTHO gold · NEAR blue · RAND cyan · tail red")
    style_axes(ax)
    ax.set_yticks([])
    ax.set_xlim(bins[0], bins[-1])
    ax.set_xlabel("centred cosine", color=MUTED)
    med = {p: float(np.median([q.cos_c for q in run.pairs if q.pool == p])) for p in lsd.POOLS}
    sd = run.background_std
    verdict(
        fig,
        f"in background-std units: ORTHO {(med['rand'] - med['ortho']) / sd:.1f} below RAND, NEAR {(med['near'] - med['rand']) / sd:.1f} above",
    )
    save(fig, out, "c3-pools.png")


def c4(run: lsd.Run, out: Path) -> None:
    cands = [c for c in run.candidates if c.novelty_nearest is not None]
    if not cands:
        print("c4 skipped: no novelty yet")
        return
    sd = run.background_std
    fig, top = figure(
        13,
        7.0,
        SECTION,
        "C4 · WHERE THE IDEAS LAND",
        "Each generated idea: centred cosine to its nearest existing note vs to its parents' midpoint, per pool",
        " · ".join(
            f"{p.upper()} nearest {np.median([c.novelty_nearest for c in cands if run.pairs[c.pair_index].pool == p]):.3f}"
            f" / midpoint {np.median([c.novelty_parents for c in cands if run.pairs[c.pair_index].pool == p]):.3f}"
            f" / cone {np.median([c.corpus_cos for c in cands if run.pairs[c.pair_index].pool == p]):.3f}"
            for p in lsd.POOLS
        )
        + f" · n = {len(cands)} · |mu| {run.mean_norm:.3f} · {sha()}",
    )
    axes = fig.subplots(
        1, 3, gridspec_kw={"top": top, "bottom": 0.11, "left": 0.05, "right": 0.99, "wspace": 0.14}
    )
    xs = np.array([c.novelty_parents for c in cands])
    ys = np.array([c.novelty_nearest for c in cands])
    lo, hi = float(min(xs.min(), ys.min())) - 0.03, float(max(xs.max(), ys.max())) + 0.03
    for ax, p in zip(axes, lsd.POOLS, strict=True):
        m = np.array([run.pairs[c.pair_index].pool == p for c in cands])
        kinds = np.array([c.kind for c in cands])
        ax.plot([lo, hi], [lo, hi], color=DIM, lw=1)
        ax.axvspan(-sd, sd, color=DIM, alpha=0.5, zorder=0)
        ax.scatter(
            xs[m & (kinds == "build")],
            ys[m & (kinds == "build")],
            s=26,
            color=POOL_COLOR[p],
            marker="o",
        )
        ax.scatter(
            xs[m & (kinds == "post")],
            ys[m & (kinds == "post")],
            s=26,
            color=POOL_COLOR[p],
            marker="^",
            alpha=0.7,
        )
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_aspect("equal")
        panel_title(ax, f"{p.upper()}: circles build, triangles post")
        style_axes(ax)
        ax.set_xlabel("cosine to parents' midpoint (centred)", color=MUTED)
        if ax is axes[0]:
            ax.set_ylabel("cosine to nearest other note (centred)", color=MUTED)
    above = float(np.mean(ys > xs))
    verdict(
        fig,
        f"{100 * above:.0f}% of ideas sit closer to some existing note than to their own parents' midpoint; the grey band is one background std",
    )
    save(fig, out, "c4-landing.png")


def c5(run: lsd.Run, out: Path) -> None:
    ratings = lsd.load_ratings(run.run_id)
    by_id = {c.id: c for c in run.candidates}
    pts = [
        (by_id[i].judge or 0.0, s)
        for i, s in ratings.items()
        if i in by_id and by_id[i].judge is not None
    ]
    if len(pts) < 10:
        print("c5 skipped: fewer than 10 ratings")
        return
    rng = np.random.default_rng(run.seed + 13)
    jx = np.array([p[0] for p in pts])
    oy = np.array([p[1] for p in pts])
    rho = lsd.spearman(list(jx), list(oy))
    null = np.array([lsd.spearman(list(jx), list(rng.permutation(oy))) for _ in range(2000)])
    p95 = float(np.percentile(null, 95))
    fig, top = figure(
        13,
        6.8,
        SECTION,
        "C5 · JUDGE VS OWNER",
        "Does the coherence judge's score track the owner's blind rating? Spearman against a permutation null",
        f"{len(pts)} rated cards · rho = {rho:.3f} · null p95 {p95:.3f} · p = {float(np.mean(null >= rho)):.3f} · bar {lsd.G2_MIN_RHO} · {sha()}",
    )
    axes = fig.subplots(
        1, 2, gridspec_kw={"top": top, "bottom": 0.12, "left": 0.06, "right": 0.98, "wspace": 0.18}
    )
    ax = axes[0]
    jit = rng.uniform(-0.15, 0.15, size=(len(pts), 2))
    ax.scatter(jx + jit[:, 0], oy + jit[:, 1], s=34, color=GOLD, alpha=0.8)
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.axhline(lsd.YES - 0.5, color=RED, ls="--", lw=1)
    panel_title(ax, "each card: judge score (x) against owner score (y); red = the yes line")
    style_axes(ax)
    ax.set_xlabel("judge 1-5", color=MUTED)
    ax.set_ylabel("owner 1-5", color=MUTED)
    ax = axes[1]
    hist(ax, null, DIM, np.linspace(-0.6, 0.8, 90), alpha=1.0)
    ax.axvline(rho, color=GOLD, lw=2)
    ax.axvline(lsd.G2_MIN_RHO, color=RED, ls="--", lw=1.2)
    panel_title(ax, "shuffled-rating null (grey), observed rho (gold), the bar (red)")
    style_axes(ax)
    ax.set_yticks([])
    ax.set_xlabel("Spearman rho", color=MUTED)
    verdict(
        fig,
        f"G2 {'PASS' if rho >= lsd.G2_MIN_RHO else 'FAIL'}: rho {rho:.2f} vs bar {lsd.G2_MIN_RHO}, null p95 {p95:.2f}",
    )
    save(fig, out, "c5-judge-vs-owner.png")


def c6(run: lsd.Run, out: Path) -> None:
    ratings = lsd.load_ratings(run.run_id)
    if not ratings:
        print("c6 skipped: no ratings")
        return
    res = lsd.gates(run, ratings, np.random.default_rng(run.seed + 13), permutations=200)
    by_id = {c.id: c for c in run.candidates}
    top_ids = {c.id for k in lsd.KINDS for p in lsd.POOLS for c in lsd.judge_top(run, k, p)}
    base = [s >= lsd.YES for i, s in ratings.items() if i in by_id and i not in top_ids]
    p_base = float(np.mean(base)) if base else 0.0
    ks = np.arange(6)
    from math import comb

    binom = np.array([comb(5, int(k)) * p_base**k * (1 - p_base) ** (5 - k) for k in ks])
    fig, top = figure(
        13,
        6.8,
        SECTION,
        "C6 · THE YIELD CLAIM",
        "Owner-yes among each pool's judge-top-5, per kind, over the binomial band of the non-top cards",
        " · ".join(
            f"{k} "
            + "/".join(
                f"{p[:1].upper()}{res['hits_top'][k][p]}of{res['rated_top'][k][p]}"
                for p in lsd.POOLS
            )
            for k in lsd.KINDS
        )
        + f" · non-top yes rate {p_base:.2f} · bar {lsd.G1_MIN_HITS} of 5 · {sha()}",
    )
    axes = fig.subplots(
        1, 2, gridspec_kw={"top": top, "bottom": 0.12, "left": 0.06, "right": 0.98, "wspace": 0.18}
    )
    for ax, kind in zip(axes, lsd.KINDS, strict=True):
        ax.barh(ks, binom / binom.max() * 0.9, color=DIM, height=0.8, left=-1.0)
        for n, p in enumerate(lsd.POOLS):
            ax.bar(n, res["hits_top"][kind][p], color=POOL_COLOR[p], width=0.7)
        ax.axhline(lsd.G1_MIN_HITS - 0.5, color=RED, ls="--", lw=1.2)
        ax.set_xticks([-0.55, 0, 1, 2])
        ax.set_xticklabels(["chance", "ORTHO", "NEAR", "RAND"], color=MUTED)
        ax.set_ylim(-0.5, 5.5)
        ax.set_yticks(ks)
        panel_title(
            ax,
            f"{kind}: yes among judge-top-5 (bars) vs 5-card binomial at the non-top rate (grey)",
        )
        style_axes(ax)
        ax.set_ylabel("cards scored >= 4", color=MUTED)
    verdict(
        fig,
        f"G1 {'PASS' if res['g1_pass'] else 'FAIL'}: "
        + (
            ", ".join(res["g1_kinds"])
            if res["g1_kinds"]
            else "ORTHO's top-5 never reaches 3 of 5 while beating NEAR"
        ),
    )
    save(fig, out, "c6-yield.png")


ARM_LABEL = {
    "A0": "A0 baseline",
    "A1": "A1 prompt",
    "A2": "A2 +4 samples",
    "A3": "A3 Sonnet",
    "A5": "A5 latents",
}
ARM_COLOR = {"A0": DIM, "A1": BLUE, "A2": GOLD, "A3": CYAN, "A5": PURPLE}


def c7(run: lsd.Run, X, Xc, out: Path) -> None:
    pilot_path = lsd.run_path(run.run_id).with_name(f"{run.run_id}-pilot.json")
    if not pilot_path.exists():
        print("c7 skipped: no pilot")
        return
    pilot = json.loads(pilot_path.read_text())
    arms = [a for a in ARM_LABEL if a in pilot["arms"]]
    S = Xc @ Xc.T
    np.fill_diagonal(S, -np.inf)
    nn_notes = S.max(axis=1)
    mu = X.mean(axis=0)
    cone_notes = X @ (mu / np.linalg.norm(mu))
    gates = [
        ("N1 spread: nearest other idea", "n1", lsd.N1_BAR, nn_notes, "notes: nearest neighbour"),
        (
            "N2 voice: cosine to the corpus mean",
            "n2",
            lsd.N2_BAR,
            cone_notes,
            "notes: own cone cosine",
        ),
        ("N3 distance: nearest note", "n3", lsd.N3_BAR, nn_notes, "notes: nearest neighbour"),
    ]
    passing = [
        a
        for a in arms
        if all(pilot["arms"][a][k] <= bar for _, k, bar, _, _ in gates)
        and pilot["arms"][a]["leak"] == 0
    ]
    fig, top = figure(
        13,
        7.6,
        SECTION,
        "C7 · THE NEWNESS GATES, FIVE ARMS",
        "Each arm's median on the three gates, drawn inside the notes' own distribution; the bar is red",
        " · ".join(
            f"{a} n1 {pilot['arms'][a]['n1']:.2f} n2 {pilot['arms'][a]['n2']:.2f} n3 {pilot['arms'][a]['n3']:.2f} leak {pilot['arms'][a]['leak']}"
            for a in arms
        )
        + f" · 30 shared pairs · {sha()}",
    )
    axes = fig.subplots(
        1,
        4,
        gridspec_kw={
            "top": top,
            "bottom": 0.12,
            "left": 0.05,
            "right": 0.99,
            "wspace": 0.22,
            "width_ratios": [1, 1, 1, 0.9],
        },
    )
    for ax, (title, key, bar, dist, dlabel) in zip(axes[:3], gates, strict=True):
        ax.hist(dist, bins=40, orientation="horizontal", color=DIM, alpha=1.0, density=True)
        ax.axhline(bar, color=RED, ls="--", lw=1.4)
        xs = np.linspace(0.15, 0.95, len(arms))
        xmax = ax.get_xlim()[1]
        for x, a in zip(xs, arms, strict=True):
            v = pilot["arms"][a][key]
            ax.scatter(
                [x * xmax],
                [v],
                s=150,
                color=ARM_COLOR[a],
                edgecolors=TEXT,
                linewidths=0.6,
                zorder=5,
            )
            ax.text(x * xmax, v + 0.02, a, color=TEXT, ha="center", fontsize=8.5)
            for pk in pilot["arms"][a]["per_kind"].values():
                ax.scatter([x * xmax], [pk[key]], s=18, color=ARM_COLOR[a], alpha=0.8, zorder=4)
        ax.set_ylim(min(0.0, float(dist.min())) - 0.02, max(0.85, float(np.percentile(dist, 99.5))))
        ax.set_xticks([])
        panel_title(ax, title)
        style_axes(ax)
        ax.set_xlabel(dlabel + " (grey)", color=MUTED)
        ax.text(xmax * 0.02, bar + 0.012, f"bar {bar}", color=RED, fontsize=8.5)
    ax = axes[3]
    ys = np.arange(len(arms))
    leak = [pilot["arms"][a]["leak"] / pilot["arms"][a]["n"] for a in arms]
    dash = [pilot["arms"][a]["em_dash_hooks"] for a in arms]
    ax.barh(ys - 0.18, leak, height=0.34, color=RED, alpha=0.85)
    ax.barh(ys + 0.18, dash, height=0.34, color=MUTED, alpha=0.85)
    for y, a, lk, dh in zip(ys, arms, leak, dash, strict=True):
        ax.text(
            0.02,
            y - 0.18,
            f"{ARM_LABEL[a]}  leak {100 * lk:.0f}%",
            color=TEXT,
            va="center",
            fontsize=8.5,
        )
        ax.text(
            0.02, y + 0.18, f"em-dash hooks {100 * dh:.0f}%", color=MUTED, va="center", fontsize=8.5
        )
    ax.set_yticks([])
    ax.set_xlim(0, 1)
    ax.set_ylim(len(arms) - 0.5, -0.6)
    panel_title(ax, "text: leakage (red), em-dash hooks (grey)")
    style_axes(ax)
    ax.set_xlabel("share of the arm's ideas", color=MUTED)
    verdict(
        fig, ("passes all gates: " + ", ".join(passing)) if passing else "no arm passes all gates"
    )
    save(fig, out, "c7-newness-arms.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=53)
    ap.add_argument("--run", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()
    out = Path(args.out)
    if args.run:
        run = lsd.load_run(args.run)
    else:
        run = lsd.new_run(args.seed, args.n)
        print("saved", lsd.save_run(run))
    notes, X = lsd.load_notes()
    if len(notes) != run.n_notes:
        # The store grows daily; figures use the run's own note set.
        ids = {n.id for n in run.notes}
        X = X[[k for k, n in enumerate(notes) if n.id in ids]]
        assert len(X) == run.n_notes, "a frozen note left the store"
    Xc, _ = lsd.centre(X)
    c0(run, X, Xc, out)
    c1(run, Xc, out)
    c2(run, Xc, out)
    c3(run, out)
    c4(run, out)
    c5(run, out)
    c6(run, out)
    c7(run, X, Xc, out)


if __name__ == "__main__":
    main()
