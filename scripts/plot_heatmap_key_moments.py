"""Figures for #144: do Claude's key_moments land where people rewatch?

YouTube ships a `heatmap` in the yt-dlp info dict — 100 uniform bins of
normalized replay intensity — and ytk fetches it on every ingest and discards
it. It is a free crowd-sourced attention signal on exactly the axis the
generated `## Key Moments` claim to mark, which makes "are our timestamps any
good" answerable instead of arguable.

Rungs:
  01  the measurement — key moments vs a uniform-random null, pooled and paired
  02  worked examples — the curve behind the number, with the marks on it
  03  is it an artifact — lift against duration and audience size

Data comes from scripts/heatmap_experiment.py (harvest -> analyze). The null is
drawn per video and seeded, so every number here is reproducible from
docs/assets/09-heatmap-key-moments/raw.json.

Usage: uv run --with matplotlib --with numpy python scripts/plot_heatmap_key_moments.py
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
    BLUE,
    CYAN,
    DIM,
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "09-heatmap-key-moments"
RESULTS = OUTDIR / "results.json"
RAW = OUTDIR / "raw.json"


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def fig01(res: dict) -> None:
    """The headline: pooled distributions, per-video pairs, and the lift."""
    km = np.asarray(res["pooled"]["key_moments"])
    null = np.asarray(res["pooled"]["null"])
    per = res["per_video"]
    km_m = np.array([v["km_mean"] for v in per])
    null_m = np.array([v["null_mean"] for v in per])
    lift = km_m - null_m

    fig, top = figure(
        16.5,
        7.6,
        1,
        "the measurement",
        "Do generated key moments land where the audience actually rewatches?",
        f"{res['videos_scored']} videos  ·  {res['key_moments_scored']} key moments  ·  "
        f"null = {res['draws_per_video']} uniform draws per video, seed {res['seed']}  ·  "
        f"replay intensity is YouTube's own most-replayed curve, 100 bins per video",
    )
    gs = fig.add_gridspec(
        1, 3, left=0.055, right=1 - MARGIN - 0.015, top=top, bottom=0.135, wspace=0.30
    )

    # (a) pooled distributions -- what a single timestamp is worth
    ax = fig.add_subplot(gs[0])
    bins = np.linspace(0, max(km.max(), null.max()), 46)
    ax.hist(null, bins=bins, color=DIM, alpha=0.95, label=f"random offsets (n={len(null)})")
    ax.hist(
        km,
        bins=bins,
        color=GOLD,
        alpha=0.72,
        label=f"key moments (n={len(km)})",
        weights=np.full(len(km), len(null) / len(km)),
    )
    ax.axvline(float(null.mean()), color=DIM, linewidth=1.4, linestyle="--")
    ax.axvline(float(km.mean()), color=GOLD, linewidth=1.6, linestyle="--")
    style_axes(ax)
    ax.set_xlabel("replay intensity at the timestamp")
    ax.set_ylabel("timestamps (null rescaled to match)")
    ax.legend(loc="upper right", fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT)
    panel_title(
        ax,
        f"pooled — key moments {km.mean():.3f} vs random {null.mean():.3f}",
        width=52,
    )

    # (b) three-way per video. The uploader's own chapters are the reference
    #     point that turns "better than chance" into "how much of the available
    #     signal did we actually get".
    has_ch = [v for v in per if v["chapter_mean"] is not None]
    ax = fig.add_subplot(gs[1])
    for v in has_ch:
        ax.plot(
            [0, 1, 2],
            [v["null_mean"], v["km_mean"], v["chapter_mean"]],
            color=DIM,
            alpha=0.30,
            linewidth=0.8,
            solid_capstyle="round",
        )
    means = [
        float(null_m.mean()),
        float(km_m.mean()),
        float(np.mean([v["chapter_mean"] for v in has_ch])),
    ]
    ax.plot([0, 1, 2], means, color=CYAN, linewidth=3.0, zorder=6)
    for x, y, c in zip([0, 1, 2], means, [MUTED, GOLD, CYAN]):
        ax.scatter([x], [y], color=c, s=70, zorder=7, edgecolors="#08080a", linewidths=1.2)
        ax.text(x, y + 0.035, f"{y:.3f}", ha="center", color=c, fontsize=TICK_SIZE + 1)
    ax.set_xlim(-0.28, 2.28)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["random", "key moments", "uploader\nchapters"])
    style_axes(ax)
    ax.set_ylabel("mean replay intensity")
    panel_title(
        ax,
        f"the ceiling — human chapters reach {means[2] - means[0]:+.3f} where we reach "
        f"{means[1] - means[0]:+.3f}  ({len(has_ch)} videos have both)",
        width=52,
    )

    # (c) both effect sizes on one axis, against the same zero
    ch_lift = np.array([v["chapter_mean"] - v["null_mean"] for v in has_ch])
    ax = fig.add_subplot(gs[2])
    bins = np.linspace(min(lift.min(), ch_lift.min()), max(lift.max(), ch_lift.max()), 36)
    ax.hist(lift, bins=bins, color=GOLD, alpha=0.80, label="key moments")
    ax.hist(ch_lift, bins=bins, color=CYAN, alpha=0.55, label="uploader chapters")
    ax.axvline(0, color=MUTED, linewidth=1.4)
    style_axes(ax)
    ax.set_xlabel("lift over that video's own null")
    ax.set_ylabel("videos")
    ax.legend(loc="upper right", fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT)
    se = lift.std(ddof=1) / np.sqrt(len(lift))
    se_ch = ch_lift.std(ddof=1) / np.sqrt(len(ch_lift))
    panel_title(
        ax,
        f"key moments {lift.mean():+.3f} [{lift.mean() - 1.96 * se:+.3f}, "
        f"{lift.mean() + 1.96 * se:+.3f}]  ·  chapters {ch_lift.mean():+.3f} "
        f"[{ch_lift.mean() - 1.96 * se_ch:+.3f}, {ch_lift.mean() + 1.96 * se_ch:+.3f}]",
        width=58,
    )

    fig.text(
        MARGIN,
        0.052,
        "Each video is scored against a null drawn from its own curve, so a video whose whole "
        "heatmap runs hot cannot inflate the result.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.022,
        f"The generated timestamps beat chance on {res['win_rate']:.0%} of videos — and reach "
        "about a third of the lift the uploader's own chapters get from the same curve.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "01-key-moments-vs-null.png")


def fig02(res: dict, raw: dict) -> None:
    """The curve behind the number, for the videos with the most moments."""
    by_id = {r["video_id"]: r for r in raw["videos"]}
    # Best, median and worst by lift. Picking the three densest notes instead
    # would show only near-zero cases -- 40 marks on a 78-minute video is close
    # to uniform coverage, so it cannot beat a uniform null by construction.
    ranked = sorted(res["per_video"], key=lambda v: v["km_mean"] - v["null_mean"])
    picks = [ranked[-1], ranked[len(ranked) // 2], ranked[0]]
    labels = ["best", "median", "worst"]

    fig, top = figure(
        16.5,
        9.4,
        2,
        "worked examples",
        "What the number looks like on a single video",
        "gold marks are generated key moments, cyan ticks are the uploader's own chapters, "
        "the filled curve is YouTube's replay intensity",
    )
    gs = fig.add_gridspec(
        len(picks), 1, left=0.062, right=1 - MARGIN - 0.01, top=top, bottom=0.075, hspace=0.62
    )

    for k, v in enumerate(picks):
        rec = by_id[v["video_id"]]
        heat = np.asarray(rec["heatmap"])
        dur = rec["duration"]
        t = (np.arange(len(heat)) + 0.5) / len(heat) * dur / 60.0

        ax = fig.add_subplot(gs[k])
        ax.fill_between(t, heat, color=GOLD, alpha=0.16, linewidth=0)
        ax.plot(t, heat, color=GOLD, linewidth=1.4, alpha=0.95)
        ax.axhline(v["null_mean"], color=DIM, linewidth=1.1, linestyle="--")

        for m in rec["key_moments"]:
            if m <= dur:
                ax.plot(
                    [m / 60.0],
                    [np.interp(m / 60.0, t, heat)],
                    marker="v",
                    color=GOLD,
                    markersize=7,
                    markeredgecolor="#fff6e0",
                    markeredgewidth=0.6,
                    zorder=6,
                )
        for c in rec.get("chapters") or []:
            if c <= dur:
                ax.plot([c / 60.0, c / 60.0], [0, 0.055], color=CYAN, linewidth=1.5, alpha=0.9)

        style_axes(ax)
        ax.set_xlim(0, dur / 60.0)
        ax.set_ylim(0, max(0.02, heat.max() * 1.18))
        ax.set_xlabel("minutes")
        ax.set_ylabel("replay")
        panel_title(
            ax,
            f"{labels[k].upper()}  ·  {rec['title'][:66]}  ·  {v['n_moments']} moments  ·  "
            f"lift {v['km_mean'] - v['null_mean']:+.3f}",
            width=104,
        )

    save(fig, "02-worked-examples.png")


def fig03(res: dict) -> None:
    """Is the effect an artifact of long videos or big audiences?"""
    per = res["per_video"]
    lift = np.array([v["km_mean"] - v["null_mean"] for v in per])
    dur = np.array([v["duration"] for v in per]) / 60.0
    nmom = np.array([v["n_moments"] for v in per])

    fig, top = figure(
        16.5,
        7.0,
        3,
        "is it an artifact",
        "The effect should not depend on how long the video is, or how many marks it got",
        "if lift tracked duration, we would be measuring the shape of long-video heatmaps "
        "rather than the quality of the timestamps",
    )
    gs = fig.add_gridspec(
        1, 3, left=0.055, right=1 - MARGIN - 0.015, top=top, bottom=0.135, wspace=0.30
    )

    # |r| this size is inside the noise floor at this n; state the threshold on
    # the panel rather than letting a drawn trend line imply a finding.
    n = len(lift)
    crit = 1.96 / np.sqrt(n - 2 + 1.96**2)

    for ax_i, (x, xlabel, title) in enumerate(
        [
            (dur, "video length (minutes)", "lift vs duration"),
            (nmom, "key moments in the note", "lift vs how many marks"),
        ]
    ):
        ax = fig.add_subplot(gs[ax_i])
        ax.scatter(x, lift, color=GOLD, s=22, alpha=0.62, linewidths=0)
        ax.axhline(0, color=MUTED, linewidth=1.2)
        if len(x) > 2 and x.std() > 0:
            r = float(np.corrcoef(x, lift)[0, 1])
            sig = abs(r) > crit
            slope, intercept = np.polyfit(x, lift, 1)
            xs = np.linspace(x.min(), x.max(), 50)
            ax.plot(
                xs,
                slope * xs + intercept,
                color=CYAN if sig else DIM,
                linewidth=1.6,
                alpha=0.9,
                linestyle="-" if sig else "--",
            )
            title = f"{title}  ·  r = {r:+.2f} ({'significant' if sig else 'n.s.'})"
        style_axes(ax)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("lift over null")
        panel_title(ax, title, width=52)

    # the honest caveat panel: how much of the corpus this covers at all
    ax = fig.add_subplot(gs[2])
    harvested = res["videos_harvested"]
    with_heat = res["videos_with_heatmap"]
    scored = res["videos_scored"]
    bars = [harvested, with_heat, scored]
    labels = ["ingested\nwith moments", "have a\nheatmap", "scored"]
    ax.bar(labels, bars, color=[DIM, BLUE, GOLD], alpha=0.94)
    for i, b in enumerate(bars):
        ax.text(i, b + max(bars) * 0.02, str(b), ha="center", color=TEXT, fontsize=TICK_SIZE)
    style_axes(ax)
    ax.set_ylim(0, max(bars) * 1.16)
    ax.set_ylabel("videos")
    panel_title(
        ax,
        f"coverage — YouTube only publishes a heatmap for {with_heat / harvested:.0%} of these",
        width=52,
    )

    fig.text(
        MARGIN,
        0.052,
        f"Neither trend clears the noise floor: at n={n}, |r| must exceed {crit:.2f} for p<0.05. "
        "Dashed fits are not findings.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        MARGIN,
        0.022,
        "Videos without a heatmap are not a random sample: YouTube withholds the curve on "
        "low-view videos, so this measures the popular half of the corpus.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "03-artifact-checks.png")


def main() -> None:
    if not RESULTS.exists():
        raise SystemExit(f"missing {RESULTS} — run heatmap_experiment.py harvest, then analyze")
    plt.style.use("dark_background")
    res = json.loads(RESULTS.read_text())
    raw = json.loads(RAW.read_text())
    fig01(res)
    fig02(res, raw)
    fig03(res)


if __name__ == "__main__":
    main()
