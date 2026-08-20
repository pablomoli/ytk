"""Section 48 — the semantic compass: the registered gates, then the
surviving instrument.

Figure 01: five axes against their registered bars — two die, and why.
Figure 02: the three-axis compass reading four different kinds of object
with one glyph (adoption is an owner decision; the loss stands).

    YTK_VISUAL_INDEX=off uv run --with torch --with matplotlib \
        python scripts/plot_semantic_compass.py
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
    RED,
    figure,
    frame_panels,
    panel_title,
    semantic_rose,
    style_axes,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "experiments" / "sae_qwen"
OUTDIR = REPO / "docs" / "assets" / "48-semantic-compass"
AXIS_ORDER = ["spoken-written", "scroll-sit", "mine-world", "fresh-settled", "code-prose"]

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


def fig01(res: dict) -> None:
    g1 = res["gate1"]
    fig, top = figure(
        13.4,
        6.6,
        1,
        "the compass gates",
        "Five registered axes: three earn their names, two die of thin poles",
        f"per axis: held-out AUC (gold) vs 50 label-shuffle nulls (grey band = p5-p95) | "
        f"registered: AUC >= 0.80 AND null p95 < 0.60 | G2 signature stability "
        f"{res['gate2']['mean_cos']:.2f} (bar 0.90, pass) | {SHA}",
    )
    ax = fig.add_axes([0.09, 0.14, 0.86, top - 0.22])
    style_axes(ax)
    ys = np.arange(len(AXIS_ORDER))[::-1]
    for y, name in zip(ys, AXIS_ORDER):
        g = g1[name]
        ax.plot(
            [g["null_auc_mean"], g["null_auc_p95"]], [y, y], color=DIM, lw=6, solid_capstyle="butt"
        )
        ok = g["pass"]
        ax.scatter([g["auc"]], [y], s=70, color=GOLD if ok else MUTED, zorder=5)
        ax.text(
            g["auc"],
            y + 0.24,
            f"{g['auc']:.2f}",
            color=GOLD if ok else MUTED,
            fontsize=8.5,
            ha="center",
        )
        ax.text(
            1.005,
            y,
            f"{g['n_pole_a']} vs {g['n_pole_b']}" + ("" if ok else "  — fails"),
            color=MUTED,
            fontsize=8,
            va="center",
        )
    ax.axvline(0.80, color=RED, lw=1.2)
    ax.text(0.802, len(AXIS_ORDER) - 0.75, "registered bar", color=RED, fontsize=8)
    ax.axvline(0.60, color=RED, lw=0.8, ls=":")
    ax.text(0.602, -0.35, "null ceiling", color=RED, fontsize=7.5)
    from matplotlib.lines import Line2D

    leg = ax.legend(
        handles=[
            Line2D([], [], marker="o", ls="", color=GOLD, ms=8, label="held-out AUC (axis passes)"),
            Line2D([], [], marker="o", ls="", color=MUTED, ms=8, label="held-out AUC (axis fails)"),
            Line2D([], [], color=DIM, lw=6, label="label-shuffle null, mean to p95"),
        ],
        frameon=False,
        fontsize=8,
        loc="center",
        bbox_to_anchor=(0.42, 0.22),
    )
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    ax.set_yticks(ys)
    ax.set_yticklabels(AXIS_ORDER)
    ax.set_xlim(0.42, 1.09)
    ax.set_xlabel("held-out ROC AUC (grey = what shuffled labels achieve)")
    verdict(fig, "3/5 axes survive vs the registered 4 — the compass, as registered, is a loss")
    save(fig, "01-the-gates.png")


def fig02(res: dict) -> None:
    import torch

    sys.path.insert(0, str(SAE))

    z = np.load(SAE / "data" / "semantic_axes.npz", allow_pickle=True)
    A = z["axes"]
    kept = [str(s) for s in z["names"]]
    pole_a = {"scroll-sit": "SCROLL", "mine-world": "MINE", "fresh-settled": "FRESH"}
    pole_b = {"scroll-sit": "SIT", "mine-world": "WORLD", "fresh-settled": "SETTLED"}
    poles = [pole_a[k] for k in kept] + [pole_b[k] for k in kept]

    rows = [json.loads(x) for x in (SAE / "data" / "rows.jsonl").read_text().splitlines()]
    X = np.load(SAE / "data" / "vectors.npz")["X"].astype(np.float32)
    tr = json.loads((SAE / "trace.json").read_text())
    v_prot = np.asarray(tr["vector"], np.float32)

    blob = torch.load(SAE / "checkpoints" / "final_d2048_k32_s0.pt", map_location="cpu")
    W_dec = blob["state"]["W_dec"].numpy()
    W_dec = W_dec / np.maximum(np.linalg.norm(W_dec, axis=1, keepdims=True), 1e-9)

    # the cell's signature: mean vector of its scored notes, via the doc join
    doc_idx = [i for i, r in enumerate(rows) if r["kind"] != "segment"]
    Xd = X[doc_idx]
    Xd = Xd / np.maximum(np.linalg.norm(Xd, axis=1, keepdims=True), 1e-9)

    objs = [
        ("the AlexNet note", v_prot, CYAN),
        ("latent #1597 (decoder)", W_dec[1597], CYAN),
        ("latent #977 EpicMap (decoder)", W_dec[977], GOLD),
        ("the whole corpus (mean note)", Xd.mean(0), MUTED),
    ]
    fig, top = figure(
        16.5,
        6.4,
        2,
        "the surviving compass",
        "One glyph, four kinds of object — a note, two directions, a corpus",
        f"axes: {', '.join(kept)} (the three that passed) | signature = signed projection on "
        f"each axis, opposite spokes are opposite poles | shared scale across panels | "
        f"adoption is an owner decision; the registered loss stands | {SHA}",
    )
    gs = fig.add_gridspec(1, 4, left=0.03, right=0.97, top=top, bottom=0.06, wspace=0.12)
    sigs = [np.asarray(v / np.linalg.norm(v)) @ A.T for _, v, _ in objs]
    rmax = max(float(np.abs(s).max()) for s in sigs) * 1.15
    for k, ((name, _, col), sig) in enumerate(zip(objs, sigs)):
        ax = fig.add_subplot(gs[0, k])
        semantic_rose(ax, sig, poles, color=col, rmax=rmax)
        panel_title(ax, name, width=30)
    verdict(
        fig,
        "the note reads SIT+WORLD (ingested longform), EpicMap reads MINE (work) — the glyph is legible",
    )
    save(fig, "02-the-surviving-compass.png")


def main() -> None:
    res = json.loads((SAE / "axes.json").read_text())
    fig01(res)
    fig02(res)
    (OUTDIR / "axes.json").write_text(json.dumps(res, indent=1))
    print("copied axes.json sidecar")


if __name__ == "__main__":
    main()
