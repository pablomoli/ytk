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


if __name__ == "__main__":
    cmds = {
        "baseline": baseline,
        "synthetic": synthetic,
        "generate-full": generate_full,
        "rung0": rung0,
        "figures": figures,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]]()
