#!/usr/bin/env python
"""18.3 — name the cone: are the always-on features readable register/domain?

Reads fingerprints.npz (18.2). Two presence notions, both reported:

- union presence (sum > 0): any activation on any token. Measured mean
  per-note L0 of 5209/16384 — a third of the dictionary ticks somewhere in
  every 300-500-token note, so >90% document frequency under this notion is
  mostly an artifact of union-over-tokens. Kept as the cautionary curve.
- mass presence (top-K per note by summed activation, K=256): a feature is
  present only where it carries real weight. The cone is defined here.

Registered prediction (preregistration.md): >= 5 features active in >90% of
notes, names describing register/domain. Kill: none above 70%.
Auto-explanations are hypotheses, not ground truth — feature 4932
("drug usage") fires on ' session', ' repo', ' skill' in a coding note —
so names are reported with that caveat and never read alone.

    uv run --with matplotlib python scripts/sae_cone.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    CYAN,
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    RED,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "18-sae-fingerprints"
MODEL_ID = "gemma-2-2b"
LAYER = "20-gemmascope-res-16k"
TOP_K = 256
TOP_NAMED = 20


def save(fig, name: str) -> None:
    frame_panels(fig)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def fetch_names(indices: list[int]) -> dict[int, str]:
    body = [{"modelId": MODEL_ID, "layer": LAYER, "index": int(i)} for i in indices]
    req = urllib.request.Request(
        "https://www.neuronpedia.org/api/features",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        feats = json.loads(resp.read())
    out = {}
    for f in feats:
        exps = f.get("explanations") or []
        out[int(f["index"])] = exps[0].get("description", "(no explanation)") if exps else "(none)"
    return out


def main() -> None:
    data = np.load(OUTDIR / "fingerprints.npz")
    S = data["sum"].astype(np.float32)
    manifest = json.loads((OUTDIR / "manifest.json").read_text())
    live = np.array([not m["skipped"] for m in manifest["notes"]])
    S = S[live]
    n = len(S)

    present_union = S > 0
    df_union = present_union.mean(axis=0)
    l0_union = present_union.sum(axis=1)

    # mass presence: top-K features per note by summed activation
    topk_idx = np.argsort(-S, axis=1)[:, :TOP_K]
    present_mass = np.zeros_like(present_union)
    rows = np.repeat(np.arange(n), TOP_K)
    present_mass[rows, topk_idx.ravel()] = True
    df_mass = present_mass.mean(axis=0)

    over90 = np.where(df_mass > 0.90)[0]
    over70 = np.where(df_mass > 0.70)[0]
    # rank the cone by mass among qualifying features
    order = sorted(np.where(df_mass > 0.70)[0], key=lambda i: -float(S[:, i].mean())) or list(
        np.argsort(-df_mass)[:TOP_NAMED]
    )
    order = order[:TOP_NAMED]
    named = fetch_names([int(i) for i in order])

    cone = {
        "n_notes": int(n),
        "presence": f"top-{TOP_K} per note by summed activation",
        "features_over_90pct": len(over90),
        "features_over_70pct": len(over70),
        "union_features_over_90pct": int((df_union > 0.90).sum()),
        "mean_note_l0_union": float(l0_union.mean()),
        "auto_name_caveat": (
            "auto-explanations are hypotheses; 4932 'drug usage' fires on "
            "' session'/' repo'/' skill' in a coding note"
        ),
        "top": [
            {
                "index": int(i),
                "df_mass": round(float(df_mass[i]), 4),
                "df_union": round(float(df_union[i]), 4),
                "mean_sum": round(float(S[:, i].mean()), 1),
                "name": named.get(int(i), "(unfetched)"),
            }
            for i in order
        ],
    }
    (OUTDIR / "cone-features.json").write_text(json.dumps(cone, indent=1))

    fig, top = figure(
        16.5,
        6.6,
        1,
        "sae fingerprints",
        "Presence must mean mass: union ticking saturates, top-K does not",
        f"{n} notes x 16384 features  ·  union presence: any token activation "
        f"(mean per-note L0 {l0_union.mean():.0f})  ·  mass presence: note's top-{TOP_K} by sum",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1, 1.3], left=0.055, right=1 - MARGIN - 0.015, top=top, bottom=0.21
    )
    ax = fig.add_subplot(gs[0])
    ax.hist(l0_union, bins=40, color=GOLD, alpha=0.85)
    style_axes(ax)
    ax.set_xlabel("distinct features with any activation, per note")
    ax.set_ylabel("notes")
    panel_title(ax, "union presence: a third of the dictionary per note", width=48)

    ax = fig.add_subplot(gs[1])
    ranks = np.arange(1, len(df_union) + 1)
    ax.plot(ranks, np.sort(df_union)[::-1], color=GOLD, linewidth=1.8, label="union presence")
    ax.plot(ranks, np.sort(df_mass)[::-1], color=CYAN, linewidth=1.8, label=f"top-{TOP_K} presence")
    ax.axhline(0.90, color=RED, linewidth=1.0, linestyle="--", label="90% (cone threshold)")
    ax.set_xscale("log")
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="lower left")
    for t in leg.get_texts():
        t.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("features ranked by ubiquity (log)")
    ax.set_ylabel("share of notes where present")
    panel_title(
        ax,
        f"union: {int((df_union > 0.9).sum())} above 90%  ·  mass: {len(over90)} above 90%",
        width=56,
    )
    fig.text(
        MARGIN,
        0.05,
        f"Registered: >= 5 features above 90% df with register/domain names; kill below 70%. "
        f"Under mass presence: {len(over90)} above 90%, {len(over70)} above 70%. "
        "Union presence saturates and is reported only as the cautionary curve.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "01-fingerprint-stats.png")

    fig, top = figure(
        16.5,
        7.6,
        2,
        "sae fingerprints",
        "The cone, named — with the auto-name caveat attached",
        f"presence = note's top-{TOP_K} features by mass  ·  gold = the {len(order)} heaviest "
        "cone candidates, numbered  ·  names are Neuronpedia auto-explanations: hypotheses, "
        "not ground truth",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1.35, 1], left=0.055, right=1 - MARGIN - 0.01, top=top, bottom=0.17
    )
    ax = fig.add_subplot(gs[0])
    ax.scatter(df_mass, S.mean(axis=0), s=7, c=MUTED, alpha=0.3, linewidths=0)
    for rank, t in enumerate(cone["top"], 1):
        ax.scatter([t["df_mass"]], [t["mean_sum"]], s=34, c=GOLD, zorder=5, linewidths=0)
        ax.annotate(
            str(rank),
            (t["df_mass"], t["mean_sum"]),
            textcoords="offset points",
            xytext=(4, 4),
            color=GOLD,
            fontsize=7.5,
        )
    ax.axvline(0.90, color=RED, linewidth=1.0, linestyle="--")
    style_axes(ax)
    ax.set_yscale("log")
    ax.set_xlabel(f"document frequency (top-{TOP_K} presence)")
    ax.set_ylabel("mean summed activation (log)")
    panel_title(ax, "ubiquity vs mass", width=40)

    ax = fig.add_subplot(gs[1])
    ax.axis("off")
    lines = [
        f"{rank:>2}. #{t['index']:<6} df {t['df_mass']:.2f}   {t['name'][:52]}"
        for rank, t in enumerate(cone["top"], 1)
    ]
    ax.text(
        0.0,
        1.0,
        "\n".join(lines),
        va="top",
        color=MUTED,
        fontsize=8.0,
        family="monospace",
        linespacing=1.55,
    )
    panel_title(ax, "the heaviest cone candidates", width=44)
    save(fig, "02-cone-features.png")

    print(
        f"\nmass presence: {len(over90)} features > 90% df, {len(over70)} > 70%  "
        f"(union: {int((df_union > 0.9).sum())} > 90%)"
    )
    for rank, t in enumerate(cone["top"][:12], 1):
        print(
            f"  {rank:>2}. df {t['df_mass']:.2f}  mass {t['mean_sum']:8.1f}  #{t['index']:>6} {t['name'][:64]}"
        )


if __name__ == "__main__":
    main()
