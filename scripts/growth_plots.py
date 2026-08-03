"""Figures for the freeze-vs-fresh growth experiments (17-corpus-growth).

Reads results.json produced by growth_experiments.py analyze. Pure plotting;
touches nothing else.

    uv run --with matplotlib python scripts/growth_experiments.py plot
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
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    RED,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "17-corpus-growth"
RESULTS = OUTDIR / "results.json"


def save(fig, name: str) -> None:
    frame_panels(fig)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def _footer(fig, y: float, text: str, width: int = 132) -> None:
    fig.text(MARGIN, y, textwrap.fill(text, width), color=MUTED, fontsize=9.5, linespacing=1.6)


def _curve(ax, curve: dict, color: str, label: str | None = None) -> None:
    ns = np.array(sorted(int(k) for k in curve))
    mean = np.array([curve[str(n)]["mean"] for n in ns])
    sd = np.array([curve[str(n)]["sd"] for n in ns])
    ax.fill_between(ns, mean - 2 * sd, mean + 2 * sd, color=color, alpha=0.18, linewidth=0)
    ax.plot(ns, mean, color=color, linewidth=2.0, label=label)
    ax.scatter(ns, mean, s=18, c=color, zorder=5, linewidths=0)


def fig01(r: dict) -> None:
    e1 = r["e1_plateau"]
    fz, fr = e1["freeze"], e1["fresh"]
    align = e1["mean_direction_alignment"]
    deg = float(np.degrees(np.arccos(np.clip(align, -1, 1))))

    fig, top = figure(
        16.5,
        6.6,
        1,
        "freeze vs fresh",
        "The cone does not move when the corpus grows",
        f"frozen snapshot n={fz['n']} vs live capture n={fr['n']}  ·  "
        f"{r['subsample_draws']} subsample draws per size, band = 2 sd  ·  seed {r['seed']}",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1.5, 1], left=0.055, right=1 - MARGIN - 0.015, top=top, bottom=0.21
    )

    ax = fig.add_subplot(gs[0])
    _curve(ax, e1["mean_norm_vs_n"], GOLD)
    ns = np.array(sorted(int(k) for k in e1["mean_norm_vs_n"]))
    ax.plot(ns, 1 / np.sqrt(ns), color=RED, linewidth=1.2, linestyle="--")
    ax.text(ns[1], 1 / np.sqrt(ns[1]) + 0.012, "isotropic 1/sqrt(n)", color=RED, fontsize=TICK_SIZE)
    ax.axhline(fz["mean_norm"], color=CYAN, linewidth=1.0, linestyle=":")
    ax.text(
        ns[-2],
        fz["mean_norm"] - 0.03,
        f"freeze {fz['mean_norm']:.3f}",
        color=CYAN,
        fontsize=TICK_SIZE,
    )
    style_axes(ax)
    ax.set_xlabel("notes sampled from the fresh corpus")
    ax.set_ylabel("length of the mean vector")
    ax.set_ylim(0, 0.60)
    panel_title(ax, "the shared offset is flat in n", width=44)

    ax = fig.add_subplot(gs[1])
    rows = [
        ("length of mean", fz["mean_norm"], fr["mean_norm"]),
        ("mean pairwise cos", fz["mean_pairwise_cos"], fr["mean_pairwise_cos"]),
        ("isotropic reference", fz["mean_norm_isotropic"], fr["mean_norm_isotropic"]),
    ]
    y = np.arange(len(rows))[::-1]
    ax.barh(y + 0.18, [v for _, v, _ in rows], height=0.32, color=CYAN, alpha=0.85)
    ax.barh(y - 0.18, [v for _, _, v in rows], height=0.32, color=GOLD, alpha=0.85)
    for yi, (lab, a, b) in zip(y, rows):
        ax.text(a + 0.008, yi + 0.18, f"freeze {a:.4f}", color=CYAN, fontsize=8.2, va="center")
        ax.text(b + 0.008, yi - 0.18, f"fresh  {b:.4f}", color=GOLD, fontsize=8.2, va="center")
    ax.set_yticks(y, [lab for lab, _, _ in rows])
    style_axes(ax)
    ax.set_xlim(0, 0.60)
    panel_title(ax, f"axis direction moved {deg:.1f} deg", width=40)

    _footer(
        fig,
        0.05,
        f"Adding {fr['n'] - fz['n']} notes left every cone statistic in place: the mean's length "
        f"changed by {abs(fr['mean_norm'] - fz['mean_norm']):.4f} and its direction rotated "
        f"{deg:.1f} degrees (cosine {align:.5f}). The plateau visible from n=256 onward says the "
        "offset is a property of the encoder and the content mix, not of how much of it there is — "
        "the falsification attempt failed, which is what the interpolation machinery needed.",
    )
    save(fig, "01-plateau.png")


def fig02(r: dict) -> None:
    e2 = r["e2_participation"]
    fig, top = figure(
        16.5,
        6.6,
        2,
        "freeze vs fresh",
        "Effective dimensionality is still buying new axes with every note",
        f"participation ratio of the centred cloud  ·  freeze {e2['freeze']:.1f} at n=493, "
        f"fresh {e2['fresh']:.1f} at n=568  ·  band = 2 sd over {r['subsample_draws']} draws",
    )
    gs = fig.add_gridspec(1, 1, left=0.055, right=1 - MARGIN - 0.015, top=top, bottom=0.24)
    ax = fig.add_subplot(gs[0])
    _curve(ax, e2["pr_vs_n"], GOLD)
    ns = np.array(sorted(int(k) for k in e2["pr_vs_n"]))
    ax.plot(ns, ns - 1, color=RED, linewidth=1.2, linestyle="--")
    ax.text(ns[0] + 6, ns[0] + 8, "hard cap n-1", color=RED, fontsize=TICK_SIZE, rotation=30)
    ax.scatter([493], [e2["freeze"]], s=52, c=CYAN, zorder=6, linewidths=0)
    ax.annotate(
        f"frozen snapshot  {e2['freeze']:.1f}",
        (493, e2["freeze"]),
        textcoords="offset points",
        xytext=(-120, 14),
        color=CYAN,
        fontsize=TICK_SIZE,
    )
    means = [e2["pr_vs_n"][str(n)]["mean"] for n in ns]
    for k in range(1, len(ns)):
        rate = (means[k] - means[k - 1]) / (ns[k] - ns[k - 1])
        ax.annotate(
            f"+{rate:.2f}/note",
            ((ns[k] + ns[k - 1]) / 2, (means[k] + means[k - 1]) / 2),
            textcoords="offset points",
            xytext=(6, -16),
            color=MUTED,
            fontsize=8.2,
        )
    style_axes(ax)
    ax.set_xlabel("notes sampled")
    ax.set_ylabel("participation ratio")
    ax.set_ylim(0, 130)
    panel_title(ax, "rising, decelerating, nowhere near a ceiling it owns", width=64)

    _footer(
        fig,
        0.05,
        "The freeze's 104 was never an encoder property: 75 more notes bought 2.3 more effective "
        "dimensions, and the curve is decelerating but not flat — every doubling still adds axes. "
        "The n-1 cap that bound the earlier measurement is far above the curve now; whatever "
        "ceiling the encoder has, this corpus has not found it yet.",
    )
    save(fig, "02-pr-growth.png")


def fig03(r: dict) -> None:
    e3 = r["e3_tag_z"]
    shared = e3["shared_tags"]
    zf = np.array([e3["freeze"][t]["z"] for t in shared])
    zg = np.array([e3["fresh"][t]["z"] for t in shared])
    corr = float(np.corrcoef(zf, zg)[0, 1])

    fig, top = figure(
        16.5,
        7.4,
        3,
        "freeze vs fresh",
        "Tag coherence replicates on fresh vectors with fresh nulls",
        f"{len(shared)} shared tags, z against size-matched nulls ({r['null_draws']} draws) "
        f"recomputed independently per snapshot  ·  r = {corr:.3f}  ·  "
        f"mean |dz| = {float(np.mean(np.abs(zg - zf))):.2f}",
    )
    gs = fig.add_gridspec(1, 1, left=0.30, right=0.70, top=top, bottom=0.20)
    ax = fig.add_subplot(gs[0])
    lim = float(max(zf.max(), zg.max())) * 1.08
    ax.plot([0, lim], [0, lim], color=MUTED, linewidth=1.0, linestyle="--", alpha=0.6)
    ax.axhline(2, color=RED, linewidth=1.0, linestyle=":", alpha=0.8)
    ax.axvline(2, color=RED, linewidth=1.0, linestyle=":", alpha=0.8)
    ax.text(lim * 0.86, 2.4, "z = 2", color=RED, fontsize=TICK_SIZE)
    ax.scatter(zf, zg, s=22, c=GOLD, alpha=0.85, linewidths=0)
    for tag in set(e3["flips_below_2"] + e3["flips_above_2"] + ["creative-coding", "ai"]):
        if tag not in shared:
            continue
        i = shared.index(tag)
        ax.scatter([zf[i]], [zg[i]], s=34, c=RED, zorder=6, linewidths=0)
        ax.annotate(
            tag,
            (zf[i], zg[i]),
            textcoords="offset points",
            xytext=(7, 4),
            color=RED,
            fontsize=8.6,
        )
    ax.set_aspect("equal")
    style_axes(ax)
    ax.set_xlabel("z on the frozen snapshot")
    ax.set_ylabel("z on the fresh corpus")
    panel_title(ax, "everything hugs the diagonal", width=44)

    _footer(
        fig,
        0.05,
        f"Only two tags crossed the z=2 line, in opposite directions — {', '.join(e3['flips_below_2'])} "
        f"(2.57 to 1.96, 12 notes) down, {', '.join(e3['flips_above_2'])} (1.94 to 2.37) up — both "
        "hovering at the threshold already; that is boundary jitter, not structure change. The "
        "largest absolute mover is creative-coding (z 11.97 to 9.74 while gaining 22 notes), still "
        "unambiguously coherent; ai strengthened most (12.32 to 15.11). Two tags reached the "
        f"6-note scoring floor for the first time: {', '.join(e3['gained'])}.",
    )
    save(fig, "03-tag-stability.png")


def fig04(r: dict) -> None:
    e4 = r["e4_path_support"]
    fig, top = figure(
        16.5,
        6.8,
        4,
        "freeze vs fresh",
        "The corpus grew 15% and the interpolation paths kept the same neighbours",
        "slerp arcs between the fig-05 pairs, support = cosine of the nearest real note at each "
        "step (endpoints excluded)  ·  dashed = frozen snapshot, solid = fresh corpus",
    )
    gs = fig.add_gridspec(
        1, 2, left=0.055, right=1 - MARGIN - 0.015, top=top, bottom=0.22, wspace=0.16
    )
    ts = np.linspace(0, 1, len(e4["freeze"]["related"]["support"]))
    for k, (pair, color) in enumerate([("related", GOLD), ("unrelated", BLUE)]):
        ax = fig.add_subplot(gs[k])
        for w, style in (("freeze", "--"), ("fresh", "-")):
            d = e4[w][pair]
            ax.plot(ts, d["support"], color=color, linewidth=1.9, linestyle=style, label=w)
            ax.axhline(e4[w]["background_cos"], color=RED, linewidth=0.9, linestyle=":", alpha=0.7)
        ax.text(
            0.02,
            e4["fresh"]["background_cos"] + 0.008,
            "corpus background",
            color=RED,
            fontsize=TICK_SIZE,
        )
        mn_f, mn_g = e4["freeze"][pair]["min"], e4["fresh"][pair]["min"]
        style_axes(ax)
        ax.set_ylim(0.2, 0.8)
        ax.set_xlabel("position along the walk")
        if k == 0:
            ax.set_ylabel("similarity of the nearest real note")
        leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="upper center")
        for t in leg.get_texts():
            t.set_color(MUTED)
        panel_title(ax, f"{pair} pair: min support {mn_f:.3f} to {mn_g:.3f}", width=44)

    _footer(
        fig,
        0.05,
        "The 75 new notes changed neither arc: minimum support moved 0.008 on the related path and "
        "not at all on the unrelated one. Density gains spread across the whole cone rather than "
        "landing near these particular walks — decode-by-retrieval works exactly as well as before, "
        "and no better. Support was already above 0.50 everywhere, so the machinery loses nothing; "
        "but growth at this rate is not what will improve it.",
    )
    save(fig, "04-path-support.png")


def fig05(c: dict) -> None:
    bg = c["background_cos"]
    fig, top = figure(
        16.5,
        6.8,
        5,
        "path census",
        "Every road in the corpus runs through inhabited country",
        f"minimum support along the slerp arc, {c['paths']['nn']['n_paths']} nearest-neighbor "
        f"pairs + {c['paths']['random']['n_paths']} random pairs, {c['steps_interior']} interior "
        f"stops each  ·  seed {c['seed']}",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1.25, 1], left=0.055, right=1 - MARGIN - 0.015, top=top, bottom=0.22
    )

    ax = fig.add_subplot(gs[0])
    bins = np.linspace(0.2, 0.8, 49)
    for label, color in (("nn", GOLD), ("random", BLUE)):
        m = np.array(c["paths"][label]["min_support"])
        ax.hist(
            m, bins=bins, density=True, histtype="stepfilled", alpha=0.35, color=color, label=label
        )
        ax.hist(m, bins=bins, density=True, histtype="step", linewidth=1.6, color=color)
    ax.axvline(bg, color=RED, linewidth=1.2, linestyle="--")
    ax.text(bg + 0.006, ax.get_ylim()[1] * 0.9, "corpus background", color=RED, fontsize=TICK_SIZE)
    style_axes(ax)
    ax.set_xlabel("minimum support along the path")
    ax.set_ylabel("density")
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE)
    for t in leg.get_texts():
        t.set_color(MUTED)
    panel_title(ax, "no path, chosen or random, ever drops to background", width=52)

    ax = fig.add_subplot(gs[1])
    for label, color in (("nn", GOLD), ("random", BLUE)):
        ax.scatter(
            c["paths"][label]["angle_deg"],
            c["paths"][label]["min_support"],
            s=8,
            c=color,
            alpha=0.5,
            linewidths=0,
            label=label,
        )
    ax.axhline(bg, color=RED, linewidth=1.0, linestyle="--", alpha=0.8)
    style_axes(ax)
    ax.set_xlabel("angle between endpoints (deg)")
    ax.set_ylabel("minimum support")
    panel_title(ax, "longer roads sag, none break", width=40)

    _footer(
        fig,
        0.05,
        "The census settles what two hand-picked paths could not: 0 of "
        f"{c['paths']['nn']['n_paths'] + c['paths']['random']['n_paths']} walks dip below the "
        "corpus background anywhere along their length. Random pairs are barely worse than "
        "nearest-neighbor pairs — the cone keeps everything close enough that even the longest "
        "roads stay decodable. There is no desert between the cities; the space is a single "
        "connected settlement whose density varies.",
    )
    save(fig, "05-path-census.png")


def fig06(c: dict) -> None:
    counts = np.array(c["hubs"]["counts"], dtype=float)
    total = counts.sum()
    share = np.cumsum(counts) / total
    ranks = np.arange(1, len(counts) + 1)
    top = c["hubs"]["top"]

    fig, ftop = figure(
        16.5,
        6.6,
        6,
        "path census",
        "Some towns sit on many roads — hubness is real but not pathological",
        f"{c['hubs']['distinct_answerers']} of {c['hubs']['corpus_n']} notes answer at least one "
        "path stop  ·  a note counts once per path it serves, not once per stop",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.2, 1],
        left=0.055,
        right=1 - MARGIN - 0.015,
        top=ftop,
        bottom=0.22,
        wspace=0.55,
    )

    ax = fig.add_subplot(gs[0])
    ax.plot(ranks, share, color=GOLD, linewidth=2.0)
    for k in (10, 50):
        ax.scatter([k], [share[k - 1]], s=34, c=CYAN, zorder=5, linewidths=0)
        ax.annotate(
            f"top {k}: {share[k - 1]:.0%} of answers",
            (k, share[k - 1]),
            textcoords="offset points",
            xytext=(10, -4),
            color=CYAN,
            fontsize=TICK_SIZE,
        )
    ax.plot(ranks, ranks / len(counts), color=RED, linewidth=1.1, linestyle="--")
    ax.text(len(counts) * 0.55, 0.42, "uniform share", color=RED, fontsize=TICK_SIZE, rotation=24)
    ax.set_xscale("log")
    style_axes(ax)
    ax.set_xlabel("notes ranked by paths served (log)")
    ax.set_ylabel("cumulative share of path answers")
    ax.set_ylim(0, 1.02)
    panel_title(ax, "concentration curve of who answers the stops", width=48)

    ax = fig.add_subplot(gs[1])
    names = [t["name"][:38] for t in top[:10]][::-1]
    served = [t["paths_served"] for t in top[:10]][::-1]
    ax.barh(np.arange(len(names)), served, height=0.62, color=GOLD, alpha=0.9)
    ax.set_yticks(np.arange(len(names)), names, fontsize=7.6)
    style_axes(ax)
    ax.set_xlabel("paths served")
    panel_title(ax, "the ten busiest towns", width=40)

    _footer(
        fig,
        0.05,
        "The top note serves 5.5% of all paths and the top ten together 12% of answers — visible "
        "concentration, far from the winner-take-all hubness that breaks cross-lingual retrieval "
        "(arXiv 2605.26575 finds hub mass, not anisotropy, is what damages reciprocity there). "
        "For the path interface this is a design input: stops should be deduplicated per walk and "
        "hub notes down-weighted, or every road will pass through the same three junctions.",
    )
    save(fig, "06-hubness.png")


def main() -> None:
    r = json.loads(RESULTS.read_text())
    fig01(r)
    fig02(r)
    fig03(r)
    fig04(r)
    census_path = OUTDIR / "census.json"
    if census_path.exists():
        c = json.loads(census_path.read_text())
        fig05(c)
        fig06(c)


if __name__ == "__main__":
    main()
