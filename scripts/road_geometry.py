#!/usr/bin/env python
"""Section 21 — road-network geometry (pre-registered 2026-08-03).

21.1 constellation of centred tag centroids; 21.2 polytope probe on the 31
cone features' decoder directions and the centroids; 21.3 intersections
(road-degree + slerp-tangent crossing angles) over the 45 tag roads; 21.4
roundabouts (handover concentration); 21.5 the map.

    uv run --with sae-lens python scripts/road_geometry.py wdec   # once
    uv run --with matplotlib python scripts/road_geometry.py

Inherits: cosine retrieval on raw vectors for roads (19.1), centred space
for all geometry (15), sum pooling + mass presence (18), stops=9, k=3.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"
OUTDIR = ASSETS / "21-geometry"
GROWTH = ASSETS / "17-corpus-growth"
SAE = ASSETS / "18-sae-fingerprints"
SEED = 20260803
N_TAGS = 10
STOPS = np.linspace(0.0, 1.0, 9)
TOP_RETRIEVED = 3
TOP_K = 256
DRAWS = 1000
POLYTOPE_FRACS = np.array([1 / 4, 1 / 3, 2 / 5, 3 / 7, 1 / 2])
FRAC_TOL = 0.02


def unit(M: np.ndarray) -> np.ndarray:
    return M / (np.linalg.norm(M, axis=-1, keepdims=True) + 1e-12)


def slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    om = float(np.arccos(np.clip(float(a @ b), -1.0, 1.0)))
    return (np.sin((1 - t) * om) * a + np.sin(t * om) * b) / (np.sin(om) + 1e-12)


def slerp_tangent(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    om = float(np.arccos(np.clip(float(a @ b), -1.0, 1.0)))
    d = (om * (-np.cos((1 - t) * om) * a + np.cos(t * om) * b)) / (np.sin(om) + 1e-12)
    return d / (np.linalg.norm(d) + 1e-12)


def participation_ratio(gram: np.ndarray) -> float:
    ev = np.clip(np.linalg.eigvalsh(gram), 0, None)
    return float(ev.sum() ** 2 / (np.square(ev).sum() + 1e-12))


def pair_cosines(V: np.ndarray) -> np.ndarray:
    C = V @ V.T
    return C[np.triu_indices(len(V), 1)]


def dimensionality(V: np.ndarray) -> np.ndarray:
    """Per-vector dimensionality of Elhage et al. 2022 over unit rows."""
    C2 = np.square(V @ V.T)
    return 1.0 / C2.sum(axis=1)


def frac_hits(D: np.ndarray) -> int:
    return int((np.abs(D[:, None] - POLYTOPE_FRACS[None, :]) <= FRAC_TOL).any(axis=1).sum())


def extract_wdec() -> None:
    """Pull the 31 cone features' decoder rows out of the Gemma-Scope SAE."""
    from sae_lens import SAE as SaeLensSAE

    cone = json.loads((SAE / "cone-features.json").read_text())
    # cone-features.json truncates its `top` list, so recompute mass-presence
    # document frequency (top-256 by sum, 18.3's instrument) from the artifact
    S = np.load(SAE / "fingerprints.npz")["sum"].astype(np.float32)
    ranks = np.argsort(-S, axis=1)[:, :256]
    present = np.zeros(S.shape, dtype=bool)
    np.put_along_axis(present, ranks, True, axis=1)
    df = present.mean(axis=0)
    idx = sorted(int(i) for i in np.where(df >= 0.9)[0])
    assert len(idx) == cone["features_over_90pct"], (len(idx), cone["features_over_90pct"])
    sae = SaeLensSAE.from_pretrained(
        release="gemma-scope-2b-pt-res", sae_id="layer_20/width_16k/average_l0_71", device="cpu"
    )
    sae_module = sae[0] if isinstance(sae, tuple) else sae
    W = sae_module.W_dec.detach().float().numpy()
    rows = W[idx]
    OUTDIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUTDIR / "cone-decoder.npz", W=rows.astype(np.float32), indices=np.array(idx)
    )
    print(f"wrote cone-decoder.npz  {rows.shape} from W_dec {W.shape}")


