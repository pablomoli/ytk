"""Section 47 — the GEN gate result (#183 rung 7).

One figure: the held-out agreement distribution against its shuffled-pairs
control, with the pre-registered bar drawn where it was set before the
translator existed.

    uv run --with matplotlib python scripts/plot_gen_gate.py
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
    RED,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "experiments" / "sae_qwen"
OUTDIR = REPO / "docs" / "assets" / "47-gen-gate"

SHA = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
).stdout.strip()


def main() -> None:
    r = json.loads((SAE / "gen_translator.json").read_text())
    z = np.load(SAE / "data" / "gen_translator.npz")
    agr, agr0 = z["agr"], z["agr0"]

    fig, top = figure(
        13.4,
        6.6,
        1,
        "the GEN gate",
        "The translator carries signal — and not enough to trust a picture",
        f"{r['n_heldout']} held-out notes | agreement = |top-10 CLIP neighbors shared| / 10, "
        f"native vs translated query | mean {r['mean_agreement']:.2f}, control "
        f"{r['control_mean']:.2f} | ridge lambda {r['ridge_lambda']}, seed {r['seed']}, "
        f"CLIP ViT-L/14 text (77-token truncation) | {SHA}",
    )
    ax = fig.add_axes([0.07, 0.13, 0.88, top - 0.20])
    bins = np.linspace(0, 1, 21)
    ax.hist(agr0, bins=bins, density=True, color=DIM, label="shuffled-pairs control")
    ax.hist(
        agr,
        bins=bins,
        density=True,
        histtype="step",
        linewidth=2.0,
        color=GOLD,
        label="real translator",
    )
    ax.axvline(0.40, color=RED, linewidth=1.4)
    ax.text(
        0.405,
        ax.get_ylim()[1] * 0.9,
        "registered bar 0.40\n(set before training)",
        color=RED,
        fontsize=8.5,
    )
    leg = ax.legend(frameon=False, fontsize=9)
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("top-10 neighbor agreement, native CLIP vs translated Qwen")
    ax.set_ylabel("density")
    panel_title(
        ax,
        f"mean {r['mean_agreement']:.2f}: 23x the control, 0.18 short of the bar",
        width=70,
    )
    verdict(fig, "FAIL — GEN mode stays closed; the fourth registered loss on the record")
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / "01-the-gate.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    (OUTDIR / "gen_translator.json").write_text(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
