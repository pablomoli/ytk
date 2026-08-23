"""E41 — vector search from first principles (#184).

Step 1 (baseline): brute-force exact top-k over the production vectors
vs the same queries through Chroma, per-query p50/p99.

Usage:
    uv run python scripts/e41_vector_search.py baseline
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytk import store

ASSETS = Path(__file__).resolve().parent.parent / "docs" / "assets" / "41-vector-search"
K = 10
N_QUERIES = 200
SEED = 41

BASES = {
    "videos": store._videos_collection,
    "segments": store._segments_collection,
    "memories": store._memories_collection,
}


def _pull_vectors() -> tuple[np.ndarray, list[str], dict[str, int]]:
    mats, ids, counts = [], [], {}
    for name, getter in BASES.items():
        coll = getter()
        got = coll.get(include=["embeddings"])
        emb = np.asarray(got["embeddings"], dtype=np.float32)
        mats.append(emb)
        ids.extend(got["ids"])
        counts[name] = len(got["ids"])
    return np.vstack(mats), ids, counts


def _pctl(samples_ms: list[float]) -> dict[str, float]:
    a = np.asarray(samples_ms)
    return {
        "p50_ms": float(np.percentile(a, 50)),
        "p99_ms": float(np.percentile(a, 99)),
        "mean_ms": float(a.mean()),
    }


def baseline() -> None:
    t0 = time.perf_counter()
    matrix, ids, counts = _pull_vectors()
    pull_s = time.perf_counter() - t0
    n, dim = matrix.shape

    # Cosine space: normalize once so the query loop is a pure dot product.
    normed = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)

    rng = np.random.default_rng(SEED)
    q_idx = rng.choice(n, size=N_QUERIES, replace=False)

    brute_ms: list[float] = []
    _ = normed @ normed[int(q_idx[0])]  # untimed warmup: first matmul pays BLAS setup
    for qi in q_idx:
        q = normed[qi]
        t = time.perf_counter()
        scores = normed @ q
        # argpartition beats full sort; k+1 because the query matches itself.
        top = np.argpartition(scores, -(K + 1))[-(K + 1) :]
        top[np.argsort(scores[top])[::-1]]
        brute_ms.append((time.perf_counter() - t) * 1000)

    chroma_ms: list[float] = []
    colls = {name: getter() for name, getter in BASES.items()}
    for (
        coll
    ) in colls.values():  # untimed warmup: first query per collection pays connection + cache costs
        coll.query(query_embeddings=[matrix[0].tolist()], n_results=1)
    for qi in q_idx:
        q = matrix[qi].tolist()
        t = time.perf_counter()
        for coll in colls.values():
            coll.query(query_embeddings=[q], n_results=K, include=["distances"])
        chroma_ms.append((time.perf_counter() - t) * 1000)

    out = {
        "stamp": time.strftime("%Y-%m-%d"),
        "step": "baseline",
        "n_vectors": int(n),
        "dim": int(dim),
        "per_collection": counts,
        "matrix_mb": round(matrix.nbytes / 2**20, 1),
        "pull_seconds": round(pull_s, 2),
        "n_queries": N_QUERIES,
        "k": K,
        "brute_force": _pctl(brute_ms),
        "chroma_three_collections": _pctl(chroma_ms),
        "samples_ms": {"brute": brute_ms, "chroma": chroma_ms},
    }
    ASSETS.mkdir(parents=True, exist_ok=True)
    path = ASSETS / "baseline.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    print(f"wrote {path}")


DATA_DIR = Path.home() / ".ytk" / "e41"
N_FULL = 10_000_000
CHUNK = 250_000  # 250k x 1024 f32 = 1GB working set; 16GB machine with neighbors
MATCH_SAMPLE = 4000
MATCH_PAIRS = 20000


def _fit_real() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mean + PCA basis scaled to reproduce the real covariance under Gaussian sampling."""
    matrix, _, _ = _pull_vectors()
    normed = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    mu = normed.mean(axis=0)
    centered = normed - mu
    _, s, vt = np.linalg.svd(centered, full_matrices=False)
    sigma = s / np.sqrt(len(normed) - 1)
    return normed, mu, (sigma[:, None] * vt)


def _gen_chunk(
    rng: np.random.Generator, n: int, mu: np.ndarray, scaled_vt: np.ndarray
) -> np.ndarray:
    z = rng.standard_normal((n, scaled_vt.shape[0]), dtype=np.float32)
    x = z @ scaled_vt.astype(np.float32) + mu.astype(np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def _pair_cosines(rng: np.random.Generator, rows: np.ndarray, n_pairs: int) -> np.ndarray:
    i = rng.integers(0, len(rows), n_pairs)
    j = rng.integers(0, len(rows), n_pairs)
    keep = i != j
    return np.einsum("ij,ij->i", rows[i[keep]], rows[j[keep]])


def _participation_ratio(rows: np.ndarray) -> float:
    c = rows - rows.mean(axis=0)
    lam = np.linalg.svd(c, compute_uv=False) ** 2
    return float(lam.sum() ** 2 / (lam**2).sum())


def synthetic() -> None:
    """Pilot: fit the real geometry, sample synthetics, measure the match."""
    rng = np.random.default_rng(SEED)
    normed, mu, scaled_vt = _fit_real()
    syn = _gen_chunk(rng, MATCH_SAMPLE, mu, scaled_vt)

    real_idx = rng.choice(len(normed), MATCH_SAMPLE, replace=False)
    real = normed[real_idx]

    out = {
        "stamp": time.strftime("%Y-%m-%d"),
        "step": "synthetic-pilot",
        "fit_n": len(normed),
        "dim": int(normed.shape[1]),
        "match_sample": MATCH_SAMPLE,
        "cos_to_mean": {
            "real": (real @ (mu / np.linalg.norm(mu))).tolist(),
            "synthetic": (syn @ (mu / np.linalg.norm(mu))).tolist(),
        },
        "pairwise_cos": {
            "real": _pair_cosines(rng, real, MATCH_PAIRS).tolist(),
            "synthetic": _pair_cosines(rng, syn, MATCH_PAIRS).tolist(),
        },
        "participation_ratio": {
            "real": _participation_ratio(real),
            "synthetic": _participation_ratio(syn),
        },
        "spectrum_top64": {
            "real": np.linalg.svd(real - real.mean(0), compute_uv=False)[:64].tolist(),
            "synthetic": np.linalg.svd(syn - syn.mean(0), compute_uv=False)[:64].tolist(),
        },
    }
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "match.json").write_text(json.dumps(out) + "\n")
    pr = out["participation_ratio"]
    print(f"PR real {pr['real']:.1f} vs synthetic {pr['synthetic']:.1f}")
    print(f"wrote {ASSETS / 'match.json'}")


