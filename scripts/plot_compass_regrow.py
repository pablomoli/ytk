"""Section 52 figures: the regrown compass and the confound it had to survive.

uv run --with matplotlib python scripts/plot_compass_regrow.py
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
    BG,
    BLUE,
    DIM,
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    RED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "docs" / "assets" / "52-compass-regrow"
EXP = ROOT / "experiments" / "sae_qwen"
STORE = Path.home() / ".ytk" / "sae" / "data"

AXES = ["spoken-written", "scroll-sit", "mine-world", "fresh-settled", "code-prose"]
BAR = 0.80  # the registered AUC threshold


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def fig01(res: dict, blob) -> None:
    """Every observation against its own null, on one ruler."""
    g = res["gate1"]
    fig, top = figure(
        12.4,
        7.4,
        1,
        "the registered gates",
        "Five axes, five nulls: where each observation falls in its own shuffle",
        f"held-out ROC AUC against 200 label shuffles per axis; bar at {BAR:.2f} and "
        f"p < 0.05; register axis split by video, majority pole subsampled; seed "
        f"{res['seed']}",
    )
    gs = fig.add_gridspec(1, 1, left=0.155, right=1 - MARGIN - 0.015, top=top, bottom=0.115)
    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "observed separation (gold) inside the shuffled null (grey)")

    for i, name in enumerate(AXES):
        nulls = np.asarray(blob[f"null_{name}"])
        hist, edges = np.histogram(nulls, bins=30, range=(0.30, 1.0))
        h = hist / hist.max() * 0.34
        c = (edges[:-1] + edges[1:]) / 2
        ax.fill_between(c, i - h, i + h, color=DIM, lw=0, zorder=2)
        obs = g[name]["auc"]
        ax.plot([obs, obs], [i - 0.40, i + 0.40], color=GOLD, lw=2.4, zorder=4)
        ax.plot([obs], [i], marker="D", ms=8.5, color=GOLD, zorder=5)
        ax.text(
            obs - 0.012,
            i + 0.005,
            f"{obs:.3f}",
            color=TEXT,
            fontsize=TICK_SIZE + 0.5,
            ha="right",
            va="center",
            zorder=6,
        )
        ax.text(
            np.median(nulls) + 0.055,
            i - 0.30,
            f"null {np.median(nulls):.2f}",
            color=MUTED,
            fontsize=TICK_SIZE - 0.5,
            ha="left",
            va="center",
        )
        meth = "ridge probe" if g[name]["method"].startswith("ridge") else "contrast"
        ax.text(
            0.315,
            i + 0.30,
            f"{g[name]['n_pole_a']:,} / {g[name]['n_pole_b']:,}   {meth}",
            color=MUTED,
            fontsize=TICK_SIZE - 0.5,
            ha="left",
            va="center",
        )

    ax.axvline(BAR, color=RED, lw=1.7, ls="--", zorder=3)
    ax.text(
        BAR - 0.008,
        len(AXES) - 0.62,
        "registered bar 0.80",
        color=RED,
        fontsize=TICK_SIZE,
        ha="right",
        va="bottom",
        rotation=90,
    )
    ax.set_yticks(range(len(AXES)))
    ax.set_yticklabels([a.replace("-", " <-> ") for a in AXES])
    ax.set_ylim(-0.62, len(AXES) - 0.38)
    ax.set_xlim(0.30, 1.02)
    ax.invert_yaxis()
    ax.set_xlabel("held-out ROC AUC")
    verdict(fig, "5 of 5 axes pass — the compass regrows")
    save(fig, "01-the-gates.png")


def fig02(res: dict, ctl: dict, cblob) -> None:
    """The rival explanation, drawn and then killed on the same ruler."""
    lc, cm = ctl["length_confound"], ctl["caliper_matched"]
    L, y = cblob["len_all"], cblob["y_all"]
    Lm = cblob["len_matched"]

    fig, top = figure(
        13.0,
        6.6,
        2,
        "the confound the gate could not catch",
        "Segments are shorter than notes — so is the axis reading register, or size?",
        f"caliper {cm['caliper']}; {cm['n_pairs']} matched pairs, "
        f"{cm['n_notes_unmatched']} notes had no segment their length; "
        f"length-alone AUC {lc['length_alone_auc_full']:.3f} -> "
        f"{cm['length_alone_auc_matched']:.3f}, probe "
        f"{res['gate1']['spoken-written']['auc']:.3f} -> {cm['probe_auc_matched']:.3f}",
    )
    gs = fig.add_gridspec(
        1, 2, left=0.062, right=1 - MARGIN - 0.015, top=top, bottom=0.135, wspace=0.20
    )

    axA = fig.add_subplot(gs[0])
    style_axes(axA)
    panel_title(axA, "the poles barely share a length")
    bins = np.linspace(0, 2600, 60)
    axA.hist(L[y == 1], bins=bins, density=True, color=GOLD, alpha=0.55, label="spoken — segments")
    axA.hist(L[y == 0], bins=bins, density=True, color=BLUE, alpha=0.55, label="written — notes")
    lo, hi = float(Lm.min()), float(Lm.max())
    axA.axvspan(lo, hi, color=TEXT, alpha=0.06, zorder=0)
    axA.text(
        (lo + hi) / 2,
        axA.get_ylim()[1] * 0.94,
        "matched band",
        color=MUTED,
        fontsize=TICK_SIZE,
        ha="center",
        va="top",
    )
    axA.set_xlabel("document length (characters)")
    axA.set_ylabel("density")
    leg = axA.legend(loc="upper right", frameon=False, fontsize=TICK_SIZE)
    for t in leg.get_texts():
        t.set_color(MUTED)

    axB = fig.add_subplot(gs[1])
    style_axes(axB)
    panel_title(axB, "matching the lengths: what survives and what does not")
    x = [0, 1]
    length = [lc["length_alone_auc_full"], cm["length_alone_auc_matched"]]
    probe = [res["gate1"]["spoken-written"]["auc"], cm["probe_auc_matched"]]
    axB.plot(x, length, color=DIM, lw=3.0, marker="o", ms=9, zorder=3)
    axB.plot(x, probe, color=GOLD, lw=3.0, marker="D", ms=9, zorder=4)
    axB.axhline(BAR, color=RED, lw=1.6, ls="--", zorder=2)
    axB.text(-0.17, BAR + 0.014, "bar 0.80", color=RED, fontsize=TICK_SIZE, ha="left", va="bottom")
    for xi, v in zip(x, length):
        axB.text(xi, v - 0.040, f"{v:.3f}", color=MUTED, fontsize=TICK_SIZE + 0.5, ha="center")
    for xi, v in zip(x, probe):
        axB.text(xi, v + 0.024, f"{v:.3f}", color=TEXT, fontsize=TICK_SIZE + 0.5, ha="center")
    # Series are named at the right end, where the lines have separated. At the
    # left they sit 0.018 apart and any label there lands on the other series.
    for label, col, series in (
        ("embedding probe", GOLD, probe),
        ("length alone", MUTED, length),
    ):
        axB.text(1.07, series[1], label, color=col, fontsize=TICK_SIZE + 1, ha="left", va="center")
    axB.set_xticks(x)
    axB.set_xticklabels(["all pairs", "length-matched"])
    axB.set_xlim(-0.20, 1.78)
    axB.set_ylim(0.42, 1.045)
    axB.set_ylabel("held-out ROC AUC")

    verdict(fig, "length collapses to 0.68, the probe holds 0.96 — register, not size")
    save(fig, "02-the-confound.png")


def main() -> None:
    res = json.loads((EXP / "axes_regrow.json").read_text())
    ctl = json.loads((EXP / "register_control.json").read_text())
    blob = np.load(STORE / "semantic_axes_regrow.npz", allow_pickle=True)
    cblob = np.load(STORE / "register_control.npz")
    fig01(res, blob)
    fig02(res, ctl, cblob)


if __name__ == "__main__":
    main()
