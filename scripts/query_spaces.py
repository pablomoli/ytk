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
    DIM,
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
    # anchor the axis on the corpus background: auto-scale zoomed into the
    # 0.556-0.631 band and made a 0.075-wide spread fill the panel
    ax.axhline(background, color=DIM, linewidth=1.2)
    ax.text(
        max(cx),
        background + 0.003,
        f"background pair cosine {background:.3f}",
        color=MUTED,
        fontsize=TICK_SIZE,
        ha="right",
    )
    ax.set_ylim(background - 0.015, max(cy) + 0.015)
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


def blends_and_extrapolation() -> None:
    """20.2 barycentric blends + 20.3 extrapolation (registered)."""
    X = unit(np.load(GROWTH / "vectors-fresh.npz")["X"].astype(np.float32))
    meta = json.loads((GROWTH / "tags-fresh.json").read_text())
    labels, names = meta["labels"], meta["names"]
    n = len(X)
    background = float((X @ X.T)[np.triu_indices(n, 1)].mean())
    rng = np.random.default_rng(SEED + 1)
    counts = Counter(t for ls in labels for t in ls)
    big = [t for t, _ in counts.most_common(N_TAGS)]
    by_tag = {t: [i for i, ls in enumerate(labels) if t in ls] for t in big}

    def top_excluding(v: np.ndarray, excl: set[int]) -> int:
        sims = X @ v
        for e in excl:
            sims[e] = -np.inf
        return int(sims.argmax())

    # ---- 20.2 barycentric novelty, real triples vs degenerate control
    def novelty(triples: list[tuple[int, int, int]]) -> list[bool]:
        out = []
        for a, b, c in triples:
            excl = {a, b, c}
            bary = top_excluding(unit(X[a] + X[b] + X[c]), excl)
            mids = {
                top_excluding(unit(X[a] + X[b]), excl),
                top_excluding(unit(X[b] + X[c]), excl),
                top_excluding(unit(X[a] + X[c]), excl),
            }
            out.append(bary not in mids)
        return out

    real_triples = []
    for _ in range(10):
        ta, tb, tc = rng.choice(len(big), size=3, replace=False)
        real_triples.append(
            (
                int(rng.choice(by_tag[big[ta]])),
                int(rng.choice(by_tag[big[tb]])),
                int(rng.choice(by_tag[big[tc]])),
            )
        )
    cos_full = X @ X.T
    np.fill_diagonal(cos_full, -np.inf)
    degen_triples = []
    for _ in range(10):
        a = int(rng.integers(0, n))
        nnb = np.argsort(-cos_full[a])[:2]
        degen_triples.append((a, int(nnb[0]), int(nnb[1])))
    nov_real = novelty(real_triples)
    nov_degen = novelty(degen_triples)
    print(
        f"20.2 barycentric novelty: real {sum(nov_real)}/10 (registered >= 3)  ·  "
        f"degenerate control {sum(nov_degen)}/10 (expected ~0)"
    )

    # ---- 20.3 extrapolation past B on the census pairs
    S_cos = cos_full.copy()
    nn_idx = S_cos.argmax(axis=1)
    pairs_nn = sorted({(min(i, int(j)), max(i, int(j))) for i, j in enumerate(nn_idx)})
    crng = np.random.default_rng(20260804)
    pairs_rand: set[tuple[int, int]] = set()
    while len(pairs_rand) < 500:
        a, b = (int(v) for v in crng.integers(0, n, 2))
        if a != b and (min(a, b), max(a, b)) not in pairs_nn:
            pairs_rand.add((min(a, b), max(a, b)))
    all_pairs = pairs_nn + sorted(pairs_rand)
    ts_ext = [1.0, 1.1, 1.25, 1.5, 1.75]
    # operationalization chosen at run time (registered wording said only
    # "support stays above background through t = 1.5"): judged on the 5th
    # percentile across all census pairs — 95% of walks must stay above.
    quant = {}
    for t in ts_ext:
        sups = []
        for i, j in all_pairs:
            v = slerp(X[i], X[j], float(t))
            sims = X @ v
            sims[[i, j]] = -np.inf
            sups.append(float(sims.max()))
        sups = np.array(sups)
        quant[t] = {
            "median": float(np.median(sups)),
            "p5": float(np.percentile(sups, 5)),
            "frac_above_bg": float((sups > background).mean()),
        }
        print(
            f"  t={t:.2f}  median {quant[t]['median']:.3f}  p5 {quant[t]['p5']:.3f}  "
            f"above-bg {quant[t]['frac_above_bg']:.1%}"
        )
    confirmed = quant[1.5]["p5"] > background
    print(
        f"20.3 verdict at t=1.5: p5 {quant[1.5]['p5']:.3f} vs background {background:.3f} -> "
        f"{'CONFIRMED' if confirmed else 'FAILED'}"
    )

    prev = json.loads((OUTDIR / "results.json").read_text())
    prev["barycentric"] = {
        "real_novel": int(sum(nov_real)),
        "degenerate_novel": int(sum(nov_degen)),
        "triples": [
            {"notes": [names[k][:40] for k in tr], "novel": bool(nv)}
            for tr, nv in zip(real_triples, nov_real)
        ],
    }
    prev["extrapolation"] = {
        "background": background,
        "operationalization": "p5 across census pairs must exceed background",
        "quantiles": {str(t): q for t, q in quant.items()},
        "confirmed_at_1_5": bool(confirmed),
    }
    (OUTDIR / "results.json").write_text(json.dumps(prev, indent=1))

    fig, top_ = figure(
        16.5,
        6.8,
        3,
        "query spaces",
        "Blends that pairwise roads cannot ask, and the road past the end",
        "left: barycenter of 3 cross-tag notes vs its three pairwise midpoints, 10 seeded "
        "triples + degenerate control  ·  right: support extrapolating past B on the 957 "
        "census arcs  ·  registered: novelty >= 3/10; p5 above background through t = 1.5",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1, 1.5],
        left=0.07,
        right=1 - MARGIN - 0.015,
        top=top_,
        bottom=0.21,
        wspace=0.30,
    )
    ax = fig.add_subplot(gs[0])
    bars = ax.bar(
        [0, 1],
        [sum(nov_real), sum(nov_degen)],
        color=[GOLD, MUTED],
        width=0.55,
    )
    for b, v in zip(bars, [sum(nov_real), sum(nov_degen)]):
        ax.text(
            b.get_x() + b.get_width() / 2, v + 0.15, str(v), ha="center", color=MUTED, fontsize=10
        )
    ax.axhline(3, color=RED, linewidth=1.0, linestyle="--", label="registered threshold")
    ax.set_xticks([0, 1], ["cross-tag triples", "degenerate control"], fontsize=9)
    ax.set_ylim(0, 10.5)
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="upper right")
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_ylabel("triples where the barycenter finds a new note (of 10)")
    panel_title(ax, "does a 3-blend ask anything new?", width=44)

    ax = fig.add_subplot(gs[1])
    med = [quant[t]["median"] for t in ts_ext]
    p5 = [quant[t]["p5"] for t in ts_ext]
    ax.plot(
        ts_ext, med, color=GOLD, linewidth=2.0, marker="o", markersize=5, label="median support"
    )
    ax.plot(ts_ext, p5, color=BLUE, linewidth=1.6, marker="o", markersize=4, label="5th percentile")
    ax.axhline(background, color=RED, linewidth=1.1, linestyle="--", label="corpus background")
    ax.axvline(1.5, color=MUTED, linewidth=0.9, linestyle=":", alpha=0.7)
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="upper right")
    for t_ in leg.get_texts():
        t_.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("t along the arc (1.0 = endpoint B; beyond is 'more B, away from A')")
    ax.set_ylabel("support of nearest real note")
    panel_title(ax, "past the end of the road", width=44)
    save(fig, "03-blends-extrapolation.png")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "blends":
        blends_and_extrapolation()
    else:
        main()