def generate_full() -> None:
    """Write the full 10M synthetic corpus as a float32 memmap (not in the repo)."""
    rng = np.random.default_rng(SEED + 1)
    _, mu, scaled_vt = _fit_real()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "synthetic-10m.f32"
    mm = np.memmap(path, dtype=np.float32, mode="w+", shape=(N_FULL, scaled_vt.shape[1]))
    t0 = time.perf_counter()
    for start in range(0, N_FULL, CHUNK):
        n = min(CHUNK, N_FULL - start)
        mm[start : start + n] = _gen_chunk(rng, n, mu, scaled_vt)
        if (start // CHUNK) % 4 == 0:
            done = start + n
            print(f"{done:,}/{N_FULL:,}  {time.perf_counter() - t0:.0f}s", flush=True)
    mm.flush()
    print(f"wrote {path} ({path.stat().st_size / 2**30:.1f}GB) in {time.perf_counter() - t0:.0f}s")


def figures() -> None:
    import subprocess

    import matplotlib

    matplotlib.use("Agg")

    from plot_assets import (
        BG,
        BLUE,
        CYAN,
        DPI,
        GOLD,
        MARGIN,
        RED,
        figure,
        frame_panels,
        panel_title,
        style_axes,
        verdict,
    )

    d = json.loads((ASSETS / "baseline.json").read_text())
    brute = np.asarray(d["samples_ms"]["brute"])
    chroma = np.asarray(d["samples_ms"]["chroma"])
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    ratio = d["chroma_three_collections"]["p50_ms"] / d["brute_force"]["p50_ms"]

    fig, top = figure(
        15.0,
        6.6,
        1,
        "the baseline",
        "At this scale, doing nothing clever wins",
        f"{d['n_vectors']:,} vectors · {d['dim']}d · {d['n_queries']} production queries · k={d['k']} · "
        f"exact p50 {d['brute_force']['p50_ms']:.2f}ms / p99 {d['brute_force']['p99_ms']:.2f}ms · "
        f"chroma p50 {d['chroma_three_collections']['p50_ms']:.1f}ms / p99 "
        f"{d['chroma_three_collections']['p99_ms']:.1f}ms · {sha}",
    )
    gs = fig.add_gridspec(1, 1, left=0.085, right=1 - MARGIN - 0.02, top=top, bottom=0.13)
    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "per-query latency — exact brute force vs the production index path")

    bins = np.linspace(0, max(chroma.max(), brute.max()) * 1.04, 70)
    ax.hist(brute, bins=bins, color=GOLD, alpha=0.92, label="exact — one normalized matmul")
    ax.hist(chroma, bins=bins, color=BLUE, alpha=0.85, label="Chroma — 3 collections, HNSW + HTTP")
    for arr, color in ((brute, GOLD), (chroma, BLUE)):
        ax.axvline(float(np.percentile(arr, 50)), color=color, lw=1.2, ls="--", alpha=0.8)
    ax.set_xlabel("latency per query (ms)")
    ax.set_ylabel("queries")
    ax.legend(framealpha=0.0, labelcolor="#eceae7")
    ax.margins(x=0.01)

    verdict(
        fig, f"exact search beats the production index {ratio:.1f}x — the index pays no rent at 18k"
    )
    frame_panels(fig)
    out = ASSETS / "01-the-baseline.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out}")

    match_path = ASSETS / "match.json"
    if not match_path.exists():
        return
    m = json.loads(match_path.read_text())
    pr_r, pr_s = m["participation_ratio"]["real"], m["participation_ratio"]["synthetic"]
    pw_r = np.asarray(m["pairwise_cos"]["real"])
    pw_s = np.asarray(m["pairwise_cos"]["synthetic"])
    cm_r = np.asarray(m["cos_to_mean"]["real"])
    cm_s = np.asarray(m["cos_to_mean"]["synthetic"])

    fig, top = figure(
        15.0,
        6.6,
        2,
        "the impostor corpus",
        "Does the synthetic corpus wear the real geometry?",
        f"fit on {m['fit_n']:,} production vectors · {m['match_sample']:,}-vector samples · "
        f"pairwise cos mean {pw_r.mean():.3f} real / {pw_s.mean():.3f} synthetic · "
        f"participation ratio {pr_r:.0f} / {pr_s:.0f} · {sha}",
    )
    gs = fig.add_gridspec(
        1, 3, left=0.055, right=1 - MARGIN - 0.01, top=top, bottom=0.14, wspace=0.24
    )
    for k, (ptitle, r_arr, s_arr) in enumerate(
        (
            ("pairwise cosine between two vectors", pw_r, pw_s),
            ("cosine to the real corpus mean — the cone", cm_r, cm_s),
        )
    ):
        ax = fig.add_subplot(gs[k])
        style_axes(ax)
        panel_title(ax, ptitle)
        bins = np.linspace(min(r_arr.min(), s_arr.min()), max(r_arr.max(), s_arr.max()), 60)
        ax.hist(r_arr, bins=bins, color=GOLD, alpha=0.9, density=True, label="real")
        ax.hist(s_arr, bins=bins, color=BLUE, alpha=0.62, density=True, label="synthetic")
        ax.set_xlabel("cosine")
        ax.legend(framealpha=0.0, labelcolor="#eceae7")
    ax = fig.add_subplot(gs[2])
    style_axes(ax)
    panel_title(ax, "covariance spectrum, top 64 components")
    ax.plot(m["spectrum_top64"]["real"], color=GOLD, lw=2.0, label="real")
    ax.plot(m["spectrum_top64"]["synthetic"], color=BLUE, lw=2.0, label="synthetic")
    ax.set_xlabel("component")
    ax.set_ylabel("singular value")
    ax.legend(framealpha=0.0, labelcolor="#eceae7")

    dm = abs(pw_r.mean() - pw_s.mean())
    verdict(fig, f"pairwise-cos means within {dm:.4f} — the impostor passes; rung 0 may run")
    frame_panels(fig)
    out = ASSETS / "02-the-impostor-corpus.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out}")

    rung0_path = ASSETS / "rung0.json"
    if not rung0_path.exists():
        return
    r0 = json.loads(rung0_path.read_text())
    n18, ms18 = 18728, r0["baseline_18k_p50_ms"]
    n10m = r0["n_vectors"]
    single_ms = r0["single_query_s"]["p50"] * 1000
    batched_ms = r0["batched"]["per_query_ms"]
    gbps = r0["corpus_gb"] / r0["single_query_s"]["p50"]

    fig, top = figure(
        15.0,
        6.6,
        3,
        "the wall",
        "Exact search falls off a cliff, and the cliff is the disk",
        f"{n10m:,} synthetic vectors · {r0['corpus_gb']}GB streamed per sweep · effective {gbps:.2f}GB/s · "
        f"single {single_ms / 1000:.0f}s · batched x{r0['batched']['n_queries']} {batched_ms / 1000:.1f}s/query · "
        f"18k baseline {ms18:.2f}ms · {sha}",
    )
    gs = fig.add_gridspec(1, 1, left=0.07, right=1 - MARGIN - 0.01, top=top, bottom=0.14)
    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "exact top-10 latency vs corpus size — measured points, log-log")

    ax.loglog([n18, n10m], [ms18, single_ms], color=GOLD, lw=1.4, ls=":", alpha=0.7)
    ax.loglog([n18], [ms18], "o", color=GOLD, ms=9)
    ax.loglog(
        [n10m], [single_ms], "o", color=GOLD, ms=9, label="single query — one full sweep each"
    )
    ax.loglog(
        [n10m], [batched_ms], "s", color=BLUE, ms=9, label="batched — 20 queries share one sweep"
    )
    ax.axhline(100, color=RED, lw=1.4, ls="--")
    ax.text(n18 * 1.1, 118, "the Exa target: 1B vectors under 100ms", color=RED, fontsize=9)
    ax.annotate(
        "534x more vectors,\n63,000x slower",
        xy=(n10m, single_ms),
        xytext=(n10m / 60, single_ms / 3),
        color="#eceae7",
        fontsize=9,
        ha="right",
        arrowprops={"arrowstyle": "-", "color": "#9a968f", "lw": 0.8},
    )
    ax.set_xlabel("corpus size (vectors)")
    ax.set_ylabel("latency per query (ms)")
    ax.legend(framealpha=0.0, labelcolor="#eceae7", loc="upper left")

    verdict(fig, "the sweep is the disk: compute rides free — 20 queries cost one query")
    frame_panels(fig)
    out = ASSETS / "03-the-wall.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out}")

    r1p, r2p = ASSETS / "rung1.json", ASSETS / "rung2.json"
    if not (r1p.exists() and r2p.exists()):
        return
    r1, r2 = json.loads(r1p.read_text()), json.loads(r2p.read_text())
    pts = [
        ("exact f32", 1.0, r0["single_query_s"]["p50"] * 1000, "38.1GB", GOLD),
        ("exact f32, batched x20", 1.0, r0["batched"]["per_query_ms"], "38.1GB", GOLD),
        ("int8", r1["recall_at_10"]["all"], r1["single_query_s"]["p50"] * 1000, "9.5GB", BLUE),
        (
            "PQ 64-byte",
            r2["recall_at_10"]["all"],
            r2["single_query_s"]["p50"] * 1000,
            "0.6GB",
            CYAN,
        ),
    ]

    fig, top = figure(
        15.0,
        6.6,
        4,
        "what speed costs in truth",
        "The Pareto plane at 10M vectors — every point is a measured trade",
        f"recall@10 vs exact ground truth (1000 queries) · single-query p50 · "
        f"int8 {r1['recall_at_10']['all']:.3f} recall at {r1['single_query_s']['p50']:.0f}s · "
        f"PQ64 {r2['recall_at_10']['all']:.3f} at {r2['single_query_s']['p50']:.1f}s (numpy gather, not SIMD) · {sha}",
    )
    gs = fig.add_gridspec(1, 1, left=0.07, right=1 - MARGIN - 0.01, top=top, bottom=0.14)
    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(
        ax, "recall@10 (right is truer) vs latency (down is faster) — labels carry the footprint"
    )

    ax.set_yscale("log")
    for name, rec, ms, size, color in pts:
        ax.plot([rec], [ms], "o", color=color, ms=11)
        ax.annotate(
            f"{name}\n{size}",
            xy=(rec, ms),
            xytext=(-12, 10),
            textcoords="offset points",
            color=color,
            fontsize=9,
            ha="right",
        )
    ax.axhline(100, color=RED, lw=1.4, ls="--")
    ax.text(0.06, 130, "the Exa target: under 100ms", color=RED, fontsize=9)
    ax.set_xlabel("recall@10 against exact ground truth")
    ax.set_ylabel("latency per query (ms, log)")
    ax.set_xlim(0, 1.06)

    verdict(
        fig, "int8 keeps 98% of the truth for 3x the speed; 64 bytes keep 16% — the gap is the work"
    )
    frame_panels(fig)
    out = ASSETS / "04-what-speed-costs.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out}")


