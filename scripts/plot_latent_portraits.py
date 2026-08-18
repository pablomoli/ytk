"""Section 49 — latent portraits: the wall, the gate, the passport.

Figure 01: 48 latents wearing faces composited purely from corpus pixels.
Figure 02: the identifiability gate that licenses them. Figure 03: the
protagonist's passport — every instrument of the epic on one page for one
note (allowed because P1 passed).

    YTK_VISUAL_INDEX=off uv run --with torch --with matplotlib \
        python scripts/plot_latent_portraits.py
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
    TEXT,
    figure,
    frame_panels,
    panel_title,
    semantic_rose,
    style_axes,
    vector_image,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "experiments" / "sae_qwen"
OUTDIR = REPO / "docs" / "assets" / "49-latent-portraits"
PROT = 1597

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


def load():
    z = np.load(SAE / "data" / "portraits.npz")
    res = json.loads((SAE / "portraits.json").read_text())
    feats = {int(f): k for k, f in enumerate(z["feats"])}
    names = {
        f["feature"]: (f.get("name"), f["freq"])
        for f in json.loads((SAE / "features.json").read_text())["features"]
    }
    return z, res, feats, names


def fig01(z, res, feats, names) -> None:
    # the 48 most frequent NAMED latents that qualify
    ranked = [f for f in sorted(names, key=lambda f: -names[f][1]) if f in feats][:48]
    fig, top = figure(
        16.5,
        13.6,
        1,
        "the portrait wall",
        "Forty-eight latents wearing faces made only of corpus pixels",
        f"portrait = activation-weighted mean of the latent's top-24 exemplar thumbnails, "
        f"center-cropped 128x128 | {res['n_qualifying']} latents qualify (>= 12 image "
        f"exemplars) | identifiability AUC {res['auc']:.2f} (figure 02) | every pixel owned "
        f"by a note | {SHA}",
    )
    gs = fig.add_gridspec(
        6, 8, left=0.03, right=0.97, top=top, bottom=0.03, wspace=0.16, hspace=0.42
    )
    for k, f in enumerate(ranked):
        ax = fig.add_subplot(gs[k // 8, k % 8])
        ax.imshow(z["portraits"][feats[f]], interpolation="bilinear")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(CYAN if f == PROT else DIM)
        name = names[f][0] or ""
        ax.set_title(
            f"#{f}  {name[:26]}",
            color=CYAN if f == PROT else MUTED,
            fontsize=6.0,
            pad=2.5,
            loc="left",
        )
    verdict(fig, "no model imagined these — the corpus painted them, and they are tellable apart")
    save(fig, "01-the-wall.png")


def fig02(z, res) -> None:
    same, cross = z["same"], z["cross"]
    fig, top = figure(
        13.4,
        6.4,
        2,
        "the identifiability gate",
        "A latent's face survives being built from the other half of its evidence",
        f"{res['n_qualifying']} latents | same = pixel correlation of disjoint-half portraits "
        f"of one latent | cross = 2,000 cross-latent pairs | AUC {res['auc']:.3f} vs the "
        f"registered 0.80 | medians {res['same_median_r']:.2f} vs {res['cross_median_r']:.2f} "
        f"| {SHA}",
    )
    ax = fig.add_axes([0.07, 0.14, 0.88, top - 0.22])
    bins = np.linspace(-0.4, 1.0, 50)
    ax.hist(cross, bins=bins, density=True, color=DIM, label="different latents (null)")
    ax.hist(
        same,
        bins=bins,
        density=True,
        histtype="step",
        linewidth=2.0,
        color=GOLD,
        label="same latent, disjoint halves",
    )
    leg = ax.legend(frameon=False, fontsize=9)
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("pixel correlation between two portraits")
    ax.set_ylabel("density")
    panel_title(ax, f"AUC {res['auc']:.3f} — the registered bar was 0.80", width=60)
    verdict(fig, "PASS — portraits are identities, not mush; the wall and the hub may wear them")
    save(fig, "02-the-gate.png")


def fig03(z, res, feats, names) -> None:

    sys.path.insert(0, str(SAE))

    tr = json.loads((SAE / "trace.json").read_text())
    az = np.load(SAE / "data" / "semantic_axes.npz", allow_pickle=True)
    A, kept = az["axes"], [str(s) for s in az["names"]]
    pole_a = {"scroll-sit": "SCROLL", "mine-world": "MINE", "fresh-settled": "FRESH"}
    pole_b = {"scroll-sit": "SIT", "mine-world": "WORLD", "fresh-settled": "SETTLED"}
    poles = [pole_a[k] for k in kept] + [pole_b[k] for k in kept]
    v = np.asarray(tr["vector"], np.float32)
    code = np.zeros(2048, np.float32)
    for f, a in tr["code"].items():
        code[int(f)] = a

    fig, top = figure(
        16.5,
        7.8,
        3,
        "the passport",
        "One note's complete papers, every stamp earned by a gate",
        f"'{tr['title']}' | portrait: #{PROT}'s (gate 49); rose: sections 48's surviving axes; "
        f"fingerprint: 2048d code, #{PROT} inked (rung 1); cell + neighbors: sections 44/46 | "
        f"{tr['named_mass_frac']:.0%} of code mass named | {SHA}",
    )
    gs = fig.add_gridspec(
        2,
        4,
        width_ratios=[1.15, 1, 1, 1.25],
        left=0.04,
        right=0.97,
        top=top,
        bottom=0.075,
        wspace=0.22,
        hspace=0.30,
    )

    ax = fig.add_subplot(gs[:, 0])
    ax.imshow(z["portraits"][feats[PROT]], interpolation="bilinear")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(CYAN)
        s.set_linewidth(1.6)
    panel_title(ax, f"portrait of #{PROT} — corpus pixels only", width=30)

    ax = fig.add_subplot(gs[0, 1])
    semantic_rose(ax, (v / np.linalg.norm(v)) @ A.T, poles, color=CYAN)
    panel_title(ax, "the note's compass", width=24)

    ax = fig.add_subplot(gs[1, 1])
    vector_image(ax, code, annotate=[(PROT, "#1597")])
    panel_title(ax, "its code, inked", width=24)

    ax = fig.add_subplot(gs[:, 2])
    ax.axis("off")
    top5 = tr["top_latents"][:5]
    lines = [f"#{t['latent']}  {(t['name'] or '')[:30]}\n        act {t['act']:.2f}" for t in top5]
    ax.text(0.02, 0.97, "speaks in latents", color=TEXT, fontsize=9.5, va="top", weight="bold")
    ax.text(0.02, 0.88, "\n".join(lines), color=MUTED, fontsize=8, va="top", linespacing=1.7)
    ax.text(
        0.02,
        0.30,
        f"resides: cell {','.join(map(str, tr['atlas_cell']['cell']))}\n"
        f"({tr['atlas_cell']['cell_method'].split(' (')[0]})\n\n"
        f"neighbors shared across\nlenses: {tr['neighbor_overlap']}/5",
        color=MUTED,
        fontsize=8,
        va="top",
        linespacing=1.6,
    )

    ax = fig.add_subplot(gs[:, 3])
    ax.axis("off")
    shared = {n["title"] for n in tr["neighbors_qwen"]} & {n["title"] for n in tr["neighbors_sae"]}
    rows_txt = []
    for n in tr["neighbors_qwen"]:
        mark = "*" if n["title"] in shared else " "
        rows_txt.append(f"{mark} {n['title'][:40]}")
    ax.text(0.0, 0.97, "keeps company with", color=TEXT, fontsize=9.5, va="top", weight="bold")
    ax.text(0.0, 0.86, "\n".join(rows_txt), color=MUTED, fontsize=8, va="top", linespacing=1.8)
    ax.text(0.0, 0.40, "* = both lenses agree", color=MUTED, fontsize=7.5, va="top")
    ax.text(
        0.0,
        0.30,
        f"gates carried:\n49 portraits AUC {res['auc']:.2f}\n48 compass: 3 axes (registered loss)\n"
        f"47 GEN: closed\n45 strips: licensed\n43 wall: coherent\n42 protagonist: measured",
        color=MUTED,
        fontsize=7.5,
        va="top",
        linespacing=1.6,
    )
    verdict(fig, "a note can now be known by face, compass, code, address, and company")
    save(fig, "03-the-passport.png")


def main() -> None:
    z, res, feats, names = load()
    fig01(z, res, feats, names)
    fig02(z, res)
    fig03(z, res, feats, names)
    slim = json.loads((SAE / "portraits.json").read_text())
    slim.pop("latents", None)
    (OUTDIR / "portraits.json").write_text(json.dumps(slim, indent=1))
    print("copied portraits.json sidecar")


if __name__ == "__main__":
    main()
