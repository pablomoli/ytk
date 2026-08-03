#!/usr/bin/env python
"""18.5 — roads as feature diffs (pre-registered).

The E6 road (coding-interview video -> instagram brain heatmap), re-read in
feature space: at each slerp stop, retrieve the top-3 real notes in Qwen
space (endpoints and their content-duplicates excluded), blend their
normalized fingerprints by retrieval weight, and track how mass moves
between the endpoints' feature vocabularies.

Registered: A-side share decreases monotonically in t (Spearman rho <=
-0.8); fading-out / persistent / fading-in sets all non-empty with
readable names. Control: shuffled stop order shows no monotone turnover.
Kill: no monotone structure -> roads keep LLM narration, feature readout
dropped, reported honestly.

    uv run --with matplotlib python scripts/sae_road.py
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
from growth_experiments import PAIR_A, PAIR_B_UNRELATED, slerp
from plot_assets import (
    BLUE,
    CYAN,
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "18-sae-fingerprints"
GROWTH = OUTDIR.parent / "17-corpus-growth"
MODEL_ID = "gemma-2-2b"
LAYER = "20-gemmascope-res-16k"
STOPS = np.linspace(0.0, 1.0, 9)
TOP_RETRIEVED = 3
TOP_K = 256  # endpoint vocabulary size, matching the 18.3 mass-presence rule
SEED = 20260806
SHUFFLES = 200
LANES_SIDE = 6
LANES_SHARED = 4
# content-identity exclusion (the E6 lesson): endpoint B exists twice under
# different filenames; row-index exclusion alone re-retrieves the duplicate
DUP_MARKERS = ("DWpSK4uDhIO",)


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
        out[int(f["index"])] = exps[0].get("description", "(none)") if exps else "(none)"
    return out


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    return float((ra @ rb) / (np.linalg.norm(ra) * np.linalg.norm(rb) + 1e-12))


def main() -> None:
    S = np.load(OUTDIR / "fingerprints.npz")["sum"].astype(np.float32)
    F = S / (S.sum(axis=1, keepdims=True) + 1e-9)
    meta = json.loads((GROWTH / "tags-fresh.json").read_text())
    names = meta["names"]
    X = np.load(GROWTH / "vectors-fresh.npz")["X"].astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-12

    i, j = names.index(PAIR_A), names.index(PAIR_B_UNRELATED)
    excluded = {i, j} | {k for k, nm in enumerate(names) if any(m in nm for m in DUP_MARKERS)}

    # endpoint vocabularies under the mass-presence rule
    a_set = set(np.argsort(-F[i])[:TOP_K].tolist())
    b_set = set(np.argsort(-F[j])[:TOP_K].tolist())
    a_only = np.array(sorted(a_set - b_set))
    b_only = np.array(sorted(b_set - a_set))
    shared = np.array(sorted(a_set & b_set))

    stops = []
    a_shares = []
    for t in STOPS:
        v = slerp(X[i], X[j], float(t))
        sims = X @ v
        for e in excluded:
            sims[e] = -1
        top = np.argsort(-sims)[:TOP_RETRIEVED]
        w = sims[top] / sims[top].sum()
        blend = (F[top] * w[:, None]).sum(axis=0)
        mass_a = float(blend[a_only].sum())
        mass_b = float(blend[b_only].sum())
        a_share = mass_a / (mass_a + mass_b + 1e-12)
        a_shares.append(a_share)
        stops.append(
            {
                "t": round(float(t), 3),
                "retrieved": [names[k][:60] for k in top],
                "weights": [round(float(x), 3) for x in w],
                "a_share": round(a_share, 4),
                "blend": blend,
            }
        )

    a_shares = np.array(a_shares)
    rho = spearman(a_shares, STOPS)
    rng = np.random.default_rng(SEED)
    null_rhos = [abs(spearman(rng.permutation(a_shares), STOPS)) for _ in range(SHUFFLES)]
    null_p95 = float(np.percentile(null_rhos, 95))

    # lanes: heaviest endpoint-exclusive and shared features, mass along t
    lane_a = sorted(a_only, key=lambda f: -float(F[i, f]))[:LANES_SIDE]
    lane_b = sorted(b_only, key=lambda f: -float(F[j, f]))[:LANES_SIDE]
    lane_s = sorted(shared, key=lambda f: -float(min(F[i, f], F[j, f])))[:LANES_SHARED]
    lanes = (
        [(int(f), "A") for f in lane_a]
        + [(int(f), "shared") for f in lane_s]
        + [(int(f), "B") for f in lane_b]
    )
    named = fetch_names([f for f, _ in lanes])

    out = {
        "seed": SEED,
        "pair": {"a": names[i].strip(), "b": names[j].strip()},
        "excluded_rows": len(excluded),
        "vocab": {"a_only": len(a_only), "b_only": len(b_only), "shared": len(shared)},
        "a_share_by_stop": [round(float(v), 4) for v in a_shares],
        "spearman_rho": round(rho, 3),
        "null_abs_rho_p95": round(null_p95, 3),
        "stops": [{k: v for k, v in s.items() if k != "blend"} for s in stops],
        "lanes": [
            {"index": f, "side": side, "name": named.get(f, "(unfetched)")} for f, side in lanes
        ],
    }
    (OUTDIR / "road-diffs.json").write_text(json.dumps(out, indent=1))

    # ---- figure: turnover curve + feature lanes
    fig, top = figure(
        16.5,
        9.6,
        5,
        "sae fingerprints",
        "A road, read as feature turnover",
        f"the E6 walk, 9 stops, top-{TOP_RETRIEVED} retrieved notes per stop (endpoints and "
        f"content-duplicates excluded)  ·  A/B vocabularies = endpoint top-{TOP_K} features  ·  "
        f"Spearman rho = {rho:.2f} (registered <= -0.8; |rho| chance p95 = {null_p95:.2f})",
    )
    gs = fig.add_gridspec(
        2,
        1,
        height_ratios=[1, 2.1],
        left=0.30,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.09,
        hspace=0.34,
    )

    ax = fig.add_subplot(gs[0])
    ax.plot(
        STOPS,
        a_shares,
        color=GOLD,
        linewidth=2.2,
        marker="o",
        markersize=5,
        label="A-side share of exclusive mass",
    )
    ax.plot(STOPS, 1 - a_shares, color=BLUE, linewidth=1.6, linestyle="--", label="B-side share")
    ax.axhline(0.5, color=MUTED, linewidth=0.8, linestyle=":", alpha=0.6)
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="center right")
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_ylim(0, 1)
    ax.set_ylabel("share of endpoint-exclusive mass")
    panel_title(ax, "who owns each stop", width=40)

    ax = fig.add_subplot(gs[1])
    n_lanes = len(lanes)
    colors = {"A": GOLD, "shared": CYAN, "B": BLUE}
    for li, (f, side) in enumerate(lanes):
        y0 = n_lanes - 1 - li
        vals = np.array([s["blend"][f] for s in stops], dtype=float)
        vmax = vals.max() + 1e-12
        scaled = 0.82 * vals / vmax
        ax.fill_between(STOPS, y0, y0 + scaled, color=colors[side], alpha=0.75, linewidth=0)
        ax.plot(STOPS, y0 + scaled, color=colors[side], linewidth=1.0, alpha=0.9)
        label = f"#{f} {named.get(f, '')[:44]}"
        ax.text(
            -0.015,
            y0 + 0.28,
            label,
            ha="right",
            va="center",
            color=MUTED,
            fontsize=7.0,
            transform=ax.get_yaxis_transform(),
        )
    ax.set_yticks([])
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.3, n_lanes)
    style_axes(ax)
    ax.set_xlabel("position along the walk (A -> B)")
    panel_title(
        ax,
        f"feature lanes: {LANES_SIDE} A-exclusive (gold), {LANES_SHARED} shared (cyan), "
        f"{LANES_SIDE} B-exclusive (blue), each scaled to its own max",
        width=90,
    )
    import textwrap

    fig.text(
        MARGIN,
        0.035,
        textwrap.fill(
            "Every lane is one named feature; its height is the mass that feature carries in the "
            "blended fingerprint of the notes retrieved at each stop. A readable road shows gold "
            "draining left-to-right, blue filling, cyan persisting — the registered rho quantifies "
            "the drain. Auto-names are hypotheses; the lanes are read as a set.",
            132,
        ),
        color=MUTED,
        fontsize=9.5,
    )
    frame_panels(fig)
    out_path = OUTDIR / "05-road-diffs.png"
    fig.savefig(out_path, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out_path.relative_to(OUTDIR.parents[2])}  ({out_path.stat().st_size // 1024}KB)")
    plt.close(fig)

    print(f"\nrho = {rho:.3f} (registered <= -0.8; chance |rho| p95 = {null_p95:.2f})")
    print(f"vocab: {len(a_only)} A-only, {len(shared)} shared, {len(b_only)} B-only")
    for s in stops:
        print(f"  t={s['t']:.2f}  A-share {s['a_share']:.2f}  {s['retrieved'][0][:52]}")


if __name__ == "__main__":
    main()