def load_corpus():
    X = unit(np.load(GROWTH / "vectors-fresh.npz")["X"].astype(np.float32))
    meta = json.loads((GROWTH / "tags-fresh.json").read_text())
    labels = meta["labels"]
    titles = meta["names"]
    counts = Counter(t for ls in labels for t in ls)
    tags = [t for t, _ in counts.most_common(N_TAGS)]
    members = {t: [i for i, ls in enumerate(labels) if t in ls] for t in tags}
    return X, labels, titles, tags, members


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from plot_assets import (
        BLUE,
        CYAN,
        DPI,
        GOLD,
        MARGIN,
        MUTED,
        RED,
        figure,
        frame_panels,
        panel_title,
        style_axes,
    )

    def save(fig, name: str) -> None:
        frame_panels(fig)
        OUTDIR.mkdir(parents=True, exist_ok=True)
        out = OUTDIR / name
        fig.savefig(out, dpi=DPI, facecolor="#08080a")
        print(f"wrote {out.relative_to(ASSETS.parent.parent)}  ({out.stat().st_size // 1024}KB)")
        plt.close(fig)

    rng = np.random.default_rng(SEED)
    X, labels, titles, tags, members = load_corpus()
    n, dim = X.shape
    mean = X.mean(axis=0)
    Xc = unit(X - mean)
    sizes = [len(members[t]) for t in tags]
    print(f"corpus {n}x{dim}, tags: " + ", ".join(f"{t}({s})" for t, s in zip(tags, sizes)))
    results: dict = {
        "seed": SEED,
        "commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        ).stdout.strip(),
        "tags": tags,
        "sizes": sizes,
    }

    # ---- 21.1 constellation -------------------------------------------------
    Cc = unit(np.stack([Xc[members[t]].mean(axis=0) for t in tags]))
    cos_real = pair_cosines(Cc)
    pr_real = participation_ratio(Cc @ Cc.T)

    iso_mean, iso_spread, iso_pr = [], [], []
    for _ in range(DRAWS):
        V = unit(rng.standard_normal((N_TAGS, dim)))
        c = pair_cosines(V)
        iso_mean.append(np.abs(c).mean())
        iso_spread.append(c.max() - c.min())
        iso_pr.append(participation_ratio(V @ V.T))
    disjoint = sum(sizes) <= n
    sub_mean, sub_spread, sub_pr = [], [], []
    for _ in range(DRAWS):
        if disjoint:
            perm = rng.permutation(n)
            groups, at = [], 0
            for s in sizes:
                groups.append(perm[at : at + s])
                at += s
        else:
            groups = [rng.choice(n, size=s, replace=False) for s in sizes]
        V = unit(np.stack([Xc[g].mean(axis=0) for g in groups]))
        c = pair_cosines(V)
        sub_mean.append(np.abs(c).mean())
        sub_spread.append(c.max() - c.min())
        sub_pr.append(participation_ratio(V @ V.T))
    results["21.1"] = {
        "subset_null_disjoint": disjoint,
        "mean_abs_cos": float(np.abs(cos_real).mean()),
        "iso_mean_abs_cos_p95": float(np.quantile(iso_mean, 0.95)),
        "spread": float(cos_real.max() - cos_real.min()),
        "subset_spread_p95": float(np.quantile(sub_spread, 0.95)),
        "participation_ratio": pr_real,
        "iso_pr_p5": float(np.quantile(iso_pr, 0.05)),
        "subset_pr_p5": float(np.quantile(sub_pr, 0.05)),
        "pair_cos_min": float(cos_real.min()),
        "pair_cos_max": float(cos_real.max()),
        "verdict_a_nonorthogonal": bool(np.abs(cos_real).mean() > np.quantile(iso_mean, 0.95)),
        "verdict_b_structured": bool(
            (cos_real.max() - cos_real.min()) > np.quantile(sub_spread, 0.95)
        ),
        "verdict_c_pr_le_5": bool(pr_real <= 5.0),
    }
    print("21.1", {k: v for k, v in results["21.1"].items() if k.startswith("verdict")})

    # ---- 21.2 polytope probe ------------------------------------------------
    dec = np.load(OUTDIR / "cone-decoder.npz")
    W = unit(dec["W"].astype(np.float64))
    dcos = pair_cosines(W)
    dD = dimensionality(W)
    d_hits = frac_hits(dD)
    iso_dec_mean, iso_dec_hits = [], []
    for _ in range(DRAWS):
        V = unit(rng.standard_normal(W.shape))
        iso_dec_mean.append(float(np.abs(pair_cosines(V)).mean()))
        iso_dec_hits.append(frac_hits(dimensionality(V)))
    cD = dimensionality(Cc.astype(np.float64))
    diffs = {}
    for a, b in combinations(range(N_TAGS), 2):
        diffs[(a, b)] = unit(Cc[a] - Cc[b])
    para = []
    for (a, b), (c, d) in combinations(diffs.keys(), 2):
        if len({a, b, c, d}) == 4:
            para.append(
                (
                    float(diffs[(a, b)] @ diffs[(c, d)]),
                    f"{tags[a]}-{tags[b]}",
                    f"{tags[c]}-{tags[d]}",
                )
            )
    para.sort(key=lambda r: -abs(r[0]))
    dC = W @ W.T
    iu31 = np.triu_indices(len(W), 1)
    antipodal = sorted(
        (
            {
                "i": int(dec["indices"][i]),
                "j": int(dec["indices"][j]),
                "cos": round(float(dC[i, j]), 4),
            }
            for i, j in zip(*iu31)
            if abs(dC[i, j]) > 0.5
        ),
        key=lambda p: p["cos"],
    )
    results["21.2"] = {
        "decoder_mean_abs_cos": float(np.abs(dcos).mean()),
        "decoder_iso_p95": float(np.quantile(iso_dec_mean, 0.95)),
        "decoder_mean_cos_signed": float(dcos.mean()),
        "decoder_frac_hits": d_hits,
        "antipodal_pairs": antipodal,
        "decoder_frac_hits_null_p95": float(np.quantile(iso_dec_hits, 0.95)),
        "decoder_D_min": float(dD.min()),
        "decoder_D_max": float(dD.max()),
        "centroid_min_pair_cos": float(pair_cosines(Cc).min()),
        "centroid_D": [float(v) for v in cD],
        "verdict_a1_nonisotropic": bool(np.abs(dcos).mean() > np.quantile(iso_dec_mean, 0.95)),
        "verdict_a2_no_plateaus": bool(d_hits <= np.quantile(iso_dec_hits, 0.95)),
        "verdict_b_no_antipodal": bool(pair_cosines(Cc).min() > -0.5),
        "parallelogram_top5": [{"cos": round(c, 3), "ab": ab, "cd": cd} for c, ab, cd in para[:5]],
    }
    print("21.2", {k: v for k, v in results["21.2"].items() if k.startswith("verdict")})

    # ---- 21.3 intersections -------------------------------------------------
    cent_raw = {t: unit(X[members[t]].mean(axis=0)) for t in tags}
    F = None  # lazy, for 21.4
    roads = []
    road_notes: dict[int, set] = {}
    slot_counter: Counter = Counter()
    for ri, (ta, tb) in enumerate(combinations(tags, 2)):
        a, b = cent_raw[ta], cent_raw[tb]
        stops = []
        for t in STOPS:
            v = slerp(a, b, float(t))
            sims = X @ v
            top = np.argsort(-sims)[:TOP_RETRIEVED]
            stops.append({"t": float(t), "top": top.tolist(), "sims": sims[top].tolist()})
            for j in top:
                slot_counter[int(j)] += 1
                road_notes.setdefault(int(j), set()).add(ri)
        roads.append(
            {
                "a": ta,
                "b": tb,
                "min_support": min(s["sims"][0] for s in stops),
                "stops": stops,
            }
        )
    degree = {j: len(rs) for j, rs in road_notes.items()}
    by_degree = sorted(degree, key=lambda j: (-degree[j], -slot_counter[j]))
    top10 = by_degree[:10]
    share = sum(slot_counter[j] for j in top10) / (len(roads) * len(STOPS) * TOP_RETRIEVED)

    def first_t(ri: int, j: int) -> float:
        return next(s["t"] for s in roads[ri]["stops"] if j in s["top"])

    null_angles = []
    for _ in range(DRAWS):
        r1, r2 = rng.choice(len(roads), 2, replace=False)
        t1, t2 = rng.choice(STOPS), rng.choice(STOPS)
        T1 = slerp_tangent(cent_raw[roads[r1]["a"]], cent_raw[roads[r1]["b"]], float(t1))
        T2 = slerp_tangent(cent_raw[roads[r2]["a"]], cent_raw[roads[r2]["b"]], float(t2))
        null_angles.append(np.degrees(np.arccos(np.clip(abs(float(T1 @ T2)), 0, 1))))
    crossings = []
    for j, rs in road_notes.items():
        if len(rs) < 2:
            continue
        angs = []
        for r1, r2 in combinations(sorted(rs), 2):
            T1 = slerp_tangent(cent_raw[roads[r1]["a"]], cent_raw[roads[r1]["b"]], first_t(r1, j))
            T2 = slerp_tangent(cent_raw[roads[r2]["a"]], cent_raw[roads[r2]["b"]], first_t(r2, j))
            angs.append(float(np.degrees(np.arccos(np.clip(abs(float(T1 @ T2)), 0, 1)))))
        crossings.append(
            {"note": j, "degree": len(rs), "max_angle": max(angs), "title": titles[j][:70]}
        )
    crossings.sort(key=lambda c: (-c["degree"], -c["max_angle"]))
    true_crossings = [c for c in crossings if c["degree"] >= 4 and c["max_angle"] >= 60.0]
    results["21.3"] = {
        "n_slots": len(roads) * len(STOPS) * TOP_RETRIEVED,
        "top10_slot_share": float(share),
        "max_degree": max(degree.values()),
        "notes_deg_ge_3": sum(1 for d in degree.values() if d >= 3),
        "notes_deg_ge_4": sum(1 for d in degree.values() if d >= 4),
        "null_angle_median": float(np.median(null_angles)),
        "true_crossings": len(true_crossings),
        "top_crossings": crossings[:10],
        "verdict_a_share_ge_25pct": bool(share >= 0.25),
        "verdict_b_3_true_crossings": bool(len(true_crossings) >= 3),
        "kill_no_deg3": bool(max(degree.values()) < 3),
    }
    print("21.3", {k: v for k, v in results["21.3"].items() if k.startswith(("verdict", "kill"))})

    # ---- 21.4 roundabouts ---------------------------------------------------
    S = np.load(SAE / "fingerprints.npz")["sum"].astype(np.float32)
    F = S / (S.sum(axis=1, keepdims=True) + 1e-9)
    fmean = {t: F[members[t]].mean(axis=0) for t in tags}
    handovers, single, curves = [], 0, []
    for ri, road in enumerate(roads):
        fa, fb = fmean[road["a"]], fmean[road["b"]]
        a_set = set(np.argsort(-fa)[:TOP_K].tolist())
        b_set = set(np.argsort(-fb)[:TOP_K].tolist())
        a_only = np.array(sorted(a_set - b_set))
        b_only = np.array(sorted(b_set - a_set))
        shares = []
        for s in road["stops"]:
            w = np.array(s["sims"])
            w = w / w.sum()
            blend = (F[s["top"]] * w[:, None]).sum(axis=0)
            ma, mb = float(blend[a_only].sum()), float(blend[b_only].sum())
            shares.append(ma / (ma + mb + 1e-12))
        sgn = np.sign(np.array(shares) - 0.5)
        flips = int((sgn[:-1] != sgn[1:]).sum())
        curves.append((shares, flips))
        if flips == 1:
            single += 1
            k = next(i for i, sh in enumerate(shares) if sh < 0.5)
            handovers.append({"road": ri, "stop": k, "note": road["stops"][k]["top"][0]})
    kill = single < 35
    results["21.4"] = {
        "single_crossing_roads": single,
        "flip_counts": dict(Counter(f for _, f in curves)),
        "kill_construct_void": bool(kill),
    }
    if not kill:
        counts = Counter(h["note"] for h in handovers)
        top_note, top_count = counts.most_common(1)[0]
        null_max = []
        for _ in range(DRAWS):
            c = Counter()
            for h in handovers:
                s = int(rng.integers(0, len(STOPS)))
                c[roads[h["road"]]["stops"][s]["top"][0]] += 1
            null_max.append(c.most_common(1)[0][1])
        h_notes = {h["note"] for h in handovers}
        h_deg = [degree[j] for j in h_notes]
        o_deg = [degree[j] for j in degree if j not in h_notes]
        pooled = np.array(h_deg + o_deg, dtype=float)
        obs = float(np.median(h_deg) - np.median(o_deg))
        perm = []
        for _ in range(10000):
            rng.shuffle(pooled)
            perm.append(float(np.median(pooled[: len(h_deg)]) - np.median(pooled[len(h_deg) :])))
        p = float((np.array(perm) >= obs).mean())
        results["21.4"].update(
            {
                "top_handover_note": {"note": int(top_note), "title": titles[top_note][:70]},
                "top_handover_count": int(top_count),
                "null_max_p95": float(np.quantile(null_max, 0.95)),
                "handover_deg_median": float(np.median(h_deg)),
                "other_deg_median": float(np.median(o_deg)),
                "perm_p": p,
                "verdict_a_concentration": bool(
                    top_count >= 4 and top_count > np.quantile(null_max, 0.95)
                ),
                "verdict_b_handover_at_intersections": bool(p < 0.05),
            }
        )
    print("21.4", {k: v for k, v in results["21.4"].items() if k.startswith(("verdict", "kill"))})

    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "results.json").write_text(json.dumps(results, indent=1))
    print("wrote results.json")

    # ---- figures ------------------------------------------------------------
    r1 = results["21.1"]
    fig, top = figure(
        16.5,
        7.6,
        1,
        "section 21.1 — the shape of the city map",
        "Ten interests are neither orthogonal nor a blur: a thin, structured constellation",
        meta=f"centred Qwen3 space · {n} notes · nulls: {DRAWS} isotropic + {DRAWS} subset draws · seed {SEED}",
    )
    gs = fig.add_gridspec(
        1, 3, left=MARGIN + 0.035, right=1 - MARGIN, top=top, bottom=0.13, wspace=0.34
    )
    ax = fig.add_subplot(gs[0])
    order = np.argsort([-s for s in sizes])
    M = (Cc @ Cc.T)[np.ix_(order, order)]
    im = ax.imshow(M, cmap="magma", vmin=-0.2, vmax=1.0)
    ax.set_xticks(range(N_TAGS))
    ax.set_yticks(range(N_TAGS))
    ax.set_xticklabels([tags[i] for i in order], rotation=60, ha="right", fontsize=6)
    ax.set_yticklabels([tags[i] for i in order], fontsize=6)
    fig.colorbar(im, ax=ax, fraction=0.046, label="centred cosine")
    panel_title(ax, "pairwise cosines, centred centroids")
    style_axes(ax)
    ax = fig.add_subplot(gs[1])
    bins = np.linspace(-0.3, 0.9, 36)
    iso_all = pair_cosines(unit(rng.standard_normal((N_TAGS * 40, dim))))
    ax.hist(iso_all, bins=bins, density=True, color=MUTED, alpha=0.55, label="isotropic null")
    ax.hist(cos_real, bins=bins, density=True, color=GOLD, alpha=0.85, label="tag centroids")
    ax.axvline(0, color=MUTED, lw=0.6, ls=":")
    ax.set_xlabel("pairwise cosine")
    ax.set_ylabel("density")
    ax.legend(fontsize=6.5)
    panel_title(
        ax, f"mean |cos| {r1['mean_abs_cos']:.3f} vs null p95 {r1['iso_mean_abs_cos_p95']:.3f}"
    )
    style_axes(ax)
    ax = fig.add_subplot(gs[2])
    ev = np.clip(np.linalg.eigvalsh(Cc @ Cc.T), 0, None)[::-1]
    ax.bar(range(1, N_TAGS + 1), ev, color=BLUE, label="eigenvalues")
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.set_xlabel("component")
    ax.set_ylabel("eigenvalue")
    ax.legend(fontsize=6.5)
    panel_title(
        ax,
        f"participation ratio {pr_real:.2f} (iso p5 {r1['iso_pr_p5']:.2f}, subset p5 {r1['subset_pr_p5']:.2f})",
    )
    style_axes(ax)
    save(fig, "01-constellation.png")

    r2 = results["21.2"]
    n_anti = sum(1 for p in r2["antipodal_pairs"] if p["cos"] < -0.5)
    fig, top = figure(
        16.5,
        7.6,
        2,
        "section 21.2 — polytope probe: the registered skeptic loses",
        "The digon shows up: six antipodal decoder pairs land twelve cone features exactly on the 1/2 plateau",
        meta=f"31 cone-feature decoder rows, Gemma-Scope 16k L0~71 · dimensionality of Elhage et al. 2022 · "
        f"{n_anti} pairs under cos -0.5 · seed {SEED}",
    )
    gs = fig.add_gridspec(1, 3, left=MARGIN, right=1 - MARGIN, top=top, bottom=0.13, wspace=0.34)
    ax = fig.add_subplot(gs[0])
    ax.scatter(range(len(dD)), np.sort(dD), color=CYAN, s=14, label="decoder D_i")
    for fval, lab in zip(POLYTOPE_FRACS, ["1/4", "1/3", "2/5", "3/7", "1/2"]):
        ax.axhline(fval, color=MUTED, lw=0.5, ls=":")
        ax.text(len(dD) - 0.5, fval + 0.006, lab, color=MUTED, fontsize=5.5, ha="right")
    ax.set_xlabel("feature (sorted)")
    ax.set_ylabel("dimensionality D_i")
    ax.legend(fontsize=6.5, loc="upper left")
    panel_title(
        ax,
        f"plateau hits {r2['decoder_frac_hits']} vs null p95 {r2['decoder_frac_hits_null_p95']:.0f}",
    )
    style_axes(ax)
    ax = fig.add_subplot(gs[1])
    bins = np.linspace(-1.0, 0.7, 60)
    iso_dec = pair_cosines(unit(rng.standard_normal((31 * 20, W.shape[1]))))
    ax.hist(iso_dec, bins=bins, density=True, color=MUTED, alpha=0.55, label="isotropic null")
    ax.hist(dcos, bins=bins, density=True, color=CYAN, alpha=0.8, label="decoder pairs")
    for p in r2["antipodal_pairs"]:
        if p["cos"] < -0.5:
            ax.axvline(p["cos"], color=RED, lw=0.7, alpha=0.8)
    ax.axvline(-2, color=RED, lw=0.7, label="antipodal pairs")  # legend proxy
    ax.set_xlim(-1.05, 0.7)
    ax.set_yscale("log")
    ax.set_xlabel("pairwise cosine")
    ax.set_ylabel("density (log)")
    ax.legend(fontsize=6.5)
    panel_title(
        ax,
        f"the pairs sit at cos {min(p['cos'] for p in r2['antipodal_pairs']):.2f}..-0.93, "
        "far outside any null",
    )
    style_axes(ax)
    ax = fig.add_subplot(gs[2])
    ax.scatter(range(N_TAGS), np.sort(cD), color=GOLD, s=22, label="centroid D_i")
    ax.axhline(1.0, color=MUTED, lw=0.5, ls=":")
    ax.set_ylim(0, max(cD) * 1.2)
    ax.set_xlabel("tag centroid (sorted)")
    ax.set_ylabel("dimensionality D_i")
    ax.legend(fontsize=6.5, loc="lower right")
    panel_title(ax, f"min pair cos {r2['centroid_min_pair_cos']:+.3f}: no antipodal pair")
    style_axes(ax)
    save(fig, "02-polytope-probe.png")

    r3 = results["21.3"]
    fig, top = figure(
        16.5,
        7.6,
        3,
        "section 21.3 — intersections",
        "A few notes carry the road network, and the roads genuinely cross there",
        meta=f"45 tag-centroid roads · 9 stops · top-3 · {r3['n_slots']} slots · crossing angle between slerp tangents",
    )
    gs = fig.add_gridspec(1, 3, left=MARGIN, right=1 - MARGIN, top=top, bottom=0.13, wspace=0.34)
    ax = fig.add_subplot(gs[0])
    degs = sorted(degree.values(), reverse=True)
    ax.plot(range(1, len(degs) + 1), degs, color=BLUE, lw=1.4, label="road-degree by rank")
    ax.set_xscale("log")
    ax.set_xlabel("note rank")
    ax.set_ylabel("roads served")
    ax.legend(fontsize=6.5)
    panel_title(
        ax,
        f"only {len(degree)} notes ever retrieved; top-10 hold {r3['top10_slot_share']:.0%} of slots",
    )
    style_axes(ax)
    ax = fig.add_subplot(gs[1])
    xs = [c["degree"] for c in crossings]
    ys = [c["max_angle"] for c in crossings]
    ax.scatter(xs, ys, color=CYAN, s=12, alpha=0.75, label="shared notes")
    ax.axhline(60, color=RED, lw=0.8, ls="--", label="60 deg bar")
    ax.axhline(r3["null_angle_median"], color=MUTED, lw=0.8, ls=":", label="null median")
    ax.set_xlabel("road-degree")
    ax.set_ylabel("max crossing angle (deg)")
    ax.legend(fontsize=6.5, loc="lower right")
    panel_title(ax, f"{r3['true_crossings']} true crossings (degree >= 4, angle >= 60)")
    style_axes(ax)
    ax = fig.add_subplot(gs[2])
    top_c = crossings[:8][::-1]
    ax.barh(range(len(top_c)), [c["degree"] for c in top_c], color=GOLD, label="road-degree")
    ax.set_yticks(range(len(top_c)))
    ax.set_yticklabels([c["title"][:22] for c in top_c], fontsize=5.8, color=MUTED)
    ax.set_xlabel("roads served")
    ax.legend(fontsize=6.5, loc="lower right")
    panel_title(ax, "the interchange list")
    style_axes(ax)
    save(fig, "03-intersections.png")

    r4 = results["21.4"]
    killed = r4["kill_construct_void"]
    fig, top = figure(
        16.5,
        7.6,
        4,
        "section 21.4 — roundabouts: killed by its registered criterion",
        "The single-handover premise does not generalize: 31 of 45 roads cross once, under the registered 35",
        meta=f"kill bar: >= 35/45 single-crossing roads · measured {r4['single_crossing_roads']}/45 · "
        "the roundabout construct is void on this corpus",
    )
    ncols = 2 if killed else 3
    gs = fig.add_gridspec(1, ncols, left=MARGIN, right=1 - MARGIN, top=top, bottom=0.13, wspace=0.3)
    ax = fig.add_subplot(gs[0])
    for shares, flips in curves:
        multi = flips != 1
        ax.plot(
            STOPS,
            shares,
            color=RED if multi else BLUE,
            lw=0.9 if multi else 0.6,
            alpha=0.7 if multi else 0.3,
        )
    ax.plot([], [], color=BLUE, lw=1.2, label="single crossing (31)")
    ax.plot([], [], color=RED, lw=1.2, label="multi / no crossing (14)")
    ax.axhline(0.5, color=MUTED, lw=0.8, ls="--", label="handover line")
    ax.set_xlabel("t along road")
    ax.set_ylabel("A-side share of exclusive mass")
    ax.legend(fontsize=6.5)
    panel_title(ax, "every road's vocabulary handover curve")
    style_axes(ax)
    ax = fig.add_subplot(gs[1])
    fc = results["21.4"]["flip_counts"]
    ks = sorted(fc)
    ax.bar([str(k) for k in ks], [fc[k] for k in ks], color=[BLUE if k == 1 else RED for k in ks])
    ax.bar(0, 0, color=BLUE, label="well-defined handover")
    ax.bar(0, 0, color=RED, label="void under registration")
    ax.axhline(35, color=GOLD, lw=1.0, ls="--", label="kill bar (35 at flips=1)")
    ax.set_xlabel("times the share curve crosses 0.5")
    ax.set_ylabel("roads")
    ax.legend(fontsize=6.5)
    panel_title(ax, f"{r4['single_crossing_roads']} < 35: the kill criterion fires")
    style_axes(ax)
    if not killed:
        counts = Counter(h["note"] for h in handovers)
        ax = fig.add_subplot(gs[2])
        common = counts.most_common(8)[::-1]
        ax.barh(
            range(len(common)), [c for _, c in common], color=GOLD, label="roads handed over here"
        )
        ax.axvline(r4["null_max_p95"], color=RED, lw=0.8, ls="--", label="shuffle null p95 (max)")
        ax.set_yticks(range(len(common)))
        ax.set_yticklabels([titles[j][:34] for j, _ in common], fontsize=5.8, color=MUTED)
        ax.set_xlabel("roads")
        ax.legend(fontsize=6.5, loc="lower right")
        panel_title(ax, f"top roundabout serves {r4['top_handover_count']} roads")
        style_axes(ax)
    save(fig, "04-roundabouts.png")

    # ---- 21.5 the map -------------------------------------------------------
    cm = Cc.mean(axis=0)
    U, sv, Vt = np.linalg.svd(Cc - cm, full_matrices=False)
    basis = Vt[:2]
    P = (Xc - cm) @ basis.T
    # city markers use the arcs' own construction (centred raw centroids) so
    # roads anchor exactly on their endpoints; the 21.1 stats keep Cc
    Pc = (np.stack([unit(cent_raw[t] - mean) for t in tags]) - cm) @ basis.T
    fig, top = figure(
        16.5,
        10.6,
        5,
        "section 21.5 — the map",
        "The road atlas: 45 roads through the interest constellation, weighted by their weakest stop",
        meta="centred corpus in the centroid-PCA basis (section 15: fitted axes or nothing) · "
        "interstates thick, backroads thin · crossings marked",
    )
    ax = fig.add_axes((MARGIN, 0.07, 1 - 2 * MARGIN, top - 0.10))
    ax.scatter(P[:, 0], P[:, 1], s=3, color=MUTED, alpha=0.28, label="notes (centred)")
    mins = np.array([r["min_support"] for r in roads])
    lo, hi = mins.min(), mins.max()
    for road in roads:
        a, b = cent_raw[road["a"]], cent_raw[road["b"]]
        arc = np.stack([unit(slerp(a, b, float(t)) - mean) for t in np.linspace(0, 1, 33)])
        q = ((road["min_support"] - lo) / (hi - lo + 1e-12)) if hi > lo else 0.5
        ax.plot(
            (arc - cm) @ basis.T[:, 0],
            (arc - cm) @ basis.T[:, 1],
            color=GOLD,
            lw=0.5 + 2.2 * q,
            alpha=0.18 + 0.5 * q,
            zorder=2,
        )
    ax.plot([], [], color=GOLD, lw=2.4, label="interstate (high min-support)")
    ax.plot([], [], color=GOLD, lw=0.6, alpha=0.4, label="backroad (low min-support)")
    for c in crossings[:6]:
        ax.scatter(*P[c["note"]], s=52, facecolors="none", edgecolors=CYAN, lw=1.2, zorder=4)
    ax.scatter([], [], s=52, facecolors="none", edgecolors=CYAN, label="intersections (top 6)")
    if not r4["kill_construct_void"]:
        rb = [j for j, _ in Counter(h["note"] for h in handovers).most_common(3)]
        for j in rb:
            ax.scatter(*P[j], s=110, facecolors="none", edgecolors=RED, lw=1.2, zorder=4)
        ax.scatter([], [], s=110, facecolors="none", edgecolors=RED, label="roundabouts (top 3)")
    for k, t in enumerate(tags):
        ax.scatter(*Pc[k], s=30, color=BLUE, zorder=5)
        ax.annotate(
            t,
            Pc[k],
            textcoords="offset points",
            xytext=(5, 5),
            color="#e8e5de",
            fontsize=7.5,
            zorder=6,
        )
    ax.scatter([], [], s=30, color=BLUE, label="tag centroids")
    ax.set_xlabel("centroid PC 1")
    ax.set_ylabel("centroid PC 2")
    ax.legend(fontsize=6.8, loc="lower right", framealpha=0.2)
    style_axes(ax)
    save(fig, "05-the-map.png")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "wdec":
        extract_wdec()
    else:
        main()
