"""Section 42 — atlas rung 0 (#183): the inventory figures.

Two figures, one claim each. Figure 01: how far the atlas's existing inputs
reach over today's corpus. Figure 02: the protagonist latent, chosen by
measurement, with the cone check that legitimizes "loudest".

Data: experiments/sae_qwen/rung0.json (rung0_inventory.py), the s0 acts cache,
features.json. Read-only; renders into docs/assets/42-atlas-inventory/.

    uv run --with matplotlib python scripts/plot_atlas_rung0.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
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
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "experiments" / "sae_qwen"
OUTDIR = REPO / "docs" / "assets" / "42-atlas-inventory"

SHA = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
).stdout.strip()


def save(fig, name: str) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    frame_panels(fig)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    import matplotlib.pyplot as plt

    plt.close(fig)


def fig01(r: dict) -> None:
    ood = r["ood"]
    mt = r["map_thumbnails"]
    seg = r["segment_coverage"]
    fig, top = figure(
        13.4,
        7.2,
        1,
        "atlas rung 0 — coverage",
        "The atlas's inputs, measured against today's corpus",
        f"live store {ood['overall']['live']:,} vectors vs Aug-8 training cache | "
        f"segments with store coverage {seg['with_segments']}/{seg['video_notes']} notes "
        f"({seg['coverage'] * 100:.1f}%) | map {mt['n_points']:,} points | {SHA}",
    )
    gs = fig.add_gridspec(1, 2, left=0.14, right=0.965, top=top, bottom=0.10, wspace=0.30)

    # Panel A: seen vs new per kind — the checkpoint's horizon
    ax = fig.add_subplot(gs[0, 0])
    style_axes(ax)
    kinds = ["video", "segment", "memory"]
    labels = ["video notes", "segments", "memories"]
    ys = np.arange(len(kinds))[::-1]
    for y, k, lab in zip(ys, kinds, labels):
        seen = ood[k]["trained_on"]
        new = ood[k]["new_since_training"]
        tot = seen + new
        ax.barh(y, seen / tot, color=GOLD, height=0.58)
        ax.barh(y, new / tot, left=seen / tot, color=BLUE, height=0.58)
        ax.text(
            1.01,
            y,
            f"{new:,} new / {tot:,}  ({ood[k]['ood_frac_of_live'] * 100:.1f}%)",
            color=MUTED,
            fontsize=8.5,
            va="center",
        )
    ax.set_yticks(ys)
    ax.set_yticklabels(labels)
    ax.set_xlim(0, 1.30)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("fraction of today's corpus (gold = seen at training, blue = new since)")
    panel_title(ax, "What the Aug-8 checkpoint has seen")

    # Panel B: thumbnail coverage per map group, largest groups first
    ax = fig.add_subplot(gs[0, 1])
    style_axes(ax)
    groups = sorted(mt["groups"].items(), key=lambda kv: -kv[1]["n"])[:14]
    ys = np.arange(len(groups))[::-1]
    for y, (g, d) in zip(ys, groups):
        ax.barh(y, d["n"], color=DIM, height=0.62)
        ax.barh(y, d["img"], color=GOLD, height=0.62)
        ax.text(d["n"] + 8, y, f"{d['img_frac'] * 100:.0f}%", color=MUTED, fontsize=8, va="center")
    ax.set_yticks(ys)
    ax.set_yticklabels(["unassigned" if g == "-1" else f"group {g}" for g, _ in groups], fontsize=8)
    ax.set_xlabel("map points (grey = all, gold = with thumbnail)")
    ax.text(
        0.97,
        0.05,
        f"overall: {mt['img_total']}/{mt['n_points']} points carry imagery "
        f"({mt['img_total'] / mt['n_points'] * 100:.1f}%)",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=8.5,
        ha="right",
    )
    panel_title(ax, "Where the feature wall can show pictures")

    verdict(
        fig,
        f"every input exists — {ood['overall']['ood_frac_of_live'] * 100:.0f}% of today's corpus is unseen by the checkpoint",
    )
    save(fig, "01-coverage.png")


def fig02(r: dict) -> None:
    z = np.load(SAE / "data" / "acts_final_d2048_k32_s0.npz")
    idx, val = z["idx"], z["val"]
    fire = val > 0
    freq = np.bincount(idx[fire].ravel(), minlength=2048).astype(float)
    n = len(idx)
    prot = r["protagonist"]["rows"][0]
    top12 = prot["top"][:12]

    fig, top = figure(
        13.4,
        7.2,
        2,
        "atlas rung 0 — protagonist",
        "The protagonist latent, chosen by measurement",
        f"note: The moment we stopped understanding AI [AlexNet] (Welch Labs) | "
        f"loudest latent #1597, activation {top12[0]['act']:.3f}, fires on "
        f"{top12[0]['freq'] * 100:.1f}% of {n:,} vectors | cone check over all 2,048 latents | {SHA}",
    )
    gs = fig.add_gridspec(1, 2, left=0.055, right=0.955, top=top, bottom=0.10, wspace=0.42)

    # Panel A: the cone check — no latent is always-on, so "loudest" is content
    ax = fig.add_subplot(gs[0, 0])
    style_axes(ax)
    f_sorted = np.sort(freq)[::-1] / n
    ax.semilogy(np.arange(1, 2049), np.maximum(f_sorted, 1e-4), color=GOLD, lw=1.6)
    ax.axhline(0.5, color=RED, lw=1.0)
    ax.text(
        40,
        0.56,
        "always-on line — section 18's cone lived here; nothing does now",
        color=RED,
        fontsize=8,
    )
    ax.axhline(f_sorted[0], color=MUTED, lw=0.8, ls=":")
    ax.text(
        700,
        f_sorted[0] * 1.15,
        f"most frequent latent: {f_sorted[0] * 100:.1f}% of corpus",
        color=MUTED,
        fontsize=8,
    )
    ax.set_xlabel("latent, ranked by firing frequency")
    ax.set_ylabel("share of corpus it fires on (log)")
    ax.set_ylim(2e-3, 1.05)
    ax.set_yticks([1.0, 0.1, 0.01])
    ax.set_yticklabels(["100%", "10%", "1%"])
    ax.minorticks_off()
    panel_title(ax, "No cone: the empty band above every latent")

    # Panel B: the protagonist's fingerprint head
    ax = fig.add_subplot(gs[0, 1])
    style_axes(ax)
    ys = np.arange(len(top12))[::-1]
    for y, t in zip(ys, top12):
        c = CYAN if t["latent"] == 1597 else GOLD
        ax.barh(y, t["act"], color=c, height=0.62)
        name = t["name"] or "(outside named head)"
        ax.text(
            t["act"] + 0.004,
            y,
            f"#{t['latent']}  {name}",
            color=c if t["latent"] == 1597 else MUTED,
            fontsize=8,
            va="center",
        )
    ax.set_yticks([])
    ax.set_xlim(0, 0.52)
    ax.set_xlabel("pre-activation on the protagonist note")
    panel_title(ax, "Top 12 latents of the AlexNet note")

    verdict(fig, "protagonist = #1597 'educational breakdown of language model mechanics'")
    save(fig, "02-protagonist.png")


def main() -> None:
    r = json.loads((SAE / "rung0.json").read_text())
    fig01(r)
    fig02(r)
    (OUTDIR / "rung0.json").write_text(json.dumps(r, indent=1))
    print("copied rung0.json sidecar")


if __name__ == "__main__":
    main()
