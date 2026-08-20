"""Section 50 — constellations: the gate, then the shapes themselves.

Figure 01: coherence against the frequency-matched null. Figure 02: four
codes on the one canonical layout — protagonist, tightest, loosest, and a
null draw — the owner's conjecture made visible.

    YTK_VISUAL_INDEX=off uv run --with torch --with matplotlib \
        python scripts/plot_constellations.py
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
    FRAME,
    GOLD,
    MUTED,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "experiments" / "sae_qwen"
OUTDIR = REPO / "docs" / "assets" / "50-constellations"

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


def fig01(res: dict, z) -> None:
    fig, top = figure(
        13.4,
        6.4,
        1,
        "the shape gate",
        "A code's 32 latents huddle far beyond frequency-matched chance",
        f"coherence = activation-weighted mean pairwise decoder cosine, ambient 1024d | null = "
        f"100 draws of 32 latents per note, sampled by corpus firing frequency, same weights | "
        f"{res['n_notes']} notes | registered bar: 60% beat their null p95 | {SHA}",
    )
    ax = fig.add_axes([0.07, 0.14, 0.88, top - 0.22])
    lo = min(float(z["null_p95"].min()), float(z["obs"].min())) - 0.005
    hi = max(float(z["null_p95"].max()), float(z["obs"].max())) + 0.005
    bins = np.linspace(lo, hi, 48)
    ax.hist(z["null_p95"], bins=bins, density=True, color=DIM, label="each note's null p95")
    ax.hist(
        z["obs"],
        bins=bins,
        density=True,
        histtype="step",
        linewidth=2.0,
        color=GOLD,
        label="each note's observed coherence",
    )
    pv = res["protagonist"]["coherence"]
    ax.axvline(pv, color=CYAN, linewidth=1.6)
    ax.text(pv + 0.001, ax.get_ylim()[1] * 0.9, f"protagonist {pv:.3f}", color=CYAN, fontsize=8.5)
    leg = ax.legend(frameon=False, fontsize=9)
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("code coherence (mean pairwise decoder cosine)")
    ax.set_ylabel("density")
    panel_title(
        ax,
        f"{res['frac_beat_null_p95'] * 100:.0f}% of notes beat their own null p95 — bar was 60%",
        width=66,
    )
    verdict(fig, "PASS at 89% — the code has a shape, and the shape is the note's")
    save(fig, "01-the-shape-gate.png")


def fig02(res: dict, z) -> None:
    import torch

    xy = z["layout"]
    rng = np.random.default_rng(50)
    blob = torch.load(
        SAE / "checkpoints" / "final_d2048_k32_s0.pt", map_location="cpu", weights_only=False
    )
    W = blob["state"]["W_dec"].numpy()
    W = W / np.maximum(np.linalg.norm(W, axis=1, keepdims=True), 1e-9)
    G = W @ W.T
    EDGE = 0.15  # draw a line where two active latents' decoders agree past this

    # frequency weights for the null panel
    za = np.load(SAE / "data" / "acts_final_d2048_k32_s0.npz")
    idxa, vala = za["idx"], za["val"]
    freq = np.bincount(idxa[vala > 0].ravel(), minlength=2048).astype(np.float64)
    fire_p = freq / freq.sum()

    prot = res["protagonist"]
    tight, loose = res["extremes"]["tightest"], res["extremes"]["loosest"]
    null_lat = rng.choice(2048, 32, replace=False, p=fire_p)
    panels = [
        ("the AlexNet note", prot["latents"], prot["acts"], CYAN, prot["coherence"]),
        (tight["title"][:34], tight["latents"], tight["acts"], GOLD, tight["coherence"]),
        (loose["title"][:34], loose["latents"], loose["acts"], MUTED, loose["coherence"]),
        ("frequency-matched chance", null_lat, prot["acts"], DIM, None),
    ]
    fig, top = figure(
        16.5,
        6.6,
        2,
        "four constellations, one sky",
        "The same canonical layout under every code — shape is now comparable",
        "background: all 2,048 latents at their frozen PCA-of-decoder positions | stars: active "
        "latents, area = activation | edges: latent pairs with decoder cosine > 0.15, alpha by "
        f"strength | fourth panel: a chance draw wearing the protagonist's weights | {SHA}",
    )
    gs = fig.add_gridspec(1, 4, left=0.03, right=0.97, top=top, bottom=0.075, wspace=0.10)
    for k, (title, lats, acts, col, coh) in enumerate(panels):
        ax = fig.add_subplot(gs[0, k])
        ax.set_facecolor("#000000")
        for s in ax.spines.values():
            s.set_color(FRAME)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.scatter(xy[:, 0], xy[:, 1], s=1.2, color=DIM, alpha=0.45, linewidths=0)
        lats = np.asarray(lats, int)
        w = np.asarray(acts, float)
        # the statistic, drawn: an edge per latent pair whose decoder cosine
        # clears the threshold — coherence becomes visible connectivity
        n_edges = 0
        for a in range(len(lats)):
            for b in range(a + 1, len(lats)):
                g = float(G[lats[a], lats[b]])
                if g > EDGE:
                    ax.plot(
                        [xy[lats[a], 0], xy[lats[b], 0]],
                        [xy[lats[a], 1], xy[lats[b], 1]],
                        color=col,
                        lw=0.8,
                        alpha=min(0.2 + 2.2 * (g - EDGE), 0.9),
                        zorder=2,
                    )
                    n_edges += 1
        ax.scatter(
            xy[lats, 0],
            xy[lats, 1],
            s=30 + 500 * (w / w.max()),
            color=col,
            alpha=0.85,
            linewidths=0,
            zorder=3,
        )
        ax.set_xlim(xy[:, 0].min() * 1.08, xy[:, 0].max() * 1.08)
        ax.set_ylim(xy[:, 1].min() * 1.08, xy[:, 1].max() * 1.08)
        tag = f"coherence {coh:.3f}" if coh is not None else "chance"
        panel_title(ax, f"{title} — {tag} — {n_edges} edges", width=32)
    verdict(fig, "coherence is edge count: the work note webs, the listicle frays, chance is dust")
    save(fig, "02-four-constellations.png")


def main() -> None:
    res = json.loads((SAE / "constellations.json").read_text())
    z = np.load(SAE / "data" / "constellations.npz")
    fig01(res, z)
    fig02(res, z)
    (OUTDIR / "constellations.json").write_text(json.dumps(res, indent=1))
    print("copied constellations.json sidecar")


if __name__ == "__main__":
    main()
