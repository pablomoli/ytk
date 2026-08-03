#!/usr/bin/env python
"""Freeze vs fresh: does the measured geometry survive 13% corpus growth?

Every geometric claim so far — the cone (12), the pair-plane inheritance (15),
the tag coherence verdict (10) — was measured on one frozen snapshot of 493
vectors. The corpus has since grown. These are the out-of-sample tests, in
priority order:

    E1  plateau falsification: does ||mean|| hold at the fresh n, and does the
        mean direction stay put?
    E2  participation ratio: the freeze capped measurable rank at 492; is ~104
        effective dims an n-limit or an encoder property?
    E3  tag z stability: do the per-tag coherence z-scores replicate on fresh
        vectors with fresh nulls?
    E4  fig-05 path support: does slerp-path retrieval support rise as the
        codebook gets denser?

Freeze and fresh both run through the same functions in the same process —
frozen numbers are never copied forward from old results.json files. The
frozen snapshot at docs/assets/10-tag-coherence/vectors.npz is read-only;
the fresh capture lands in docs/assets/17-corpus-growth/ and never touches it.

    harvest -> vectors-fresh.npz + tags-fresh.json   (reads vault + Chroma)
    analyze -> results.json                          (pure numpy, both snapshots)
    plot    -> *.png

    uv run --with matplotlib python scripts/growth_experiments.py <phase>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parents[1]
FREEZE = REPO / "docs" / "assets" / "10-tag-coherence"
OUTDIR = REPO / "docs" / "assets" / "17-corpus-growth"
FRESH_VECTORS = OUTDIR / "vectors-fresh.npz"
FRESH_TAGS = OUTDIR / "tags-fresh.json"
RESULTS = OUTDIR / "results.json"

SEED = 20260804
NULL_DRAWS = 400  # matches tag_coherence.py
MIN_NOTES = 6  # matches tag_coherence.py
SUBSAMPLE_DRAWS = 20
PATH_STEPS = 41  # matches plot_plane.py fig05

# fig-05 endpoints, identified by stored name so both snapshots use the same notes
PAIR_A = "Every Software Engineer Interview Question I Got in 2026 (Coding, System Design "
PAIR_B_RELATED = "Tech interviews with NeetCode"
PAIR_B_UNRELATED = "randyroberts-DWpSK4uDhIO-tribe-brain-heatmap"


def _unit(M: np.ndarray) -> np.ndarray:
    return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)


def harvest() -> None:
    """Fresh capture, same join as tag_coherence.harvest, different destination."""
    from tag_coherence import parse_frontmatter_tags

    from ytk import store
    from ytk.vault import _get_brain_path

    OUTDIR.mkdir(parents=True, exist_ok=True)
    brain = _get_brain_path()

    by_path: dict[str, list[str]] = {}
    for note in (brain / "sources").rglob("*.md"):
        tags = parse_frontmatter_tags(note.read_text(encoding="utf-8", errors="ignore"))
        if tags:
            by_path[str(note)] = tags

    vecs: list[np.ndarray] = []
    labels: list[list[str]] = []
    names: list[str] = []
    sources: list[str] = []

    vids = store._videos_collection().get(include=["embeddings", "metadatas"])
    for emb, meta in zip(vids["embeddings"], vids["metadatas"]):
        tags = [t.strip() for t in str(meta.get("tags", "")).split(",") if t.strip()]
        if not tags:
            continue
        vecs.append(np.asarray(emb, dtype=np.float32))
        labels.append(tags)
        names.append(str(meta.get("title", meta.get("video_id", "")))[:80])
        sources.append("youtube")

    mem = store._memories_collection().get(include=["embeddings", "metadatas"])
    for emb, meta in zip(mem["embeddings"], mem["metadatas"]):
        path = str(meta.get("source_path", ""))
        tags = by_path.get(path)
        if not tags:
            continue
        vecs.append(np.asarray(emb, dtype=np.float32))
        labels.append(tags)
        names.append(Path(path).stem[:80])
        sources.append(Path(path).parent.name)

    X = _unit(np.vstack(vecs))
    np.savez_compressed(FRESH_VECTORS, X=X)
    FRESH_TAGS.write_text(json.dumps({"labels": labels, "names": names, "sources": sources}))
    print(f"fresh capture: {len(X)} notes -> {FRESH_VECTORS.name}")


def _load(which: str) -> tuple[np.ndarray, dict]:
    if which == "freeze":
        X = np.load(FREEZE / "vectors.npz")["X"].astype(np.float64)
        meta = json.loads((FREEZE / "tags.json").read_text())
    else:
        X = np.load(FRESH_VECTORS)["X"].astype(np.float64)
        meta = json.loads(FRESH_TAGS.read_text())
    return _unit(X), meta


def cone_stats(X: np.ndarray) -> dict:
    mu = X.mean(0)
    G = X @ X.T
    iu = np.triu_indices(len(X), k=1)
    return {
        "n": len(X),
        "mean_norm": float(np.linalg.norm(mu)),
        "mean_norm_isotropic": float(1 / np.sqrt(len(X))),
        "mean_pairwise_cos": float(G[iu].mean()),
        "mean_cos_to_mean_dir": float((X @ (mu / np.linalg.norm(mu))).mean()),
    }


def participation(X: np.ndarray) -> float:
    ev = np.linalg.svd(X - X.mean(0), compute_uv=False) ** 2
    ev = ev / ev.sum()
    return float((ev.sum() ** 2) / (ev**2).sum())


def subsample_curve(X: np.ndarray, fn, sizes: list[int], rng) -> dict:
    """fn measured on SUBSAMPLE_DRAWS random subsets per size: mean and sd."""
    out = {}
    for n in sizes:
        if n > len(X):
            continue
        vals = [fn(X[rng.choice(len(X), size=n, replace=False)]) for _ in range(SUBSAMPLE_DRAWS)]
        out[str(n)] = {"mean": float(np.mean(vals)), "sd": float(np.std(vals))}
    return out


def _mean_pairwise(sub: np.ndarray) -> float:
    if len(sub) < 2:
        return float("nan")
    gram = sub @ sub.T
    n = len(sub)
    return float((gram.sum() - np.trace(gram)) / (n * (n - 1)))


def tag_z(X: np.ndarray, labels: list[list[str]], rng) -> dict:
    """Per-tag coherence z against a size-matched null; tag_coherence.analyze verbatim."""
    from collections import Counter

    counts = Counter(t for ts in labels for t in ts)
    keep = sorted([t for t, c in counts.items() if c >= MIN_NOTES], key=lambda t: -counts[t])
    null_cache: dict[int, tuple[float, float]] = {}
    out = {}
    for tag in keep:
        idx = [i for i, ts in enumerate(labels) if tag in ts]
        obs = _mean_pairwise(X[idx])
        n = len(idx)
        if n not in null_cache:
            draws = [
                _mean_pairwise(X[rng.choice(len(X), size=n, replace=False)])
                for _ in range(NULL_DRAWS)
            ]
            null_cache[n] = (float(np.mean(draws)), float(np.std(draws)))
        mu, sd = null_cache[n]
        out[tag] = {"n": n, "z": (obs - mu) / sd if sd > 0 else 0.0}
    return out


def slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    om = float(np.arccos(np.clip(a @ b, -1.0, 1.0)))
    return (np.sin((1 - t) * om) * a + np.sin(t * om) * b) / np.sin(om)


def path_support(X: np.ndarray, names: list[str], a_name: str, b_name: str) -> dict | None:
    """Support along the slerp arc: cosine of the nearest real note, endpoints excluded."""
    try:
        i, j = names.index(a_name), names.index(b_name)
    except ValueError:
        return None
    ts = np.linspace(0, 1, PATH_STEPS)
    sup = []
    for t in ts:
        s = X @ slerp(X[i], X[j], float(t))
        s[[i, j]] = -1
        sup.append(float(s.max()))
    sup = np.array(sup)
    return {
        "i": i,
        "j": j,
        "support": [round(float(v), 4) for v in sup],
        "min": float(sup.min()),
        "median": float(np.median(sup)),
    }


def analyze() -> dict:
    rng = np.random.default_rng(SEED)
    snaps = {w: _load(w) for w in ("freeze", "fresh")}
    sizes = [64, 128, 256, 384, 493, len(snaps["fresh"][0])]

    out: dict = {
        "seed": SEED,
        "commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO
        ).stdout.strip(),
        "null_draws": NULL_DRAWS,
        "subsample_draws": SUBSAMPLE_DRAWS,
    }

    # E1 — the cone under growth
    e1 = {w: cone_stats(X) for w, (X, _) in snaps.items()}
    mu_f = snaps["freeze"][0].mean(0)
    mu_g = snaps["fresh"][0].mean(0)
    e1["mean_direction_alignment"] = float(
        (mu_f / np.linalg.norm(mu_f)) @ (mu_g / np.linalg.norm(mu_g))
    )
    e1["mean_norm_vs_n"] = subsample_curve(
        snaps["fresh"][0], lambda M: float(np.linalg.norm(M.mean(0))), sizes, rng
    )
    out["e1_plateau"] = e1

    # E2 — participation ratio: n-limited or real
    out["e2_participation"] = {
        "freeze": participation(snaps["freeze"][0]),
        "fresh": participation(snaps["fresh"][0]),
        "pr_vs_n": subsample_curve(snaps["fresh"][0], participation, sizes, rng),
    }

    # E3 — tag coherence z, fresh nulls on both sides
    z = {w: tag_z(X, meta["labels"], rng) for w, (X, meta) in snaps.items()}
    both = sorted(set(z["freeze"]) & set(z["fresh"]))
    out["e3_tag_z"] = {
        "freeze": z["freeze"],
        "fresh": z["fresh"],
        "shared_tags": both,
        "gained": sorted(set(z["fresh"]) - set(z["freeze"])),
        "lost": sorted(set(z["freeze"]) - set(z["fresh"])),
        "flips_below_2": [t for t in both if z["freeze"][t]["z"] >= 2 > z["fresh"][t]["z"]],
        "flips_above_2": [t for t in both if z["fresh"][t]["z"] >= 2 > z["freeze"][t]["z"]],
    }

    # E4 — path support on the same named pairs
    e4 = {}
    for w, (X, meta) in snaps.items():
        e4[w] = {
            "background_cos": cone_stats(X)["mean_pairwise_cos"],
            "related": path_support(X, meta["names"], PAIR_A, PAIR_B_RELATED),
            "unrelated": path_support(X, meta["names"], PAIR_A, PAIR_B_UNRELATED),
        }
    out["e4_path_support"] = e4

    OUTDIR.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(out, indent=1))

    for w in ("freeze", "fresh"):
        c = e1[w]
        print(
            f"{w:6s} n={c['n']}  ||mean||={c['mean_norm']:.4f}  "
            f"pairwise={c['mean_pairwise_cos']:+.4f}  "
            f"PR={out['e2_participation'][w]:.1f}"
        )
    print(f"mean-direction alignment: {e1['mean_direction_alignment']:+.5f}")
    zf, zg = z["freeze"], z["fresh"]
    print(
        f"tags: {len(zf)} freeze / {len(zg)} fresh / {len(both)} shared  "
        f"dropped-below-2: {out['e3_tag_z']['flips_below_2']}  "
        f"rose-above-2: {out['e3_tag_z']['flips_above_2']}"
    )
    for pair in ("related", "unrelated"):
        a, b = e4["freeze"][pair], e4["fresh"][pair]
        if a and b:
            print(
                f"path {pair:9s} min support {a['min']:.3f} -> {b['min']:.3f}   "
                f"median {a['median']:.3f} -> {b['median']:.3f}"
            )
    return out


def census() -> dict:
    """E5 — path support for every nearest-neighbor pair and a random-pair
    sample, plus who actually answers the stops (the hubness question)."""
    from collections import Counter

    X, meta = _load("fresh")
    names = meta["names"]
    n = len(X)
    S = X @ X.T
    np.fill_diagonal(S, -1.0)
    nn = S.argmax(1)

    pairs_nn = sorted({(min(i, int(j)), max(i, int(j))) for i, j in enumerate(nn)})
    rng = np.random.default_rng(SEED)
    pairs_rand: set[tuple[int, int]] = set()
    while len(pairs_rand) < 500:
        i, j = (int(v) for v in rng.integers(0, n, 2))
        if i != j and (min(i, j), max(i, j)) not in pairs_nn:
            pairs_rand.add((min(i, j), max(i, j)))

    ts = np.linspace(0, 1, PATH_STEPS)[1:-1]  # interior stops only

    def walk(i: int, j: int) -> tuple[float, float, float, list[int]]:
        Q = np.stack([slerp(X[i], X[j], float(t)) for t in ts])
        sup = Q @ X.T
        sup[:, [i, j]] = -1.0
        best = sup.argmax(1)
        vals = sup[np.arange(len(ts)), best]
        angle = float(np.degrees(np.arccos(np.clip(X[i] @ X[j], -1, 1))))
        return float(vals.min()), float(np.median(vals)), angle, [int(b) for b in best]

    hub_counts: Counter[int] = Counter()
    rows = {}
    for label, pairs in (("nn", pairs_nn), ("random", sorted(pairs_rand))):
        mins, medians, angles = [], [], []
        for i, j in pairs:
            mn, md, ang, best = walk(i, j)
            mins.append(mn)
            medians.append(md)
            angles.append(ang)
            hub_counts.update(set(best))  # one vote per path, not per stop
        rows[label] = {
            "n_paths": len(pairs),
            "min_support": [round(v, 4) for v in mins],
            "median_support": [round(v, 4) for v in medians],
            "angle_deg": [round(v, 2) for v in angles],
        }

    ranked = hub_counts.most_common()
    total_paths = rows["nn"]["n_paths"] + rows["random"]["n_paths"]
    out = {
        "seed": SEED,
        "steps_interior": len(ts),
        "background_cos": cone_stats(X)["mean_pairwise_cos"],
        "paths": rows,
        "hubs": {
            "distinct_answerers": len(ranked),
            "corpus_n": n,
            "top": [
                {"name": names[i][:60], "paths_served": c, "share": round(c / total_paths, 4)}
                for i, c in ranked[:15]
            ],
            "counts": [c for _, c in ranked],
        },
    }
    (OUTDIR / "census.json").write_text(json.dumps(out, indent=1))
    for label in ("nn", "random"):
        m = np.array(rows[label]["min_support"])
        print(
            f"{label:6s} {rows[label]['n_paths']} paths  min-support "
            f"p5 {np.percentile(m, 5):.3f}  median {np.median(m):.3f}  "
            f"below background: {(m < out['background_cos']).mean():.1%}"
        )
    print(
        f"hubs: {len(ranked)} of {n} notes ever answer a stop; "
        f"top note serves {ranked[0][1]}/{total_paths} paths ({names[ranked[0][0]][:50]})"
    )
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    if cmd == "harvest":
        harvest()
    elif cmd == "analyze":
        analyze()
    elif cmd == "census":
        census()
    elif cmd == "plot":
        from growth_plots import main as plot_main

        plot_main()
    else:
        raise SystemExit(f"unknown phase: {cmd}")
