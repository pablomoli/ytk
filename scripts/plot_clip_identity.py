"""Section 51 — the portrait claim re-judged, and closed.

One figure: the CLIP-space gate beside its pixel-space predecessor, the
distributions that explain the number, and the structural ceiling in the
meta line.

    uv run --with matplotlib python scripts/plot_clip_identity.py
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
    DIM,
    DPI,
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
OUTDIR = REPO / "docs" / "assets" / "51-clip-identity"

SHA = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
).stdout.strip()


def main() -> None:
    res = json.loads((SAE / "clip_identity.json").read_text())
    z = np.load(SAE / "data" / "clip_identity.npz")
    same, cross = z["same"], z["cross"]

    fig, top = figure(
        13.4,
        6.6,
        1,
        "the second judge",
        "Perceptually judged, latent portraits still have almost no identity",
        f"same split-half design as section 49, judge = CLIP ViT-L/14 image cosine | AUC "
        f"{res['auc']:.2f} vs the registered 0.80 (pixel judge: 0.43) | post-hoc, disclosed: "
        f"genre-centering lifts only to 0.64 | the ceiling is structural — "
        f"{res['n_unique_thumbnails']} unique images serve {res['n_qualifying']} latents, "
        f"random latent pairs already share 11% of their images | {SHA}",
    )
    ax = fig.add_axes([0.07, 0.14, 0.88, top - 0.22])
    bins = np.linspace(0.75, 1.0, 60)
    ax.hist(cross, bins=bins, density=True, color=DIM, label="different latents")
    ax.hist(
        same,
        bins=bins,
        density=True,
        histtype="step",
        linewidth=2.0,
        color=GOLD,
        label="same latent, disjoint halves",
    )
    ax.axvline(float(np.median(same)), color=GOLD, lw=1.2, ls="--")
    ax.axvline(float(np.median(cross)), color=MUTED, lw=1.2, ls=":")
    ax.text(
        float(np.median(cross)) - 0.002,
        ax.get_ylim()[1] * 0.55,
        "medians 0.007 apart:\nin CLIP space every thumbnail\nresembles every other —\nthe genre is its own cone",
        color=MUTED,
        fontsize=8.5,
        ha="right",
    )
    leg = ax.legend(frameon=False, fontsize=9, loc="upper left")
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("CLIP-image cosine between two identity vectors")
    ax.set_ylabel("density")
    panel_title(ax, f"AUC {res['auc']:.2f} — the registered bar was 0.80", width=60)
    verdict(fig, "FAIL — dead in both judges; the portrait metaphor closes for good")
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / "01-the-second-judge.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    slim = {k: v for k, v in res.items() if k != "medoids"}
    (OUTDIR / "clip_identity.json").write_text(json.dumps(slim, indent=1))


if __name__ == "__main__":
    main()
