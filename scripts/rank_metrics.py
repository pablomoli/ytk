#!/usr/bin/env python
"""Section 19 Phase A + 18.4b — rank metrics offline, and the continuous
cross-space measure (both pre-registered in 18-sae-fingerprints/preregistration.md).

Six similarity metrics over the fresh Qwen snapshot, judged on three tasks
with built-in ground truth. Strictly read-only; production search is
untouched (Phase B goes through the retrieval eval gate or not at all).

    19.1 tag-match@10: do a note's top-10 neighbors share a tag more often?
         Registered: Spearman and L1 beat raw cosine by >= 2 points
         absolute; after centring the rank-vs-cosine gap shrinks below 1.
    19.2 hub flattening: CSLS(k=10) cuts the census top-10 answerer share
         by >= 1/3 while median path min-support shifts < 0.01.
    19.3 duplicate detection: the known duplicate pair ranks strictly
         higher relative to ordinary neighbors under CSLS than cosine.
    18.4b continuous cross-space agreement: cosine of per-tag differential
         z-vectors (SAE) vs Qwen centroid cosine, r >= 0.4, shuffle -> ~0.

    uv run --with matplotlib python scripts/rank_metrics.py

Spearman is implemented as its identity: cosine over per-vector
rank-transformed, standardized rows — which is also the production unlock
(a rank-transformed parallel collection makes HNSW serve Spearman as-is).
"""

from __future__ import annotations

import json
import sys
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
OUTDIR = ASSETS / "19-rank-metrics"
GROWTH = ASSETS / "17-corpus-growth"
SAE = ASSETS / "18-sae-fingerprints"
SEED = 20260807
K_MATCH = 10
CSLS_K = 10
DUP_A = "randyroberts-DWpSK4uDhIO-tribe-brain-heatmap"
DUP_B = "rndyrbrts-2026-04-02-DWpSK4uDhIO"
PATH_STEPS_INTERIOR = 39  # matches the census


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out.relative_to(ASSETS.parent.parent)}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def unit(M: np.ndarray) -> np.ndarray:
    return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)


def rank_transform(X: np.ndarray) -> np.ndarray:
    R = np.argsort(np.argsort(X, axis=1), axis=1).astype(np.float32)
    R -= R.mean(axis=1, keepdims=True)
    return unit(R)


def sim_matrices(X: np.ndarray) -> dict[str, np.ndarray]:
    Xc = unit(X - X.mean(axis=0))
    R = rank_transform(X)
    Rc = rank_transform(X - X.mean(axis=0))
    cos = X @ X.T
    # L1: similarity = negative distance (dense pairwise, 568^2 x 1024 — fine)
    l1 = -np.abs(X[:, None, :] - X[None, :, :]).sum(axis=2)
    # CSLS over raw cosine
    tmp = cos.copy()
    np.fill_diagonal(tmp, -np.inf)
    knn_mean = np.sort(tmp, axis=1)[:, -CSLS_K:].mean(axis=1)
    csls = 2 * cos - knn_mean[:, None] - knn_mean[None, :]
    return {
        "cosine": cos,
        "cosine-centred": Xc @ Xc.T,
        "L1": l1,
        "spearman": R @ R.T,
        "spearman-centred": Rc @ Rc.T,
        "csls": csls,
    }


def tag_match(sims: np.ndarray, labels: list[list[str]], rng=None) -> float:
    S = sims.copy()
    np.fill_diagonal(S, -np.inf)
    nn = np.argsort(-S, axis=1)[:, :K_MATCH]
    sets = [set(ts) for ts in labels]
    if rng is not None:
        perm = rng.permutation(len(sets))
        sets = [sets[p] for p in perm]
    hits = [np.mean([bool(sets[i] & sets[j]) for j in nn[i]]) for i in range(len(sets))]
    return float(np.mean(hits))


