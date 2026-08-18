"""Section 45 — atlas rung 4 (#183): segment strips.

Figure 01: the two gates that license the strips — aggregation validity
(segment-mean codes point at their own document) and temporal structure
(latent series autocorrelate above the order-shuffle null). Figure 02: the
protagonist's strip, real order over one shuffle draw of the same values.

Data: experiments/sae_qwen/strips.{json,npz} (segment_strips.py). Read-only.

    uv run --with matplotlib python scripts/plot_segment_strips.py
"""

from __future__ import annotations

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
    CYAN,
    DIM,
    DPI,
    GOLD,
    MUTED,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
    style_axes,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "experiments" / "sae_qwen"
OUTDIR = REPO / "docs" / "assets" / "45-segment-strips"

SHA = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
).stdout.strip()


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def fig01(meta: dict, z) -> None:
    ga, gt = meta["gate_aggregation"], meta["gate_temporal"]
    fig, top = figure(
        16.5,
        6.8,
        1,
        "atlas rung 4 — the license",
        "Before any strip renders: do segments add up, and does order matter?",
        f"{meta['n_videos']} videos with a doc code and >= 8 ordered segments | left: cosine of "
        f"segment-mean code vs own document code, null = another video's segments | right: mean "
        f"lag-1 autocorr of the top-8 latent series, null = 100 order-shuffles | {SHA}",
    )
    gs = fig.add_gridspec(1, 2, left=0.055, right=0.975, top=top, bottom=0.115, wspace=0.16)

    ax = fig.add_subplot(gs[0, 0])
    bins = np.linspace(-0.1, 1.0, 45)
    ax.hist(z["mismatched"], bins=bins, density=True, color=DIM, label="mismatched video (null)")
    ax.hist(
        z["matched"],
        bins=bins,
        density=True,
        histtype="step",
        linewidth=2.0,
        color=GOLD,
        label="own video",
    )
    leg = ax.legend(frameon=False, fontsize=8.5)
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("cosine(mean segment code, document code)")
    ax.set_ylabel("density")
    panel_title(
        ax,
        f"aggregation: median {ga['matched_median']:.2f} vs null {ga['mismatched_median']:.2f} "
        f"({ga['matched_below_mismatched_max']}/{meta['n_videos']} inside null reach)",
        width=54,
    )

    ax = fig.add_subplot(gs[0, 1])
    bins = np.linspace(-0.3, 0.9, 45)
    ax.hist(z["null_ac"], bins=bins, density=True, color=DIM, label="order shuffled (null)")
    ax.hist(
        z["obs_ac"],
        bins=bins,
        density=True,
        histtype="step",
        linewidth=2.0,
        color=GOLD,
        label="real order",
    )
    pa = meta["protagonist"]["autocorr"]
    ax.axvline(pa, color=CYAN, linewidth=1.6)
    ax.text(pa + 0.01, ax.get_ylim()[1] * 0.9, f"protagonist {pa:.2f}", color=CYAN, fontsize=8.5)
    leg = ax.legend(frameon=False, fontsize=8.5)
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("mean lag-1 autocorrelation, top-8 latents")
    panel_title(
        ax,
        f"temporal: {gt['videos_above_own_null']}/{gt['n']} videos above their own shuffle null",
        width=54,
    )
    verdict(
        fig,
        "both gates pass — segments add up (0.67 vs 0.02) and order is signal (0.28 vs -0.04)",
    )
    save(fig, "01-the-license.png")


def fig02(meta: dict, z) -> None:
    S = z["prot_strip"]  # n_seg x 8, real order
    tops = list(meta["protagonist"]["top_latents"])
    rng = np.random.default_rng(45)
    S_sh = S[rng.permutation(len(S))]
    pa, pn = meta["protagonist"]["autocorr"], meta["protagonist"]["autocorr_shuffle_null"]

    fig, top = figure(
        16.5,
        7.6,
        2,
        "atlas rung 4 — protagonist strip",
        "The AlexNet video as a timeline of concepts",
        f"{meta['protagonist']['n_segments']} transcript segments encoded live (the video "
        f"postdates the acts cache) | rows = its top-8 latents by mean mass | top: real order, "
        f"lag-1 autocorr {pa:.2f} | bottom: the same values, order shuffled once ({pn:.2f} over "
        f"100 shuffles) | {SHA}",
    )
    gs = fig.add_gridspec(2, 1, left=0.30, right=0.975, top=top, bottom=0.14, hspace=0.32)
    vmax = float(S.max())
    for k, (M, tag, tcol) in enumerate(
        (
            (S, "real order — concepts run in stretches", GOLD),
            (S_sh, "shuffled order — the null: same values, no stretches", MUTED),
        )
    ):
        ax = fig.add_subplot(gs[k, 0])
        ax.imshow(
            punch(M.T / vmax),
            cmap=saturated_magma(),
            vmin=0,
            vmax=1,
            aspect="auto",
            interpolation="nearest",
        )
        ax.set_yticks(range(len(tops)))
        labels = [f"#{t['latent']}  {(t['name'] or '')[:34]}" for t in tops]
        ax.set_yticklabels(labels, fontsize=7.2)
        for tick in ax.get_yticklabels():
            tick.set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=7)
        for s_ in ax.spines.values():
            s_.set_color(DIM if k else GOLD)
        if k:
            ax.set_xlabel("segment index (timeline)")
        panel_title(ax, tag, width=70)
    verdict(fig, "a strip is a reading order — shuffling keeps the ink and loses the story")
    save(fig, "02-protagonist-strip.png")


def main() -> None:
    meta = json.loads((SAE / "strips.json").read_text())
    z = np.load(SAE / "data" / "strips.npz")
    fig01(meta, z)
    fig02(meta, z)
    (OUTDIR / "strips.json").write_text(json.dumps(meta, indent=1))
    print("copied strips.json sidecar")


if __name__ == "__main__":
    main()