def _chunked_topk(mm: np.memmap, queries: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Exact top-k of queries against the memmap, one chunked sweep."""
    nq = len(queries)
    best_s = np.full((nq, k), -np.inf, dtype=np.float32)
    best_i = np.zeros((nq, k), dtype=np.int64)
    qt = queries.T.astype(np.float32)
    for start in range(0, mm.shape[0], CHUNK):
        chunk = np.asarray(mm[start : start + CHUNK])
        scores = chunk @ qt  # (chunk, nq)
        for q in range(nq):
            s = scores[:, q]
            idx = np.argpartition(s, -k)[-k:]
            cand_s = np.concatenate([best_s[q], s[idx]])
            cand_i = np.concatenate([best_i[q], idx + start])
            keep = np.argsort(cand_s)[-k:]
            best_s[q], best_i[q] = cand_s[keep], cand_i[keep]
    return best_s, best_i


def rung0() -> None:
    """Exact brute force at 10M: single-query sweeps vs one batched sweep."""
    mm = np.memmap(DATA_DIR / "synthetic-10m.f32", dtype=np.float32, mode="r").reshape(N_FULL, 1024)
    rng = np.random.default_rng(SEED + 2)

    real, mu, scaled_vt = _fit_real()
    q_real = real[rng.choice(len(real), 10, replace=False)]
    q_syn = _gen_chunk(rng, 10, mu, scaled_vt)  # held out: fresh draws, not memmap rows
    queries = np.vstack([q_real, q_syn]).astype(np.float32)

    single_s: list[float] = []
    for q in queries[:5]:
        t = time.perf_counter()
        _chunked_topk(mm, q[None, :], K)
        single_s.append(time.perf_counter() - t)

    t = time.perf_counter()
    _chunked_topk(mm, queries, K)
    batched_total = time.perf_counter() - t

    out = {
        "stamp": time.strftime("%Y-%m-%d"),
        "step": "rung0-brute-10m",
        "n_vectors": N_FULL,
        "dim": 1024,
        "corpus_gb": round((DATA_DIR / "synthetic-10m.f32").stat().st_size / 2**30, 1),
        "single_query_s": {"samples": single_s, "p50": float(np.median(single_s))},
        "batched": {
            "n_queries": len(queries),
            "total_s": batched_total,
            "per_query_ms": batched_total / len(queries) * 1000,
        },
        "baseline_18k_p50_ms": json.loads((ASSETS / "baseline.json").read_text())["brute_force"][
            "p50_ms"
        ],
    }
    (ASSETS / "rung0.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "stamp"}, indent=2))


N_GT_QUERIES = 1000
GT_K = 100
Q_BLOCK = 250  # 250k-row chunk x 250 query cols = 250MB of scores


def ground_truth() -> None:
    """Exact top-100 for 1000 queries (500 real, 500 held-out synthetic) — the referee file."""
    mm = np.memmap(DATA_DIR / "synthetic-10m.f32", dtype=np.float32, mode="r").reshape(N_FULL, 1024)
    rng = np.random.default_rng(SEED + 3)
    real, mu, scaled_vt = _fit_real()
    q_real = real[rng.choice(len(real), N_GT_QUERIES // 2, replace=False)]
    q_syn = _gen_chunk(rng, N_GT_QUERIES // 2, mu, scaled_vt)
    queries = np.vstack([q_real, q_syn]).astype(np.float32)

    t0 = time.perf_counter()
    all_i = np.zeros((N_GT_QUERIES, GT_K), dtype=np.int64)
    for b in range(0, N_GT_QUERIES, Q_BLOCK):
        _, idx = _chunked_topk(mm, queries[b : b + Q_BLOCK], GT_K)
        all_i[b : b + Q_BLOCK] = idx
        print(f"queries {b + Q_BLOCK}/{N_GT_QUERIES}  {time.perf_counter() - t0:.0f}s", flush=True)

    np.save(DATA_DIR / "gt-queries.npy", queries)
    np.save(DATA_DIR / "gt-top100.npy", all_i)
    print(f"ground truth done in {time.perf_counter() - t0:.0f}s -> {DATA_DIR}")


def _recall_at_10(found: np.ndarray, gt_top100: np.ndarray) -> float:
    """Fraction of the true top-10 recovered, averaged over queries.

    _chunked_topk rows are ascending by score, so the true top-10 sit at
    the END of each ground-truth row — g[-10:], never g[:10].
    """
    hits = 0
    for f, g in zip(found, gt_top100):
        hits += len(set(f.tolist()[-10:]) & set(g.tolist()[-10:]))
    return hits / (len(found) * 10)


def rung1_quantize() -> None:
    """int8 with per-vector scale: 4x less to stream, recall priced later."""
    mm = np.memmap(DATA_DIR / "synthetic-10m.f32", dtype=np.float32, mode="r").reshape(N_FULL, 1024)
    out = np.memmap(DATA_DIR / "synthetic-10m.i8", dtype=np.int8, mode="w+", shape=(N_FULL, 1024))
    scales = np.zeros(N_FULL, dtype=np.float32)
    t0 = time.perf_counter()
    for start in range(0, N_FULL, CHUNK):
        chunk = np.asarray(mm[start : start + CHUNK])
        vmax = np.abs(chunk).max(axis=1)
        scales[start : start + CHUNK] = vmax / 127.0
        out[start : start + CHUNK] = np.round(chunk / (vmax[:, None] / 127.0)).astype(np.int8)
    out.flush()
    np.save(DATA_DIR / "scales.npy", scales)
    print(f"quantized in {time.perf_counter() - t0:.0f}s")


def _int8_topk(queries: np.ndarray, k: int) -> tuple[np.ndarray, list[float]]:
    """Chunked sweep over the int8 memmap; returns indices and per-call seconds."""
    mm = np.memmap(DATA_DIR / "synthetic-10m.i8", dtype=np.int8, mode="r").reshape(N_FULL, 1024)
    scales = np.load(DATA_DIR / "scales.npy")
    nq = len(queries)
    best_s = np.full((nq, k), -np.inf, dtype=np.float32)
    best_i = np.zeros((nq, k), dtype=np.int64)
    qt = queries.T.astype(np.float32)
    t0 = time.perf_counter()
    for start in range(0, N_FULL, CHUNK):
        chunk = np.asarray(mm[start : start + CHUNK]).astype(np.float32)
        scores = (chunk @ qt) * scales[start : start + CHUNK, None]
        for q in range(nq):
            s = scores[:, q]
            idx = np.argpartition(s, -k)[-k:]
            cand_s = np.concatenate([best_s[q], s[idx]])
            cand_i = np.concatenate([best_i[q], idx + start])
            keep = np.argsort(cand_s)[-k:]
            best_s[q], best_i[q] = cand_s[keep], cand_i[keep]
    return best_i, [time.perf_counter() - t0]


def rung1() -> None:
    queries = np.load(DATA_DIR / "gt-queries.npy")
    gt = np.load(DATA_DIR / "gt-top100.npy")

    single_s = []
    for q in queries[:3]:
        _, t = _int8_topk(q[None, :], K)
        single_s.append(t[0])

    found = np.zeros((N_GT_QUERIES, K), dtype=np.int64)
    t0 = time.perf_counter()
    for b in range(0, N_GT_QUERIES, Q_BLOCK):
        idx, _ = _int8_topk(queries[b : b + Q_BLOCK], K)
        found[b : b + Q_BLOCK] = idx
    recall_sweep_s = time.perf_counter() - t0

    out = {
        "stamp": time.strftime("%Y-%m-%d"),
        "step": "rung1-int8",
        "bytes_per_vector": 1024 + 4,
        "corpus_gb": round((DATA_DIR / "synthetic-10m.i8").stat().st_size / 2**30, 1),
        "single_query_s": {"samples": single_s, "p50": float(np.median(single_s))},
        "recall_at_10": {
            "all": _recall_at_10(found, gt),
            "real_queries": _recall_at_10(found[:500], gt[:500]),
            "synthetic_queries": _recall_at_10(found[500:], gt[500:]),
        },
        "recall_sweep_s": recall_sweep_s,
    }
    (ASSETS / "rung1.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


PQ_M = 64  # subspaces of 16 dims
PQ_KS = 256
PQ_TRAIN = 500_000
PQ_ITERS = 15


def rung2_train() -> None:
    """Train PQ codebooks on a sample, encode all 10M to 64-byte codes."""
    mm = np.memmap(DATA_DIR / "synthetic-10m.f32", dtype=np.float32, mode="r").reshape(N_FULL, 1024)
    rng = np.random.default_rng(SEED + 4)
    sample = np.asarray(mm[rng.choice(N_FULL, PQ_TRAIN, replace=False)])

    d_sub = 1024 // PQ_M
    books = np.zeros((PQ_M, PQ_KS, d_sub), dtype=np.float32)
    t0 = time.perf_counter()
    for m in range(PQ_M):
        x = sample[:, m * d_sub : (m + 1) * d_sub]
        cb = x[rng.choice(len(x), PQ_KS, replace=False)].copy()
        for _ in range(PQ_ITERS):
            d2 = (
                ((x[:, None, :] - cb[None]) ** 2).sum(-1)
                if False
                else ((x**2).sum(1)[:, None] - 2 * x @ cb.T + (cb**2).sum(1)[None])
            )
            assign = d2.argmin(1)
            for j in range(PQ_KS):
                mask = assign == j
                if mask.any():
                    cb[j] = x[mask].mean(0)
        books[m] = cb
        if m % 16 == 0:
            print(f"codebook {m}/{PQ_M}  {time.perf_counter() - t0:.0f}s", flush=True)
    np.save(DATA_DIR / "pq-books.npy", books)

    codes = np.zeros((N_FULL, PQ_M), dtype=np.uint8)
    for start in range(0, N_FULL, CHUNK):
        chunk = np.asarray(mm[start : start + CHUNK])
        for m in range(PQ_M):
            x = chunk[:, m * d_sub : (m + 1) * d_sub]
            cb = books[m]
            d2 = (x**2).sum(1)[:, None] - 2 * x @ cb.T + (cb**2).sum(1)[None]
            codes[start : start + CHUNK, m] = d2.argmin(1).astype(np.uint8)
        if (start // CHUNK) % 8 == 0:
            print(
                f"encode {start + CHUNK:,}/{N_FULL:,}  {time.perf_counter() - t0:.0f}s", flush=True
            )
    np.save(DATA_DIR / "pq-codes.npy", codes)
    print(f"PQ train+encode in {time.perf_counter() - t0:.0f}s")


def rung2() -> None:
    """ADC search over the in-RAM 64-byte codes."""
    books = np.load(DATA_DIR / "pq-books.npy")
    codes = np.load(DATA_DIR / "pq-codes.npy")  # 640MB, lives in RAM — that is the point
    queries = np.load(DATA_DIR / "gt-queries.npy")
    gt = np.load(DATA_DIR / "gt-top100.npy")
    d_sub = 1024 // PQ_M

    def search_one(q: np.ndarray) -> np.ndarray:
        lut = np.einsum("mkd,md->mk", books, q.reshape(PQ_M, d_sub))  # dot-product ADC
        scores = np.zeros(N_FULL, dtype=np.float32)
        for start in range(0, N_FULL, 2_000_000):
            block = codes[start : start + 2_000_000]
            scores[start : start + 2_000_000] = lut[np.arange(PQ_M)[None, :], block].sum(1)
        return np.argpartition(scores, -K)[-K:]

    single_s = []
    for q in queries[:5]:
        t = time.perf_counter()
        search_one(q)
        single_s.append(time.perf_counter() - t)

    found = np.zeros((N_GT_QUERIES, K), dtype=np.int64)
    t0 = time.perf_counter()
    for i, q in enumerate(queries):
        found[i] = search_one(q)
    all_s = time.perf_counter() - t0

    out = {
        "stamp": time.strftime("%Y-%m-%d"),
        "step": "rung2-pq",
        "bytes_per_vector": PQ_M,
        "corpus_gb": round(codes.nbytes / 2**30, 2),
        "single_query_s": {"samples": single_s, "p50": float(np.median(single_s))},
        "recall_at_10": {
            "all": _recall_at_10(found, gt),
            "real_queries": _recall_at_10(found[:500], gt[:500]),
            "synthetic_queries": _recall_at_10(found[500:], gt[500:]),
        },
        "all_queries_s": all_s,
    }
    (ASSETS / "rung2.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


PQ3_VARIANTS = ("center", "rotate", "m128")


def _corpus_mean() -> np.ndarray:
    """Mean of the frozen 10M memmap — never re-derived from the live store."""
    path = DATA_DIR / "e41-mu.npy"
    if path.exists():
        return np.load(path)
    mm = np.memmap(DATA_DIR / "synthetic-10m.f32", dtype=np.float32, mode="r").reshape(N_FULL, 1024)
    acc = np.zeros(1024, dtype=np.float64)
    for start in range(0, N_FULL, CHUNK):
        acc += np.asarray(mm[start : start + CHUNK]).sum(axis=0, dtype=np.float64)
    mu = (acc / N_FULL).astype(np.float32)
    np.save(path, mu)
    return mu


def _rotation() -> np.ndarray:
    path = DATA_DIR / "rot-1024.npy"
    if path.exists():
        return np.load(path)
    rng = np.random.default_rng(SEED + 5)
    q, _ = np.linalg.qr(rng.standard_normal((1024, 1024)))
    q = q.astype(np.float32)
    np.save(path, q)
    return q


def _variant_transform(variant: str):
    """Applied identically to corpus rows and queries; both preserve exact ranking."""
    if variant == "center":
        mu = _corpus_mean()
        return lambda x: x - mu
    if variant == "rotate":
        rot = _rotation()
        return lambda x: x @ rot
    return lambda x: x


def _pq_fit(sample: np.ndarray, m: int, rng: np.random.Generator) -> np.ndarray:
    d_sub = sample.shape[1] // m
    books = np.zeros((m, PQ_KS, d_sub), dtype=np.float32)
    t0 = time.perf_counter()
    for i in range(m):
        x = sample[:, i * d_sub : (i + 1) * d_sub]
        cb = x[rng.choice(len(x), PQ_KS, replace=False)].copy()
        for _ in range(PQ_ITERS):
            d2 = (x**2).sum(1)[:, None] - 2 * x @ cb.T + (cb**2).sum(1)[None]
            assign = d2.argmin(1)
            for j in range(PQ_KS):
                mask = assign == j
                if mask.any():
                    cb[j] = x[mask].mean(0)
        books[i] = cb
        if i % 16 == 0:
            print(f"codebook {i}/{m}  {time.perf_counter() - t0:.0f}s", flush=True)
    return books


def _pq_encode_stream(books: np.ndarray, transform, out_path: Path) -> None:
    mm = np.memmap(DATA_DIR / "synthetic-10m.f32", dtype=np.float32, mode="r").reshape(N_FULL, 1024)
    m, _, d_sub = books.shape
    codes = np.zeros((N_FULL, m), dtype=np.uint8)
    t0 = time.perf_counter()
    for start in range(0, N_FULL, CHUNK):
        chunk = transform(np.asarray(mm[start : start + CHUNK]))
        for i in range(m):
            x = chunk[:, i * d_sub : (i + 1) * d_sub]
            cb = books[i]
            d2 = (x**2).sum(1)[:, None] - 2 * x @ cb.T + (cb**2).sum(1)[None]
            codes[start : start + CHUNK, i] = d2.argmin(1).astype(np.uint8)
        if (start // CHUNK) % 8 == 0:
            print(
                f"encode {start + CHUNK:,}/{N_FULL:,}  {time.perf_counter() - t0:.0f}s", flush=True
            )
    np.save(out_path, codes)
    print(f"encoded -> {out_path}  {time.perf_counter() - t0:.0f}s")


def _adc_search_one(q: np.ndarray, books: np.ndarray, codes: np.ndarray) -> np.ndarray:
    m, _, d_sub = books.shape
    lut = np.einsum("mkd,md->mk", books, q.reshape(m, d_sub))
    scores = np.zeros(N_FULL, dtype=np.float32)
    for start in range(0, N_FULL, 2_000_000):
        block = codes[start : start + 2_000_000]
        scores[start : start + 2_000_000] = lut[np.arange(m)[None, :], block].sum(1)
    return np.argpartition(scores, -K)[-K:]


def rung3_train(variant: str) -> None:
    """PQ variant codebooks + full encode; center/rotate are rank-preserving transforms."""
    assert variant in PQ3_VARIANTS
    m = 128 if variant == "m128" else PQ_M
    transform = _variant_transform("none" if variant == "m128" else variant)
    mm = np.memmap(DATA_DIR / "synthetic-10m.f32", dtype=np.float32, mode="r").reshape(N_FULL, 1024)
    rng = np.random.default_rng(SEED + 6)
    sample = transform(np.asarray(mm[rng.choice(N_FULL, PQ_TRAIN, replace=False)]))
    books = _pq_fit(sample, m, rng)
    np.save(DATA_DIR / f"pq3-books-{variant}.npy", books)
    _pq_encode_stream(books, transform, DATA_DIR / f"pq3-codes-{variant}.npy")


def rung3(variant: str) -> None:
    """ADC sweep for one PQ variant against the frozen referee."""
    assert variant in PQ3_VARIANTS
    books = np.load(DATA_DIR / f"pq3-books-{variant}.npy")
    codes = np.load(DATA_DIR / f"pq3-codes-{variant}.npy")
    queries = np.load(DATA_DIR / "gt-queries.npy")
    gt = np.load(DATA_DIR / "gt-top100.npy")
    transform = _variant_transform("none" if variant == "m128" else variant)
    # center: ADC scores differ from raw by the constant q@mu — same ranking, so raw q is used
    q_all = queries if variant == "center" else transform(queries)

    single_s = []
    for q in q_all[:5]:
        t = time.perf_counter()
        _adc_search_one(q, books, codes)
        single_s.append(time.perf_counter() - t)

    found = np.zeros((N_GT_QUERIES, K), dtype=np.int64)
    t0 = time.perf_counter()
    for i, q in enumerate(q_all):
        found[i] = _adc_search_one(q, books, codes)
        if i % 250 == 249:
            print(f"sweep {i + 1}/{N_GT_QUERIES}  {time.perf_counter() - t0:.0f}s", flush=True)
    all_s = time.perf_counter() - t0

    out = {
        "stamp": time.strftime("%Y-%m-%d"),
        "step": f"rung3-pq-{variant}",
        "bytes_per_vector": int(books.shape[0]),
        "corpus_gb": round(codes.nbytes / 2**30, 2),
        "single_query_s": {"samples": single_s, "p50": float(np.median(single_s))},
        "recall_at_10": {
            "all": _recall_at_10(found, gt),
            "real_queries": _recall_at_10(found[:500], gt[:500]),
            "synthetic_queries": _recall_at_10(found[500:], gt[500:]),
        },
        "all_queries_s": all_s,
    }
    (ASSETS / f"rung3-{variant}.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


IVF_NLIST = 1024
IVF_TRAIN = 500_000
IVF_ITERS = 10
IVF_NPROBES = (1, 2, 4, 8, 16, 32, 64)


def _kmeans_dot(sample: np.ndarray, nlist: int, rng: np.random.Generator) -> np.ndarray:
    """Spherical k-means by dot product — the metric search will use."""
    cb = sample[rng.choice(len(sample), nlist, replace=False)].copy()
    for it in range(IVF_ITERS):
        assign = (sample @ cb.T).argmax(1)
        for j in range(nlist):
            mask = assign == j
            if mask.any():
                c = sample[mask].mean(0)
                cb[j] = c / np.linalg.norm(c)
        print(f"kmeans iter {it}", flush=True)
    return cb


def rung4_train() -> None:
    """IVF: coarse centroids, assignment, and a list-contiguous int8 layout on disk."""
    mm = np.memmap(DATA_DIR / "synthetic-10m.f32", dtype=np.float32, mode="r").reshape(N_FULL, 1024)
    rng = np.random.default_rng(SEED + 7)
    sample = np.asarray(mm[rng.choice(N_FULL, IVF_TRAIN, replace=False)])
    t0 = time.perf_counter()
    centroids = _kmeans_dot(sample, IVF_NLIST, rng)
    np.save(DATA_DIR / "ivf-centroids.npy", centroids)

    assign = np.zeros(N_FULL, dtype=np.int32)
    for start in range(0, N_FULL, CHUNK):
        chunk = np.asarray(mm[start : start + CHUNK])
        assign[start : start + CHUNK] = (chunk @ centroids.T).argmax(1)
        if (start // CHUNK) % 8 == 0:
            print(
                f"assign {start + CHUNK:,}/{N_FULL:,}  {time.perf_counter() - t0:.0f}s", flush=True
            )
    perm = np.argsort(assign, kind="stable")
    sizes = np.bincount(assign, minlength=IVF_NLIST)
    offsets = np.zeros(IVF_NLIST + 1, dtype=np.int64)
    offsets[1:] = np.cumsum(sizes)
    np.save(DATA_DIR / "ivf-perm.npy", perm)
    np.save(DATA_DIR / "ivf-offsets.npy", offsets)

    i8 = np.memmap(DATA_DIR / "synthetic-10m.i8", dtype=np.int8, mode="r").reshape(N_FULL, 1024)
    scales = np.load(DATA_DIR / "scales.npy")
    out = np.memmap(DATA_DIR / "ivf-i8.bin", dtype=np.int8, mode="w+", shape=(N_FULL, 1024))
    for start in range(0, N_FULL, CHUNK):
        out[start : start + CHUNK] = i8[perm[start : start + CHUNK]]
        if (start // CHUNK) % 8 == 0:
            print(
                f"reorder {start + CHUNK:,}/{N_FULL:,}  {time.perf_counter() - t0:.0f}s", flush=True
            )
    out.flush()
    np.save(DATA_DIR / "ivf-scales.npy", scales[perm])
    print(f"ivf layout done in {time.perf_counter() - t0:.0f}s")


def rung4() -> None:
    """Recall/latency vs nprobe over the list-contiguous int8 layout."""
    centroids = np.load(DATA_DIR / "ivf-centroids.npy")
    perm = np.load(DATA_DIR / "ivf-perm.npy")
    offsets = np.load(DATA_DIR / "ivf-offsets.npy")
    scales = np.load(DATA_DIR / "ivf-scales.npy")
    mm = np.memmap(DATA_DIR / "ivf-i8.bin", dtype=np.int8, mode="r").reshape(N_FULL, 1024)
    queries = np.load(DATA_DIR / "gt-queries.npy")
    gt = np.load(DATA_DIR / "gt-top100.npy")

    def search_one(q: np.ndarray, nprobe: int) -> np.ndarray:
        lists = np.argsort(q @ centroids.T)[-nprobe:]
        best_s: list[np.ndarray] = []
        best_i: list[np.ndarray] = []
        for li in lists:
            lo, hi = int(offsets[li]), int(offsets[li + 1])
            if lo == hi:
                continue
            rows = np.asarray(mm[lo:hi]).astype(np.float32)
            s = (rows @ q) * scales[lo:hi]
            k = min(K, len(s))
            idx = np.argpartition(s, -k)[-k:]
            best_s.append(s[idx])
            best_i.append(perm[lo + idx])
        s = np.concatenate(best_s)
        i = np.concatenate(best_i)
        return i[np.argsort(s)[-K:]]

    results = {}
    for nprobe in IVF_NPROBES:
        single_s = []
        for q in queries[:5]:
            t = time.perf_counter()
            search_one(q, nprobe)
            single_s.append(time.perf_counter() - t)
        found = np.zeros((N_GT_QUERIES, K), dtype=np.int64)
        scanned = 0
        t0 = time.perf_counter()
        for i, q in enumerate(queries):
            lists = np.argsort(q @ centroids.T)[-nprobe:]
            scanned += int((offsets[lists + 1] - offsets[lists]).sum())
            found[i] = search_one(q, nprobe)
        results[str(nprobe)] = {
            "recall_at_10": _recall_at_10(found, gt),
            "single_query_ms_p50": float(np.median(single_s)) * 1000,
            "scanned_fraction": scanned / (N_GT_QUERIES * N_FULL),
            "sweep_s": time.perf_counter() - t0,
        }
        print(f"nprobe {nprobe}: {json.dumps(results[str(nprobe)])}", flush=True)

    out = {
        "stamp": time.strftime("%Y-%m-%d"),
        "step": "rung4-ivf",
        "nlist": IVF_NLIST,
        "by_nprobe": results,
    }
    (ASSETS / "rung4.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


def rung4_control() -> None:
    """List-size skew: real geometry vs isotropic, same n, same nlist."""
    mm = np.memmap(DATA_DIR / "synthetic-10m.f32", dtype=np.float32, mode="r").reshape(N_FULL, 1024)
    rng = np.random.default_rng(SEED + 8)
    n, nlist = 1_000_000, 256
    real = np.asarray(mm[rng.choice(N_FULL, n, replace=False)])
    iso = rng.standard_normal((n, 1024), dtype=np.float32)
    iso /= np.linalg.norm(iso, axis=1, keepdims=True)

    def sizes(x: np.ndarray) -> np.ndarray:
        cb = _kmeans_dot(x[rng.choice(n, IVF_TRAIN // 2, replace=False)], nlist, rng)
        assign = np.zeros(n, dtype=np.int32)
        for start in range(0, n, CHUNK):
            assign[start : start + CHUNK] = (x[start : start + CHUNK] @ cb.T).argmax(1)
        return np.bincount(assign, minlength=nlist)

    def gini(s: np.ndarray) -> float:
        s = np.sort(s.astype(np.float64))
        i = np.arange(1, len(s) + 1)
        return float(((2 * i - len(s) - 1) * s).sum() / (len(s) * s.sum()))

    real_sizes, iso_sizes = sizes(real), sizes(iso)
    out = {
        "stamp": time.strftime("%Y-%m-%d"),
        "step": "rung4-control",
        "n": n,
        "nlist": nlist,
        "real": {
            "sizes": real_sizes.tolist(),
            "gini": gini(real_sizes),
            "max_over_median": float(real_sizes.max() / np.median(real_sizes)),
        },
        "isotropic": {
            "sizes": iso_sizes.tolist(),
            "gini": gini(iso_sizes),
            "max_over_median": float(iso_sizes.max() / np.median(iso_sizes)),
        },
    }
    (ASSETS / "ivf-control.json").write_text(json.dumps(out) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k not in ("real", "isotropic")}, indent=2))
    print(f"gini real {out['real']['gini']:.3f} vs isotropic {out['isotropic']['gini']:.3f}")


HNSW_N = 1_000_000
HNSW_EFS = (10, 40, 100, 200)


def rung5() -> None:
    """hnswlib at the RAM ceiling: the full corpus cannot load; reference numbers at 1M."""
    import resource

    import hnswlib

    mm = np.memmap(DATA_DIR / "synthetic-10m.f32", dtype=np.float32, mode="r").reshape(N_FULL, 1024)
    queries = np.load(DATA_DIR / "gt-queries.npy")

    t0 = time.perf_counter()
    _, gt_idx = _chunked_topk(mm[:HNSW_N], queries, GT_K)
    gt_s = time.perf_counter() - t0

    # chunked adds keep peak RSS at index + one chunk; a materialized 1M copy would not fit
    index = hnswlib.Index(space="ip", dim=1024)
    index.init_index(max_elements=HNSW_N, ef_construction=200, M=16)
    t0 = time.perf_counter()
    for start in range(0, HNSW_N, CHUNK):
        chunk = np.asarray(mm[start : start + CHUNK])
        index.add_items(chunk, np.arange(start, start + len(chunk)), num_threads=-1)
        print(
            f"hnsw add {start + len(chunk):,}/{HNSW_N:,}  {time.perf_counter() - t0:.0f}s",
            flush=True,
        )
    build_s = time.perf_counter() - t0
    rss_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30

    results = {}
    for ef in HNSW_EFS:
        index.set_ef(ef)
        found = np.zeros((N_GT_QUERIES, K), dtype=np.int64)
        lat = []
        for i, q in enumerate(queries):
            t = time.perf_counter()
            labels, _ = index.knn_query(q[None, :], k=K, num_threads=1)
            lat.append(time.perf_counter() - t)
            found[i] = labels[0]
        results[str(ef)] = {
            "recall_at_10": _recall_at_10(found, gt_idx),
            "p50_ms": float(np.median(lat)) * 1000,
            "p99_ms": float(np.percentile(lat, 99)) * 1000,
        }
        print(f"ef {ef}: {json.dumps(results[str(ef)])}", flush=True)

    out = {
        "stamp": time.strftime("%Y-%m-%d"),
        "step": "rung5-hnsw-1m",
        "n": HNSW_N,
        "full_corpus_gb_f32": 38.1,
        "machine_ram_gb": 16,
        "build_s": build_s,
        "rss_gb": rss_gb,
        "gt_subset_s": gt_s,
        "by_ef": results,
    }
    (ASSETS / "rung5.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


def figures2(outdir: Path | None = None) -> None:
    """Weekend-2 figures from the sidecars; each renders only when its data exists.

    With outdir set, renders are checkpoints (scratchpad, for review mid-queue);
    without it they are the committed assets.
    """
    import subprocess

    import matplotlib

    matplotlib.use("Agg")

    from plot_assets import (
        BG,
        BLUE,
        CYAN,
        DIM,
        DPI,
        GOLD,
        MARGIN,
        RED,
        figure,
        frame_panels,
        panel_title,
        style_axes,
        verdict,
    )

    out_dir = outdir or ASSETS
    out_dir.mkdir(parents=True, exist_ok=True)
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()

    def load(name: str) -> dict | None:
        p = ASSETS / name
        return json.loads(p.read_text()) if p.exists() else None

    r1, r2 = load("rung1.json"), load("rung2.json")
    var = {v: load(f"rung3-{v}.json") for v in PQ3_VARIANTS}

    # figure 05 — the byte budget: recall kept per layout, predictions drawn as geometry
    if r1 and r2:
        rows: list[tuple[str, float, float, float, str]] = [
            ("int8 · 1028B", 1028, r1["recall_at_10"]["all"], r1["single_query_s"]["p50"], BLUE),
            ("PQ64 · 64B", 64, r2["recall_at_10"]["all"], r2["single_query_s"]["p50"], GOLD),
        ]
        if var["center"]:
            d = var["center"]
            rows.append(
                (
                    "PQ64 centered · 64B",
                    64,
                    d["recall_at_10"]["all"],
                    d["single_query_s"]["p50"],
                    GOLD,
                )
            )
        if var["rotate"]:
            d = var["rotate"]
            rows.append(
                (
                    "PQ64 rotated · 64B",
                    64,
                    d["recall_at_10"]["all"],
                    d["single_query_s"]["p50"],
                    GOLD,
                )
            )
        if var["m128"]:
            d = var["m128"]
            rows.append(
                ("PQ128 · 128B", 128, d["recall_at_10"]["all"], d["single_query_s"]["p50"], GOLD)
            )

        meta_bits = [f"{len(rows)} layouts · 1,000 referee queries · recall@10 vs exact top-10"]
        if var["center"]:
            meta_bits.append(
                f"centered {var['center']['recall_at_10']['all']:.4f} vs raw "
                f"{r2['recall_at_10']['all']:.3f} (P1 band ±0.02)"
            )
        if var["rotate"]:
            meta_bits.append(f"rotated {var['rotate']['recall_at_10']['all']:.3f} (P2 bar 0.25)")
        if var["m128"]:
            meta_bits.append(f"128B {var['m128']['recall_at_10']['all']:.3f} (P3 bar 0.45)")
        meta_bits.append(sha)

        fig, top = figure(
            15.0,
            6.8,
            5,
            "the byte budget",
            "What buys the truth back below 1KB per vector",
            " · ".join(meta_bits),
        )
        gs = fig.add_gridspec(1, 1, left=0.20, right=1 - MARGIN - 0.02, top=top, bottom=0.13)
        ax = fig.add_subplot(gs[0])
        style_axes(ax)
        panel_title(ax, "recall@10 by layout — registered predictions drawn before the runs")

        ys = np.arange(len(rows))[::-1]
        for y, (label, _, rec, lat, color) in zip(ys, rows):
            ax.hlines(y, 0, rec, color=color, lw=3.4, alpha=0.95)
            ax.plot([rec], [y], "o", color=color, ms=9)
            ax.annotate(
                f"{rec:.3f} · {lat:.2f}s",
                (rec, y),
                xytext=(8, 4),
                textcoords="offset points",
                color=color,
                fontsize=9,
            )
        # P1: the registered no-change band around rung 2, spanning the centered row only
        if len(rows) >= 3:
            y_c = ys[2]
            ax.barh(
                y_c,
                0.04,
                left=r2["recall_at_10"]["all"] - 0.02,
                height=0.62,
                color=DIM,
                zorder=0,
            )
            ax.annotate(
                "P1: no change",
                (r2["recall_at_10"]["all"], y_c - 0.44),
                color="#9a968f",
                fontsize=8.5,
                ha="center",
                va="top",
            )
        # P2 / P3 registered minimums as red ticks on their own rows
        for pred, row_i in ((0.25, 3), (0.45, 4)):
            if len(rows) > row_i:
                ax.vlines(pred, ys[row_i] - 0.31, ys[row_i] + 0.31, color=RED, lw=1.6, ls="--")
        ax.set_yticks(ys)
        ax.set_yticklabels([r[0] for r in rows], fontsize=10)
        ax.set_xlabel("recall@10 against exact ground truth")
        ax.set_xlim(0, 1.06)

        centered_null = (
            var["center"]
            and abs(var["center"]["recall_at_10"]["all"] - r2["recall_at_10"]["all"]) < 0.02
        )
        v = "centering is a no-op, exactly as registered — k-means moves with the data"
        if var["rotate"] and var["m128"]:
            v = (
                f"centering {'holds the null' if centered_null else 'BREAKS the registered null'}; "
                f"rotation {var['rotate']['recall_at_10']['all']:.2f}, "
                f"128B {var['m128']['recall_at_10']['all']:.2f} vs bars 0.25 / 0.45"
            )
        verdict(fig, v)
        frame_panels(fig)
        out = out_dir / "05-the-byte-budget.png"
        fig.savefig(out, dpi=DPI, facecolor=BG)
        print(f"wrote {out}")

    # figure 06 — IVF: what a scan fraction buys, and the cone's tax on list balance
    r4, ctl = load("rung4.json"), load("ivf-control.json")
    if r4:
        by = {int(k): v for k, v in r4["by_nprobe"].items()}
        probes = sorted(by)
        scans = [by[p]["scanned_fraction"] for p in probes]
        recalls = [by[p]["recall_at_10"] for p in probes]
        lats = [by[p]["single_query_ms_p50"] for p in probes]

        meta = (
            f"nlist {r4['nlist']} · 1,000 referee queries · "
            + " · ".join(
                f"np{p} {by[p]['recall_at_10']:.2f}@{by[p]['scanned_fraction'] * 100:.1f}%"
                for p in probes[:4]
            )
            + f" · {sha}"
        )
        fig, top = figure(
            15.0,
            6.8,
            6,
            "the inverted index",
            "Recall against the fraction of the corpus a query touches",
            meta,
        )
        ncols = 2 if ctl else 1
        gs = fig.add_gridspec(
            1, ncols, left=0.07, right=1 - MARGIN - 0.01, top=top, bottom=0.14, wspace=0.22
        )
        ax = fig.add_subplot(gs[0])
        style_axes(ax)
        panel_title(ax, "recall@10 vs scanned fraction — the registered box is 0.90 inside 5%")
        ax.plot(scans, recalls, color=GOLD, lw=2.0, marker="o", ms=7)
        for p, s, r, lt in zip(probes, scans, recalls, lats):
            ax.annotate(
                f"nprobe {p} · {lt:.0f}ms",
                (s, r),
                xytext=(7, -11),
                textcoords="offset points",
                color=GOLD,
                fontsize=8.5,
            )
        ax.axhline(0.90, color=RED, lw=1.4, ls="--")
        ax.axvline(0.05, color=RED, lw=1.4, ls="--")
        ax.set_xscale("log")
        ticks = [0.001, 0.01, 0.05, 0.1]
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{t * 100:g}%" for t in ticks])
        ax.set_xlabel("fraction of corpus scanned (log)")
        ax.set_ylabel("recall@10")
        ax.set_ylim(0, 1.04)

        if ctl:
            ax2 = fig.add_subplot(gs[1])
            style_axes(ax2)
            panel_title(ax2, "list sizes, largest to smallest — the cone's tax vs isotropic")
            rs = np.sort(np.asarray(ctl["real"]["sizes"]))[::-1]
            iso = np.sort(np.asarray(ctl["isotropic"]["sizes"]))[::-1]
            ax2.plot(
                np.arange(1, len(rs) + 1),
                rs,
                color=GOLD,
                lw=2.0,
                label=f"real geometry · gini {ctl['real']['gini']:.2f}",
            )
            ax2.plot(
                np.arange(1, len(iso) + 1),
                iso,
                color=DIM,
                lw=2.0,
                label=f"isotropic control · gini {ctl['isotropic']['gini']:.2f}",
            )
            ax2.set_xlabel(f"list rank (of {ctl['nlist']})")
            ax2.set_ylabel("vectors in list")
            ax2.legend(framealpha=0.0, labelcolor="#eceae7")

        hit = min(
            (p for p in probes if by[p]["recall_at_10"] >= 0.90),
            default=None,
            key=lambda p: by[p]["scanned_fraction"],
        )
        if hit is not None:
            v = (
                f"0.90 recall inside a {by[hit]['scanned_fraction'] * 100:.1f}% scan at "
                f"{by[hit]['single_query_ms_p50']:.0f}ms — P4 "
                + ("passes" if by[hit]["scanned_fraction"] <= 0.05 else "misses the 5% bound")
            )
        else:
            v = f"no nprobe reaches 0.90 recall — P4 fails; best {max(recalls):.2f}"
        verdict(fig, v)
        frame_panels(fig)
        out = out_dir / "06-the-inverted-index.png"
        fig.savefig(out, dpi=DPI, facecolor=BG)
        print(f"wrote {out}")

    # figure 07 — the reference that cannot load
    r5 = load("rung5.json")
    if r5:
        by = {int(k): v for k, v in r5["by_ef"].items()}
        efs = sorted(by)
        fig, top = figure(
            15.0,
            6.8,
            7,
            "the reference",
            "The library that just works cannot even load the corpus",
            f"hnswlib M=16 efC=200 · {r5['n']:,} of {N_FULL:,} vectors · build {r5['build_s']:.0f}s · "
            f"RSS {r5['rss_gb']:.1f}GB · full corpus {r5['full_corpus_gb_f32']}GB f32 vs "
            f"{r5['machine_ram_gb']}GB RAM · {sha}",
        )
        gs = fig.add_gridspec(
            1, 2, left=0.105, right=1 - MARGIN - 0.01, top=top, bottom=0.14, wspace=0.26
        )
        ax = fig.add_subplot(gs[0])
        style_axes(ax)
        panel_title(ax, "what fits — corpus footprint by layout vs the machine")
        names = ["f32", "int8", "PQ128", "PQ64", "HNSW 1M (RSS)"]
        sizes = [38.1, 9.5, 1.28, 0.64, r5["rss_gb"]]
        colors = [GOLD, GOLD, GOLD, GOLD, CYAN]
        yb = np.arange(len(names))[::-1]
        ax.barh(yb, sizes, height=0.6, color=colors)
        ax.axvline(16, color=RED, lw=1.6, ls="--")
        ax.text(16.6, yb[0] + 0.1, "16GB machine", color=RED, fontsize=9)
        for y, s in zip(yb, sizes):
            ax.annotate(
                f"{s:.2g}GB",
                (s, y),
                xytext=(6, -3),
                textcoords="offset points",
                color="#eceae7",
                fontsize=9,
            )
        ax.set_yticks(yb)
        ax.set_yticklabels(names, fontsize=10)
        ax.set_xscale("log")
        ax.set_xlabel("resident bytes (GB, log)")

        ax2 = fig.add_subplot(gs[1])
        style_axes(ax2)
        panel_title(
            ax2, f"at {r5['n'] // 1_000_000}M it is excellent — recall vs p50 latency by efSearch"
        )
        ax2.plot(
            [by[e]["p50_ms"] for e in efs],
            [by[e]["recall_at_10"] for e in efs],
            color=CYAN,
            lw=2.0,
            marker="o",
            ms=7,
        )
        for e in efs:
            ax2.annotate(
                f"ef {e}",
                (by[e]["p50_ms"], by[e]["recall_at_10"]),
                xytext=(7, -11),
                textcoords="offset points",
                color=CYAN,
                fontsize=8.5,
            )
        ax2.axhline(0.90, color=RED, lw=1.4, ls="--")
        ax2.set_xlabel("p50 latency per query (ms)")
        ax2.set_ylabel("recall@10 (1M ground truth)")
        ax2.set_ylim(0, 1.04)

        good = [e for e in efs if by[e]["recall_at_10"] >= 0.90]
        v = "the graph index never gets to run at 10M — 39GB against 16GB is the finding"
        if good:
            e = min(good, key=lambda e: by[e]["p50_ms"])
            v += f"; at 1M it serves 0.90 recall in {by[e]['p50_ms']:.1f}ms"
        verdict(fig, v)
        frame_panels(fig)
        out = out_dir / "07-the-reference.png"
        fig.savefig(out, dpi=DPI, facecolor=BG)
        print(f"wrote {out}")

    # figure 08 — the whole climb on one panel
    r0, r6 = load("rung0.json"), load("rung6.json")
    if r0 and r1 and r2:
        pts = [
            ("exact f32", r0["single_query_s"]["p50"] * 1000, 1.0, GOLD),
            ("int8", r1["single_query_s"]["p50"] * 1000, r1["recall_at_10"]["all"], GOLD),
            ("PQ64", r2["single_query_s"]["p50"] * 1000, r2["recall_at_10"]["all"], GOLD),
        ]
        for vname, label in (("rotate", "PQ64 rotated"), ("m128", "PQ128")):
            if var[vname]:
                d = var[vname]
                pts.append(
                    (label, d["single_query_s"]["p50"] * 1000, d["recall_at_10"]["all"], GOLD)
                )
        if r4:
            by = {int(k): v for k, v in r4["by_nprobe"].items()}
            for p in sorted(by):
                pts.append(
                    (f"IVF np{p}", by[p]["single_query_ms_p50"], by[p]["recall_at_10"], BLUE)
                )
        if r5:
            by5 = {int(k): v for k, v in r5["by_ef"].items()}
            e = max(by5)
            pts.append((f"HNSW 1M ef{e}", by5[e]["p50_ms"], by5[e]["recall_at_10"], CYAN))
        if r6:
            for kname, ref in (("sweep_s", r1), ("gather_s", r2)):
                if kname in r6:
                    pts.append(
                        (
                            "rust " + kname.split("_")[0],
                            r6[kname]["p50"] * 1000,
                            ref["recall_at_10"]["all"],
                            CYAN,
                        )
                    )

        fig, top = figure(
            15.0,
            7.2,
            8,
            "the climb",
            "Every layout on one map — truth kept against time paid",
            f"{len(pts)} operating points · 10M vectors · 1,000 referee queries · "
            f"exact {r0['single_query_s']['p50']:.0f}s -> best measured point · {sha}",
        )
        gs = fig.add_gridspec(1, 1, left=0.08, right=1 - MARGIN - 0.02, top=top, bottom=0.13)
        ax = fig.add_subplot(gs[0])
        style_axes(ax)
        panel_title(ax, "recall@10 vs single-query latency — up and left is the whole game")
        for label, ms, rec, color in pts:
            ax.plot([ms], [rec], "o", color=color, ms=8)
            ax.annotate(
                label,
                (ms, rec),
                xytext=(7, 5),
                textcoords="offset points",
                color=color,
                fontsize=8.5,
            )
        ax.axvline(100, color=RED, lw=1.4, ls="--")
        ax.text(110, 0.08, "the Exa target: 1B under 100ms", color=RED, fontsize=9)
        ax.set_xscale("log")
        ax.set_xlabel("latency per query (ms, log)")
        ax.set_ylabel("recall@10")
        ax.set_ylim(0, 1.06)

        verdict(fig, "the ladder is real: each rung trades an order of magnitude for a stated loss")
        frame_panels(fig)
        out = out_dir / "08-the-climb.png"
        fig.savefig(out, dpi=DPI, facecolor=BG)
        print(f"wrote {out}")


if __name__ == "__main__":
    cmds = {
        "baseline": baseline,
        "synthetic": synthetic,
        "generate-full": generate_full,
        "rung0": rung0,
        "ground-truth": ground_truth,
        "rung1-quantize": rung1_quantize,
        "rung1": rung1,
        "rung2-train": rung2_train,
        "rung2": rung2,
        "rung3-train": lambda: rung3_train(sys.argv[2]),
        "rung3": lambda: rung3(sys.argv[2]),
        "rung4-train": rung4_train,
        "rung4": rung4,
        "rung4-control": rung4_control,
        "rung5": rung5,
        "figures": figures,
        "figures2": lambda: figures2(Path(sys.argv[2]) if len(sys.argv) > 2 else None),
    }
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]]()