def main() -> None:
    rng = np.random.default_rng(SEED)
    X = unit(np.load(GROWTH / "vectors-fresh.npz")["X"].astype(np.float32))
    meta = json.loads((GROWTH / "tags-fresh.json").read_text())
    labels, names = meta["labels"], meta["names"]
    n = len(X)

    print("building similarity matrices ...")
    sims = sim_matrices(X)

    # ---- 19.1 tag-match@10
    scores = {m: round(tag_match(s, labels) * 100, 2) for m, s in sims.items()}
    floor = round(
        float(np.mean([tag_match(sims["cosine"], labels, rng) for _ in range(5)])) * 100, 2
    )
    gap_raw = scores["spearman"] - scores["cosine"]
    gap_cen = scores["spearman-centred"] - scores["cosine-centred"]
    print("tag-match@10 (%):", scores, f"permuted floor {floor}")

    # ---- 19.2 hub flattening on the census pairs (same seed => same pairs)
    S_cos = sims["cosine"].copy()
    np.fill_diagonal(S_cos, -1.0)
    nn_idx = S_cos.argmax(axis=1)
    pairs_nn = sorted({(min(i, int(j)), max(i, int(j))) for i, j in enumerate(nn_idx)})
    crng = np.random.default_rng(20260804)  # census seed, reproduces its random pairs
    pairs_rand: set[tuple[int, int]] = set()
    while len(pairs_rand) < 500:
        a, b = (int(v) for v in crng.integers(0, n, 2))
        if a != b and (min(a, b), max(a, b)) not in pairs_nn:
            pairs_rand.add((min(a, b), max(a, b)))
    all_pairs = pairs_nn + sorted(pairs_rand)

    knn_pen = np.sort(np.where(np.eye(n, dtype=bool), -np.inf, sims["cosine"]), axis=1)[
        :, -CSLS_K:
    ].mean(axis=1)
    ts = np.linspace(0, 1, PATH_STEPS_INTERIOR + 2)[1:-1]

    def census_pass(use_csls: bool):
        hub: Counter[int] = Counter()
        mins = []
        for i, j in all_pairs:
            Q = np.stack([slerp(X[i], X[j], float(t)) for t in ts])
            sup = Q @ X.T
            sup[:, [i, j]] = -np.inf
            if use_csls:
                choice = (2 * sup - knn_pen[None, :]).argmax(axis=1)
            else:
                choice = sup.argmax(axis=1)
            vals = sup[np.arange(len(ts)), choice]  # support stays cosine for comparability
            mins.append(float(vals.min()))
            hub.update({int(c) for c in choice})
        counts = np.array([c for _, c in hub.most_common()], dtype=float)
        top10_share = float(counts[:10].sum() / counts.sum())
        return top10_share, np.array(mins), counts

    share_cos, mins_cos, counts_cos = census_pass(False)
    share_csls, mins_csls, counts_csls = census_pass(True)
    dmin = float(np.median(mins_csls) - np.median(mins_cos))
    print(
        f"hub top-10 share: cosine {share_cos:.3f} -> csls {share_csls:.3f} "
        f"(registered cut >= 1/3)  ·  median min-support shift {dmin:+.4f}"
    )

    # ---- 19.3 duplicate detection
    ia, ib = names.index(DUP_A), names.index(DUP_B)
    ranks = {}
    for mname in ("cosine", "csls", "spearman", "L1"):
        row = sims[mname][ia].copy()
        row[ia] = -np.inf
        order = np.argsort(-row)
        ranks[mname] = int(np.where(order == ib)[0][0]) + 1
    print("duplicate rank (1 = nearest):", ranks)

    # ---- 18.4b continuous cross-space agreement
    tr = json.loads((SAE / "tag-regions.json").read_text())
    tags = tr["tags"]
    F = np.load(SAE / "fingerprints.npz")["sum"].astype(np.float32)
    F = F / (F.sum(axis=1, keepdims=True) + 1e-9)
    corpus_mean = F.mean(axis=0)
    zrng = np.random.default_rng(tr["seed"])  # same null construction as 18.4
    null_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    zvecs = {}
    for tag in tags:
        idx = [i for i, ls in enumerate(labels) if tag in ls]
        k = len(idx)
        if k not in null_cache:
            draws = np.stack(
                [
                    F[zrng.choice(len(F), size=k, replace=False)].mean(axis=0) - corpus_mean
                    for _ in range(tr["null_draws"])
                ]
            )
            null_cache[k] = (draws.mean(axis=0), draws.std(axis=0) + 1e-12)
        mu0, sd0 = null_cache[k]
        zvecs[tag] = (F[idx].mean(axis=0) - corpus_mean - mu0) / sd0
    Z = unit(np.stack([zvecs[t] for t in tags]))
    cents = unit(
        np.stack([X[[i for i, ls in enumerate(labels) if t in ls]].mean(axis=0) for t in tags])
    )
    iu = np.triu_indices(len(tags), k=1)
    sae_sim = (Z @ Z.T)[iu]
    qwen_sim = (cents @ cents.T)[iu]
    r_cont = float(np.corrcoef(sae_sim, qwen_sim)[0, 1])
    # shuffle control: z-vectors under permuted labels
    r_null = []
    for _ in range(20):
        perm = zrng.permutation(len(labels))
        plabels = [labels[p] for p in perm]
        pz = []
        for tag in tags:
            idx = [i for i, ls in enumerate(plabels) if tag in ls]
            mu0, sd0 = null_cache[len(idx)]
            pz.append((F[idx].mean(axis=0) - corpus_mean - mu0) / sd0)
        PZ = unit(np.stack(pz))
        r_null.append(float(np.corrcoef((PZ @ PZ.T)[iu], qwen_sim)[0, 1]))
    print(
        f"18.4b continuous r = {r_cont:.3f} (registered >= 0.4; shuffled mean {np.mean(r_null):+.3f})"
    )

    out = {
        "seed": SEED,
        "tag_match_at_10_pct": scores,
        "permuted_floor_pct": floor,
        "gaps": {"raw_spearman_minus_cosine": round(gap_raw, 2), "centred": round(gap_cen, 2)},
        "hub": {
            "top10_share_cosine": round(share_cos, 4),
            "top10_share_csls": round(share_csls, 4),
            "median_min_support_shift": round(dmin, 4),
        },
        "duplicate_rank": ranks,
        "continuous_cross_space": {
            "r": round(r_cont, 3),
            "shuffled_mean_r": round(float(np.mean(r_null)), 3),
        },
    }
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "results.json").write_text(json.dumps(out, indent=1))

    # ---- figures
    fig, top = figure(
        16.5,
        6.8,
        1,
        "rank metrics",
        "Six metrics, one task with ground truth: do neighbors share your tags?",
        f"tag-match@{K_MATCH} over {n} notes  ·  permuted-tag floor {floor:.1f}%  ·  registered: "
        "Spearman and L1 beat cosine by >= 2 points raw; centring shrinks the gap below 1",
    )
    gs = fig.add_gridspec(1, 1, left=0.20, right=0.80, top=top, bottom=0.22)
    ax = fig.add_subplot(gs[0])
    order = ["cosine", "L1", "spearman", "csls", "cosine-centred", "spearman-centred"]
    vals = [scores[m] for m in order]
    colors = [GOLD if "centred" not in m else CYAN for m in order]
    bars = ax.bar(range(len(order)), vals, color=colors, alpha=0.9, width=0.62)
    for b, v in zip(bars, vals):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v + 0.3,
            f"{v:.1f}",
            ha="center",
            color=MUTED,
            fontsize=8.5,
        )
    ax.set_xticks(range(len(order)), order, fontsize=8.5)
    ax.text(
        0.99,
        0.04,
        f"permuted-tag floor: {floor:.1f}% — far below this window",
        ha="right",
        transform=ax.transAxes,
        color=RED,
        fontsize=TICK_SIZE,
    )
    style_axes(ax)
    ax.set_ylabel(f"% of top-{K_MATCH} neighbors sharing a tag")
    ax.set_ylim(min(vals) - 6, max(vals) + 3)
    panel_title(ax, "gold = raw space, cyan = centred", width=44)
    save(fig, "01-tag-match.png")

    fig, top = figure(
        16.5,
        6.8,
        2,
        "rank metrics",
        "CSLS and the busy junctions",
        f"the 957 census paths re-answered with CSLS(k={CSLS_K}) reranking  ·  registered: top-10 "
        "answerer share cut by a third, median min-support shift under 0.01",
    )
    gs = fig.add_gridspec(
        1, 2, left=0.055, right=1 - MARGIN - 0.015, top=top, bottom=0.22, wspace=0.28
    )
    ax = fig.add_subplot(gs[0])
    for counts, color, lab in ((counts_cos, GOLD, "cosine"), (counts_csls, BLUE, "csls")):
        share = np.cumsum(counts) / counts.sum()
        ax.plot(np.arange(1, len(counts) + 1), share, color=color, linewidth=2.0, label=lab)
    ax.set_xscale("log")
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="upper left")
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("notes ranked by paths served (log)")
    ax.set_ylabel("cumulative share of answers")
    panel_title(ax, f"top-10 share {share_cos:.0%} -> {share_csls:.0%}", width=44)
    ax = fig.add_subplot(gs[1])
    bins = np.linspace(0.25, 0.8, 45)
    ax.hist(
        mins_cos,
        bins=bins,
        density=True,
        histtype="step",
        linewidth=1.8,
        color=GOLD,
        label="cosine",
    )
    ax.hist(
        mins_csls,
        bins=bins,
        density=True,
        histtype="step",
        linewidth=1.8,
        color=BLUE,
        label="csls-chosen",
    )
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE)
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("path minimum support (cosine units)")
    ax.set_ylabel("density")
    panel_title(ax, f"median min-support shift {dmin:+.4f}", width=40)
    save(fig, "02-hub-flattening.png")

    fig, top = figure(
        16.5,
        6.6,
        3,
        "rank metrics",
        "A high correlation the shuffle control takes back",
        f"45 tag pairs  ·  x = Qwen centroid cosine, y = cosine of full differential-z vectors "
        f"(SAE space)  ·  r = {r_cont:.3f} clears the registered 0.4 — but shuffled labels "
        f"still give {np.mean(r_null):+.2f}: the agreement is corpus geometry, not tag structure",
    )
    gs = fig.add_gridspec(1, 1, left=0.30, right=0.70, top=top, bottom=0.20)
    ax = fig.add_subplot(gs[0])
    ax.scatter(qwen_sim, sae_sim, s=34, c=GOLD, alpha=0.85, linewidths=0)
    m, b = np.polyfit(qwen_sim, sae_sim, 1)
    xs = np.linspace(qwen_sim.min(), qwen_sim.max(), 20)
    ax.plot(xs, m * xs + b, color=BLUE, linewidth=1.4, linestyle="--", label="least squares")
    pair_names = [(tags[a], tags[b]) for a, b in zip(*iu)]
    top_ix = np.argsort(-(sae_sim + qwen_sim))[:4]
    for k in top_ix:
        ax.annotate(
            f"{pair_names[k][0]} + {pair_names[k][1]}",
            (qwen_sim[k], sae_sim[k]),
            textcoords="offset points",
            xytext=(7, 4),
            color=CYAN,
            fontsize=7.6,
        )
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="upper left")
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("tag centroid cosine (Qwen)")
    ax.set_ylabel("differential-z cosine (SAE)")
    panel_title(ax, "two encoders, shared scaffolding", width=40)
    save(fig, "03-continuous-overlap.png")


if __name__ == "__main__":
    main()
