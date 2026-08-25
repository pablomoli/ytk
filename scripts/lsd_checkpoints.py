"""Section 53 checkpoints C0-C4 for `ytk lsd`, drawn from one frozen run.

    uv run --with matplotlib python scripts/lsd_checkpoints.py --seed 53 --out <dir> [--run RUN_ID]

Without --run a new run is sampled and saved under ~/.ytk/lsd/runs/. Each
figure is one claim; the math is in the section README, not here.
"""

from __future__ import annotations

import argparse
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
    assert len(notes) == run.n_notes, "store changed since the run was frozen"
    Xc, _ = lsd.centre(X)
    c0(run, X, Xc, out)
    c1(run, Xc, out)
    c2(run, Xc, out)
    c3(run, out)


if __name__ == "__main__":
    main()
