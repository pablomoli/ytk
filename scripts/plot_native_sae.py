"""Native top-k SAE on the production Qwen space — what it costs, what it says.

Reads the artifacts written by experiments/sae_qwen/ and renders the two
house-style figures in docs/assets/24-native-sae/.

    uv run --with matplotlib --with scikit-learn --with torch \
        python scripts/plot_native_sae.py
"""

from __future__ import annotations

import glob
import json
import sys
import textwrap
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
EXP = REPO / "experiments" / "sae_qwen"
OUTDIR = REPO / "docs" / "assets" / "24-native-sae"
sys.path.insert(0, str(REPO / "scripts"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DIM,
    DPI,
    FRAME,
    GOLD,
    MARGIN,
    MUTED,
    PANEL,
    PURPLE,
    RED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

CFG_ORDER = [(2048, 16), (2048, 32), (4096, 16), (4096, 32)]
CFG_COLOR = {(2048, 16): MUTED, (2048, 32): BLUE, (4096, 16): PURPLE, (4096, 32): GOLD}


def hdr_fix(fig):
    fig.texts[1].set_x(MARGIN + 0.092)


def dark_legend(ax, handles, loc="lower right", ncol=1, fs=8.2):
    leg = ax.legend(
        handles=handles,
        loc=loc,
        fontsize=fs,
        facecolor=PANEL,
        edgecolor=FRAME,
        labelcolor=TEXT,
        framealpha=1.0,
        borderpad=0.55,
        ncol=ncol,
    )
    leg.set_zorder(8)
    return leg


def runs(tag):
    out = []
    for f in sorted(glob.glob(str(EXP / f"results_{tag}_s*.json"))):
        out.append(json.loads(Path(f).read_text())[0])
    return out


def fig01(sweep, faith, faith_final):
    final, restrict = runs("final"), runs("restrict")

    fig, top = figure(
        14.6,
        6.9,
        1,
        "a native SAE on 16k vectors",
        "Training a top-k autoencoder directly on the production Qwen space",
        meta="16,483 deduplicated 1024-d vectors from 5,026 notes · held-out split at note level "
        "(10%) · 3 seeds per config · AuxK revival · best-val checkpoint kept",
    )
    hdr_fix(fig)
    x0, w, gap = 0.078, 0.245, 0.077
    bot, h = 0.155, top - 0.245
    axA = fig.add_axes([x0, bot, w, h])
    axB = fig.add_axes([x0 + w + gap, bot, w, h])
    axC = fig.add_axes([x0 + 2 * (w + gap), bot, w, h])

    # A — held-out reconstruction cosine; sweep, then the two extra conditions
    xs, vals_all, cols, ticks = [], [], [], []
    for i, (d, k) in enumerate(CFG_ORDER):
        rs = [r for r in sweep if r["d_sae"] == d and r["k"] == k]
        xs.append(i)
        vals_all.append([r["val"]["recon_cos"] for r in rs])
        cols.append(CFG_COLOR[(d, k)])
        ticks.append(f"{d}\nk={k}")
    for x, group, col, tick in (
        (4.9, final, CYAN, "2048/k32\n14k steps"),
        (6.3, restrict, RED, "2048/k32\ncontent only"),
    ):
        xs.append(x)
        vals_all.append([r["val"]["recon_cos"] for r in group])
        cols.append(col)
        ticks.append(tick)
    for x, vals, col in zip(xs, vals_all, cols):
        axA.bar(x, np.mean(vals), width=0.6, color=col, alpha=0.9, zorder=2)
        axA.scatter(
            [x] * len(vals), vals, s=28, facecolor=PANEL, edgecolor=TEXT, linewidth=0.9, zorder=5
        )
        axA.text(
            x,
            np.mean(vals) + 0.028,
            f"{np.mean(vals):.3f}",
            ha="center",
            color=TEXT,
            fontsize=9,
            zorder=6,
        )
    axA.axvline(3.9, color=FRAME, linewidth=1.0)
    axA.text(1.5, 0.955, "sweep, 4k steps", ha="center", color=MUTED, fontsize=8.5)
    axA.text(5.6, 0.955, "to plateau, 14k steps", ha="center", color=MUTED, fontsize=8.5)
    axA.set_xticks(xs, ticks, fontsize=8)
    axA.set_xlim(-0.75, 7.05)
    axA.set_ylim(0, 1.03)
    style_axes(axA)
    axA.set_ylabel("held-out reconstruction cosine", fontsize=TICK_SIZE)
    panel_title(axA, "how much of the vector survives", width=40)
    fig.text(
        x0,
        0.072,
        "L0 = k exactly in every run; dead features 0.00-0.08% throughout",
        color=MUTED,
        fontsize=8.5,
    )

    # B — training curves: the sweep budget and the plateau runs
    for d, k in CFG_ORDER:
        for r in sweep:
            if r["d_sae"] != d or r["k"] != k:
                continue
            xs = [c[0] for c in r["curve"]]
            ys = [c[1] for c in r["curve"]]
            axB.plot(xs, ys, color=CFG_COLOR[(d, k)], linewidth=1.1, alpha=0.9)
            bi = int(np.argmax(ys))
            axB.scatter([xs[bi]], [ys[bi]], s=20, color=TEXT, zorder=6)
    for r in final:
        xs = [c[0] for c in r["curve"]]
        ys = [c[1] for c in r["curve"]]
        axB.plot(xs, ys, color=CYAN, linewidth=1.0, alpha=0.75, linestyle="--")
    axB.axvline(4000, color=MUTED, linewidth=0.8, linestyle=":")
    axB.text(4250, 0.665, "sweep budget", color=MUTED, fontsize=7.5, rotation=90, va="bottom")
    axB.set_ylim(0.64, 0.86)
    axB.set_xlim(0, 14300)
    axB.set_xticks([0, 4000, 8000, 12000], ["0", "4k", "8k", "12k"])
    style_axes(axB)
    axB.set_xlabel("training step (batch 512)", fontsize=TICK_SIZE)
    axB.set_ylabel("held-out reconstruction cosine", fontsize=TICK_SIZE)
    panel_title(axB, "the ceiling is data, not budget", width=40)
    dark_legend(
        axB,
        [
            Line2D([], [], color=CFG_COLOR[c], linewidth=2, label=f"{c[0]}, k={c[1]}")
            for c in CFG_ORDER
        ]
        + [Line2D([], [], color=CYAN, linewidth=1.2, linestyle="--", label="2048/k32, 14k steps")],
        loc="lower right",
        fs=7.8,
    )

    # C — retrieval cost, drawn as the drop from the real index
    orig5 = next(iter(faith["configs"].values()))["orig"]["hit@5"]
    hit5, ov10, xs, cols = [], [], [], []
    for i, (d, k) in enumerate(CFG_ORDER):
        rs = [v for key, v in faith["configs"].items() if key.startswith(f"sae_d{d}_k{k}_")]
        xs.append(i)
        hit5.append([r["recon"]["hit@5"] for r in rs])
        ov10.append(np.mean([r["overlap@10"] for r in rs]))
        cols.append(CFG_COLOR[(d, k)])
    fin = list(faith_final["configs"].values())
    xs.append(4.8)
    hit5.append([r["recon"]["hit@5"] for r in fin])
    ov10.append(np.mean([r["overlap@10"] for r in fin]))
    cols.append(CYAN)

    axC.axhline(orig5, color=RED, linewidth=1.4, linestyle="--", zorder=3)
    for x, hs, col in zip(xs, hit5, cols):
        m = float(np.mean(hs))
        axC.plot([x, x], [orig5, m], color=col, linewidth=2.2, zorder=4)
        axC.scatter(
            [x] * len(hs), hs, s=26, facecolor=PANEL, edgecolor=col, linewidth=1.1, zorder=6
        )
        axC.scatter([x], [m], s=90, color=col, zorder=7)
        axC.text(x + 0.16, m, f"{m:.3f}", ha="left", va="center", color=TEXT, fontsize=9, zorder=8)
    axC.plot(xs, ov10, color=GOLD, linewidth=1.4, marker="D", markersize=5, zorder=5)
    for x, o in zip(xs, ov10):
        axC.text(
            x, o - 0.016, f"{o:.2f}", ha="center", va="top", color=GOLD, fontsize=8.5, zorder=8
        )
    axC.text(
        -0.6,
        orig5 + 0.008,
        f"the real index: hit@5 {orig5:.3f}",
        color=RED,
        fontsize=8.5,
        ha="left",
        va="bottom",
        zorder=8,
    )
    axC.text(
        -0.6,
        0.655,
        "dots: hit@5 through an index of reconstructions",
        color=TEXT,
        fontsize=8.5,
        ha="left",
        zorder=8,
    )
    axC.text(
        -0.6,
        0.635,
        "gold: top-10 overlap with the real ranking",
        color=GOLD,
        fontsize=8.5,
        ha="left",
        zorder=8,
    )
    axC.axvline(3.95, color=FRAME, linewidth=1.0)
    axC.set_xticks(xs, [f"{d}\nk={k}" for d, k in CFG_ORDER] + ["2048/k32\n14k steps"], fontsize=8)
    axC.set_xlim(-0.75, 5.75)
    axC.set_ylim(0.62, 0.945)
    style_axes(axC)
    axC.set_ylabel("frozen-query retrieval, 156 queries", fontsize=TICK_SIZE)
    panel_title(axC, "retrieval through a reconstructed index", width=40)

    fig.text(
        MARGIN,
        0.035,
        "Real Qwen query vectors against an index of SAE reconstructions; the numpy mirror of the "
        "production ranking reproduces eval/retrieval/baseline.json exactly "
        "(hit@1 .712 / hit@5 .904 / hit@10 .942). Production search is unchanged and no baseline "
        "was re-stamped.",
        color=MUTED,
        fontsize=8.5,
    )
    return fig, "01-native-sae-cost.png"


def fig02(feats, taste, stab):
    named = [f for f in feats["features"] if f.get("name")]
    top14 = sorted(named, key=lambda f: -f["freq"])[:14]

    fig, top = figure(
        14.6,
        8.4,
        2,
        "what the latents say",
        "Named features of the production space, and the deliberate-save regression",
        meta=f"{feats['checkpoint']} · dict 2048, k=32 · names by claude-haiku-4-5 from each "
        "latent's 8 strongest excerpts — UNPROBED hypotheses, nothing here is causally tested",
    )
    hdr_fix(fig)
    axA = fig.add_axes([0.250, 0.095, 0.320, top - 0.135])
    axB = fig.add_axes([0.665, 0.50, 0.295, top - 0.54])
    axC = fig.add_axes([0.665, 0.095, 0.295, 0.315])

    conf_color = {"high": GOLD, "medium": BLUE, "low": DIM}
    y = np.arange(len(top14))[::-1]
    for yi, f in zip(y, top14):
        axA.barh(
            yi,
            100 * f["freq"],
            height=0.62,
            color=conf_color.get(str(f.get("name_confidence", "")).lower(), MUTED),
        )
        axA.text(
            100 * f["freq"] + 0.12, yi, f"#{f['feature']}", color=MUTED, fontsize=7.5, va="center"
        )
    axA.set_yticks(
        y, [textwrap.shorten(f["name"], 38, placeholder="…") for f in top14], fontsize=8.5
    )
    axA.set_xlim(0, 19.5)
    style_axes(axA)
    axA.set_xlabel("% of the 16,483 vectors the latent fires on", fontsize=TICK_SIZE)
    panel_title(axA, "the most-active named latents", width=60)
    ns = stab["named_subset"]
    axA.text(
        0.985,
        0.03,
        f"reproduced by an independent init:\n"
        f"{100 * ns['named_frac_above_0.8']:.0f}% of these top-100 latents,\n"
        f"{100 * ns['all_frac_above_0.8']:.0f}% of the full 2048 dictionary",
        transform=axA.transAxes,
        ha="right",
        va="bottom",
        color=RED,
        fontsize=8.5,
        zorder=8,
        bbox={"facecolor": PANEL, "edgecolor": FRAME, "boxstyle": "round,pad=0.45"},
    )
    dark_legend(
        axA,
        [Patch(facecolor=conf_color[c], label=f"{c} confidence") for c in ("high", "medium")],
        loc="center right",
        fs=8,
    )

    targets = [
        ("A   r>=1 vs r=0\n(deliberate save)", "A_deliberate", RED),
        ("B   r>=2 vs r=1\n(wrote a thought)", "B_thought", GOLD),
        ("C   r>=2 vs r=1,\nInstagram only", "C_thought_instagram", BLUE),
    ]
    yb = np.arange(len(targets))[::-1]
    raw = taste["raw_baseline"]
    for yi, (lab, key, col) in zip(yb, targets):
        t = taste[key]
        axB.barh(yi, t["auc_mean"], height=0.48, color=col, alpha=0.9, zorder=3)
        axB.errorbar(
            t["auc_mean"], yi, xerr=t["auc_sd"], color=TEXT, linewidth=1.0, capsize=3, zorder=6
        )
        axB.scatter(
            [t["auc_null_mean"]], [yi], marker="|", s=180, color=MUTED, linewidth=1.6, zorder=7
        )
        axB.scatter(
            [raw[key]],
            [yi],
            marker="D",
            s=34,
            facecolor=CYAN,
            edgecolor=PANEL,
            linewidth=0.6,
            zorder=8,
        )
        axB.text(
            t["auc_mean"] + t["auc_sd"] + 0.018,
            yi,
            f"{t['auc_mean']:.2f}",
            color=TEXT,
            fontsize=8.5,
            va="center",
        )
    axB.axvline(0.5, color=MUTED, linewidth=0.9, linestyle=":")
    axB.set_yticks(yb, [t[0] for t in targets], fontsize=8)
    axB.set_xlim(0.42, 1.30)
    axB.set_xticks([0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    axB.set_ylim(-0.7, 2.7)
    style_axes(axB)
    axB.set_xlabel("ROC AUC, 5x5-fold CV", fontsize=TICK_SIZE)
    panel_title(axB, "can the latents predict a save?", width=44)
    dark_legend(
        axB,
        [
            Line2D(
                [],
                [],
                marker="|",
                linestyle="none",
                markersize=10,
                color=MUTED,
                label="shuffled-label null",
            ),
            Line2D(
                [],
                [],
                marker="D",
                linestyle="none",
                markersize=6,
                color=CYAN,
                label="raw Qwen note vector",
            ),
        ],
        loc="center right",
        fs=7.6,
    )

    surv = taste["A_deliberate"]["survivors"]
    ys = np.arange(len(surv))[::-1]
    lo = min(s["coef_mean"] for s in surv)
    for yi, s in zip(ys, surv):
        neg = s["coef_mean"] < 0
        axC.barh(yi, s["coef_mean"], height=0.58, color=CYAN if neg else GOLD, zorder=3)
        axC.text(
            0.004 if neg else -0.004,
            yi,
            textwrap.shorten(s["name"] or f"#{s['feature']}", 31, placeholder="…"),
            ha="left" if neg else "right",
            va="center",
            color=TEXT,
            fontsize=7.6,
            zorder=6,
        )
    axC.axvline(0, color=MUTED, linewidth=0.9, zorder=4)
    axC.set_yticks([])
    axC.set_xlim(lo * 1.12, abs(lo) * 1.02)
    axC.set_ylim(-0.8, len(surv) - 0.2)
    style_axes(axC)
    axC.set_xlabel(
        "L1 coefficient — negative predicts r=0 (YouTube), positive predicts a save",
        fontsize=8.2,
    )
    panel_title(axC, "the 11 survivors of target A", width=44)

    fig.text(
        MARGIN,
        0.032,
        "target A is confounded by medium — every r>=1 note is Instagram/TikTok/web and every r=0 note "
        "is YouTube — so A reads the source, not the taste; B and C hold the medium fixed and find "
        "nothing sign-stable at 27 and 19 positives",
        color=MUTED,
        fontsize=8.5,
    )
    return fig, "02-latents-and-taste.png"


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    sweep = json.loads((EXP / "results_sweep.json").read_text())
    faith = json.loads((EXP / "faithfulness.json").read_text())
    faith_final = json.loads((EXP / "faithfulness_final.json").read_text())
    feats = json.loads((EXP / "features.json").read_text())
    taste = json.loads((EXP / "taste.json").read_text())
    stab = json.loads((EXP / "stability.json").read_text())
    for f, args in ((fig01, (sweep, faith, faith_final)), (fig02, (feats, taste, stab))):
        fig, name = f(*args)
        frame_panels(fig)
        out = OUTDIR / name
        fig.savefig(out, dpi=DPI, facecolor=BG)
        print(f"wrote {out.relative_to(REPO)} ({out.stat().st_size // 1024}KB)")
        plt.close(fig)


if __name__ == "__main__":
    main()
