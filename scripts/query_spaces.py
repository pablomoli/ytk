#!/usr/bin/env python
"""20.1 + 20.4 — the highway and the missing-bridges list (pre-registered).

20.1: tag-centroid road between the two strongest genuinely distinct
interests. Endpoint rule fixed in the registration: A = most coherent tag
by fresh z; B = next most coherent with centroid cosine below the median
of the 45 large-tag pairs (0.9161). Nine stops, top-3 notes each, feature
lanes from tag mean fingerprints.

20.4: midpoint support for all note pairs (t=0.5 slerp = normalized chord),
aggregated to the 45 large-tag pairs — weak bridges between individually
coherent tags are named acquisition targets.

    uv run --with matplotlib python scripts/query_spaces.py

Inherits: cosine retrieval (19.1 verdict), sum pooling, mass presence,
auto-names as hypotheses.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from growth_experiments import slerp
from plot_assets import (
    BLUE,
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

ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"
OUTDIR = ASSETS / "20-query-spaces"
GROWTH = ASSETS / "17-corpus-growth"
SAE = ASSETS / "18-sae-fingerprints"
MODEL_ID = "gemma-2-2b"
LAYER = "20-gemmascope-res-16k"
SEED = 20260808
STOPS = np.linspace(0.0, 1.0, 9)
TOP_RETRIEVED = 3
TOP_K = 256
COS_THRESHOLD = 0.9161  # median of the 45 large-tag pairs, per registration
LANES_SIDE = 6
LANES_SHARED = 4
N_TAGS = 10
MIN_Z = 2.0


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out.relative_to(ASSETS.parent.parent)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def unit(M: np.ndarray) -> np.ndarray:
    return M / (np.linalg.norm(M, axis=-1, keepdims=True) + 1e-12)


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
    X = unit(np.load(GROWTH / "vectors-fresh.npz")["X"].astype(np.float32))
    meta = json.loads((GROWTH / "tags-fresh.json").read_text())
    labels, names = meta["labels"], meta["names"]
    n = len(X)
    S = np.load(SAE / "fingerprints.npz")["sum"].astype(np.float32)
    F = S / (S.sum(axis=1, keepdims=True) + 1e-9)
    zfresh = json.loads((GROWTH / "results.json").read_text())["e3_tag_z"]["fresh"]
    background = float((X @ X.T)[np.triu_indices(n, 1)].mean())

    def tag_idx(tag: str) -> list[int]:
        return [i for i, ls in enumerate(labels) if tag in ls]

    def centroid(tag: str) -> np.ndarray:
        return unit(X[tag_idx(tag)].mean(axis=0))

    # ---- endpoint rule (registered): most coherent, then first distinct
    by_z = sorted(zfresh.items(), key=lambda kv: -kv[1]["z"])
    tag_a = by_z[0][0]
    ca = centroid(tag_a)
    tag_b = None
    for t, _ in by_z[1:]:
        if float(centroid(t) @ ca) < COS_THRESHOLD:
            tag_b = t
            break
    assert tag_b is not None
    cb = centroid(tag_b)
    print(
        f"highway: {tag_a} (z {zfresh[tag_a]['z']:.1f}) -> {tag_b} (z {zfresh[tag_b]['z']:.1f})  cos {float(ca @ cb):.3f}"
    )

    # ---- 20.1 highway
    fa = unit(F[tag_idx(tag_a)].mean(axis=0)[None, :])[0]
    fb = unit(F[tag_idx(tag_b)].mean(axis=0)[None, :])[0]
    a_set = set(np.argsort(-fa)[:TOP_K].tolist())
    b_set = set(np.argsort(-fb)[:TOP_K].tolist())
    a_only = np.array(sorted(a_set - b_set))
    b_only = np.array(sorted(b_set - a_set))
    shared = np.array(sorted(a_set & b_set))

    a_ids, b_ids = set(tag_idx(tag_a)), set(tag_idx(tag_b))
    stops, a_shares, supports, bridges = [], [], [], []
    for t in STOPS:
        v = slerp(ca, cb, float(t))
        sims = X @ v
        top = np.argsort(-sims)[:TOP_RETRIEVED]
        supports.append(float(sims[top[0]]))
        w = sims[top] / sims[top].sum()
        blend = (F[top] * w[:, None]).sum(axis=0)
        ma, mb = float(blend[a_only].sum()), float(blend[b_only].sum())
        a_shares.append(ma / (ma + mb + 1e-12))
        is_bridge = top[0] not in a_ids and top[0] not in b_ids
        bridges.append(bool(is_bridge))
        stops.append(
            {
                "t": round(float(t), 3),
                "support": round(float(sims[top[0]]), 4),
                "retrieved": [names[k][:56] for k in top],
                "top_is_bridge": bool(is_bridge),
                "blend": blend,
            }
        )
    a_shares = np.array(a_shares)
    rho = spearman(a_shares, STOPS)
    rng = np.random.default_rng(SEED)
    null_p95 = float(
        np.percentile([abs(spearman(rng.permutation(a_shares), STOPS)) for _ in range(200)], 95)
    )
    verdicts = {
        "support_above_background": bool(min(supports) >= background),
        "min_support": round(min(supports), 4),
        "background": round(background, 4),
        "rho": round(rho, 3),
        "null_abs_rho_p95": round(null_p95, 3),
        "any_bridge_stop": bool(any(bridges)),
        "n_bridge_stops": int(sum(bridges)),
    }
    print("20.1 verdicts:", verdicts)

    lane_a = sorted(a_only, key=lambda f: -float(fa[f]))[:LANES_SIDE]
    lane_s = sorted(shared, key=lambda f: -float(min(fa[f], fb[f])))[:LANES_SHARED]
    lane_b = sorted(b_only, key=lambda f: -float(fb[f]))[:LANES_SIDE]
    lanes = (
        [(int(f), "A") for f in lane_a]
        + [(int(f), "shared") for f in lane_s]
        + [(int(f), "B") for f in lane_b]
    )
    named = fetch_names([f for f, _ in lanes])

    # ---- 20.4 missing bridges: all-pairs midpoint support (t=0.5 => unit chord)
    print("computing all-pairs midpoint support ...")
    iu, ju = np.triu_indices(n, k=1)
    sup_mid = np.empty(len(iu), dtype=np.float32)
    for s0 in range(0, len(iu), 4096):
        sl = slice(s0, min(s0 + 4096, len(iu)))
        M = unit(X[iu[sl]] + X[ju[sl]])
        sims = M @ X.T
        sims[np.arange(sims.shape[0]), iu[sl]] = -np.inf
        sims[np.arange(sims.shape[0]), ju[sl]] = -np.inf
        sup_mid[sl] = sims.max(axis=1)
    all_median = float(np.median(sup_mid))

    counts = Counter(t for ls in labels for t in ls)
    big = [t for t, _ in counts.most_common(N_TAGS)]
    membership = {t: np.zeros(n, dtype=bool) for t in big}
    for t in big:
        membership[t][tag_idx(t)] = True
    pair_lookup = {}
    for k, (i, j) in enumerate(zip(iu, ju)):
        pair_lookup.setdefault(int(i), []).append(k)
    rows = []
    for a in range(len(big)):
        for b in range(a + 1, len(big)):
            ta, tb = big[a], big[b]
            mask = (membership[ta][iu] & membership[tb][ju]) | (
                membership[tb][iu] & membership[ta][ju]
            )
            if not mask.any():
                continue
            ends_cos = float(centroid(ta) @ centroid(tb))
            rows.append(
                {
                    "a": ta,
                    "b": tb,
                    "n_pairs": int(mask.sum()),
                    "mean_mid_support": round(float(sup_mid[mask].mean()), 4),
                    "centroid_cos": round(ends_cos, 4),
                    "both_coherent": bool(
                        zfresh.get(ta, {}).get("z", 0) > MIN_Z
                        and zfresh.get(tb, {}).get("z", 0) > MIN_Z
                    ),
                }
            )
    rows.sort(key=lambda r: r["mean_mid_support"])
    weak = [r for r in rows if r["both_coherent"] and r["mean_mid_support"] < all_median]
    print(
        f"20.4: all-pairs median {all_median:.4f}; weak coherent bridges: {len(weak)} (registered >= 2)"
    )
    for r in weak[:6]:
        print(
            f"  {r['a']} + {r['b']}  support {r['mean_mid_support']:.3f}  cos {r['centroid_cos']:.3f}"
        )

    out = {
        "seed": SEED,
        "highway": {
            "a": tag_a,
            "b": tag_b,
            "centroid_cos": round(float(ca @ cb), 4),
            "verdicts": verdicts,
            "stops": [{k: v for k, v in s.items() if k != "blend"} for s in stops],
            "lanes": [{"index": f, "side": side, "name": named.get(f, "")} for f, side in lanes],
        },
        "bridges": {
            "all_pairs_median": all_median,
            "tag_pairs": rows,
            "weak_coherent": [dict(r) for r in weak],
        },
    }
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "results.json").write_text(json.dumps(out, indent=1))

    # ---- figure 01: the highway
    fig, top_ = figure(
        16.5,
        9.6,
        1,
        "query spaces",
        f"The highway: {tag_a} to {tag_b}",
        f"tag-centroid slerp, 9 stops, top-{TOP_RETRIEVED} notes per stop  ·  centroid cos "
        f"{float(ca @ cb):.2f}  ·  rho = {rho:.2f} (registered <= -0.8, chance p95 {null_p95:.2f})"
        f"  ·  min stop support {min(supports):.2f} vs background {background:.2f}",
    )
    gs = fig.add_gridspec(
        2,
        1,
        height_ratios=[1, 2.1],
        left=0.30,
        right=1 - MARGIN - 0.015,
        top=top_,
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
        label=f"{tag_a}-side share",
    )
    ax.plot(
        STOPS, 1 - a_shares, color=BLUE, linewidth=1.6, linestyle="--", label=f"{tag_b}-side share"
    )
    for t, br in zip(STOPS, bridges):
        if br:
            ax.axvline(t, color=CYAN, linewidth=0.9, alpha=0.5)
    ax.axhline(0.5, color=MUTED, linewidth=0.8, linestyle=":", alpha=0.6)
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="center right")
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_ylim(0, 1)
    ax.set_ylabel("share of exclusive mass")
    panel_title(ax, "vocabulary handover (cyan verticals: bridge stops)", width=52)

    ax = fig.add_subplot(gs[1])
    colors = {"A": GOLD, "shared": CYAN, "B": BLUE}
    n_lanes = len(lanes)
    for li, (f, side) in enumerate(lanes):
        y0 = n_lanes - 1 - li
        vals = np.array([s["blend"][f] for s in stops], dtype=float)
        scaled = 0.82 * vals / (vals.max() + 1e-12)
        ax.fill_between(STOPS, y0, y0 + scaled, color=colors[side], alpha=0.75, linewidth=0)
        ax.plot(STOPS, y0 + scaled, color=colors[side], linewidth=1.0, alpha=0.9)
        ax.text(
            -0.015,
            y0 + 0.28,
            f"#{f} {named.get(f, '')[:44]}",
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
    ax.set_xlabel(f"position along the highway ({tag_a} -> {tag_b})")
    panel_title(ax, "feature lanes between the two interest vocabularies", width=64)
    save(fig, "01-highway.png")

    # ---- figure 02: missing bridges
    fig, top_ = figure(
        16.5,
        7.2,
        2,
        "query spaces",
        "The missing-bridges list: weak crossings between real interests",
        f"45 large-tag pairs, mean midpoint support over all cross-tag note pairs  ·  all-pairs "
        f"median {all_median:.3f}  ·  weak coherent bridges found: {len(weak)} (registered >= 2)",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.35, 1],
        left=0.055,
        right=1 - MARGIN - 0.01,
        top=top_,
        bottom=0.19,
        wspace=0.24,
    )
    ax = fig.add_subplot(gs[0])
    cx = [r["centroid_cos"] for r in rows]
    cy = [r["mean_mid_support"] for r in rows]
    cc = [GOLD if r["both_coherent"] else MUTED for r in rows]
    ax.scatter(cx, cy, s=30, c=cc, alpha=0.85, linewidths=0)
    ax.axhline(all_median, color=RED, linewidth=1.0, linestyle="--")
    ax.text(min(cx), all_median + 0.003, "all-pairs median", color=RED, fontsize=TICK_SIZE)
    for r in weak[:5]:
        ax.annotate(
            f"{r['a']} + {r['b']}",
            (r["centroid_cos"], r["mean_mid_support"]),
            textcoords="offset points",
            xytext=(7, -9),
            color=CYAN,
            fontsize=7.6,
        )
    style_axes(ax)
    ax.set_xlabel("endpoint centroid cosine")
    ax.set_ylabel("mean midpoint support")
    panel_title(ax, "gold = both tags coherent; weak bridges labeled", width=52)

    ax = fig.add_subplot(gs[1])
    ax.axis("off")
    lines = ["weakest crossings (acquisition targets):", ""]
    for r in rows[:12]:
        flag = "*" if r["both_coherent"] and r["mean_mid_support"] < all_median else " "
        lines.append(
            f"{flag} {r['a'][:14]:14s}+ {r['b'][:14]:14s} {r['mean_mid_support']:.3f}  ({r['n_pairs']} pairs)"
        )
    lines += ["", "* = weak bridge between coherent interests"]
    ax.text(
        0.0,
        1.0,
        "\n".join(lines),
        va="top",
        color=MUTED,
        fontsize=8.2,
        family="monospace",
        linespacing=1.6,
    )
    panel_title(ax, "ranked by bridge weakness", width=44)
    save(fig, "02-missing-bridges.png")


if __name__ == "__main__":
    main()
