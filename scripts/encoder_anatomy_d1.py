#!/usr/bin/env python
"""Section 58, dissection D1: the shipped vector's coordinates, and the centred exam.

Registered in docs/design/encoder-anatomy/README.md before any call. Two
questions: is the cone (section 12) carried by a few loud coordinates or
spread over many, and does subtracting it move the retrieval gate.

READ-ONLY on Chroma and the vault. The harvest lands in ~/.ytk/encoder-anatomy/
(every stored document vector, too large for the repo); results and figures
land in docs/assets/58-encoder-anatomy-d1/.

    uv run --extra lab python scripts/encoder_anatomy_d1.py harvest
    uv run --extra lab python scripts/encoder_anatomy_d1.py coords
    uv run --extra lab python scripts/encoder_anatomy_d1.py exam
    uv run --extra lab python scripts/encoder_anatomy_d1.py figures
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
SECTION = REPO / "docs" / "assets" / "58-encoder-anatomy-d1"
RESULTS = SECTION / "results.json"
HARVEST = Path(os.path.expanduser("~/.ytk/encoder-anatomy"))
STORE = HARVEST / "d1-store.npz"
QUERIES = HARVEST / "d1-queries.npz"

SPECIMEN = "vid::UZDiGooFs54"  # Welch Labs, AlexNet; held since section 42
SEED = 20261031
NULL_DRAWS = 300
BOOT_DRAWS = 2000
FETCH_K = (
    500  # full rankings are cheap in numpy; the gate filters to the frozen ids then cuts to 10
)
TOP_KS = (1, 3, 10, 100)


def _unit(X: np.ndarray) -> np.ndarray:
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)


def _load_results() -> dict:
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {}


def _save_results(d: dict) -> None:
    SECTION.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(d, indent=1))


# ---------------------------------------------------------------- harvest


def harvest() -> None:
    """Every stored document vector from the three text collections, keyed the
    way the gate's searchers key them (vid::, mem::<doc_id>, seg::)."""
    from ytk import store

    HARVEST.mkdir(parents=True, exist_ok=True)
    vecs, keys, kinds, titles = [], [], [], []
    for kind, col, key_of in (
        (
            "vid",
            store._videos_collection(),
            lambda i, m: f"vid::{store.meta_str(m, 'video_id') or i}",
        ),
        ("mem", store._memories_collection(), lambda i, m: f"mem::{store.meta_str(m, 'doc_id')}"),
        ("seg", store._segments_collection(), lambda i, m: f"seg::{i}"),
    ):
        total = col.count()
        offset = 0
        while offset < total:
            got = col.get(limit=2000, offset=offset, include=["embeddings", "metadatas"])
            ids = got["ids"]
            embs = store.chroma_field(got["embeddings"], "embeddings")
            metas = store.chroma_field(got["metadatas"], "metadatas")
            for i, e, m in zip(ids, embs, metas):
                vecs.append(np.asarray(e, dtype=np.float32))
                keys.append(key_of(i, m))
                kinds.append(kind)
                titles.append(store.meta_str(m, "title")[:120])
            offset += len(ids)
        print(f"{kind}: {total} vectors")
    X = np.vstack(vecs)
    np.savez_compressed(
        STORE, X=X, keys=np.array(keys), kinds=np.array(kinds), titles=np.array(titles)
    )
    print(f"{len(X)} x {X.shape[1]} -> {STORE}")


def _store() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    z = np.load(STORE)
    return _unit(z["X"].astype(np.float64)), z["keys"], z["kinds"], z["titles"]


# --------------------------------------------------------------- coordinates


def _shares(mu: np.ndarray, ks=TOP_KS) -> dict[str, float]:
    sq = np.sort(mu**2)[::-1]
    tot = sq.sum()
    return {f"top{k}": float(sq[:k].sum() / tot) for k in ks}


def _pair_cos_contrib(X: np.ndarray) -> np.ndarray:
    """Per-coordinate contribution to the mean pairwise cosine, i != j.

    sum_{i!=j} x_id x_jd = (sum_i x_id)^2 - sum_i x_id^2: Timkey and van
    Schijndel's ruler, which asks which coordinates carry the similarity
    rather than which carry the mean."""
    n = len(X)
    s = X.sum(0)
    q = (X**2).sum(0)
    return (s**2 - q) / (n * (n - 1))


def coords() -> dict:
    X, keys, kinds, titles = _store()
    n, d = X.shape
    rng = np.random.default_rng(SEED)
    t0 = time.time()

    mu = X.mean(0)
    by_kind = {k: X[kinds == k].mean(0) for k in ("vid", "mem", "seg")}
    kind_cos = {
        f"{a}-{b}": float(
            by_kind[a] @ by_kind[b] / (np.linalg.norm(by_kind[a]) * np.linalg.norm(by_kind[b]))
        )
        for a, b in (("vid", "mem"), ("vid", "seg"), ("mem", "seg"))
    }
    order = np.argsort(mu**2)[::-1]
    contrib = _pair_cos_contrib(X)
    c_order = np.argsort(contrib)[::-1]
    c_tot = contrib.sum()

    # sign agreement: how many notes lean the same way on the loudest coordinates
    agree = {int(j): float(np.mean(np.sign(X[:, j]) == np.sign(mu[j]))) for j in order[:10]}

    # null 1: isotropic unit vectors, same n and d
    iso = {f"top{k}": [] for k in TOP_KS}
    iso_norm = []
    for _ in range(NULL_DRAWS):
        Y = _unit(rng.standard_normal((n, d)))
        m = Y.mean(0)
        iso_norm.append(float(np.linalg.norm(m)))
        for k, v in _shares(m).items():
            iso[k].append(v)
    # null 2: coordinates shuffled within each note, so magnitude profile is kept
    # and only coordinate identity is destroyed
    shuf = {f"top{k}": [] for k in TOP_KS}
    shuf_norm = []
    for _ in range(NULL_DRAWS):
        m = rng.permuted(X, axis=1).mean(0)
        shuf_norm.append(float(np.linalg.norm(m)))
        for k, v in _shares(m).items():
            shuf[k].append(v)

    sp = int(np.flatnonzero(keys == SPECIMEN)[0])
    x = X[sp]
    spec_sq = x**2
    spec = {
        "key": SPECIMEN,
        "title": str(titles[sp]),
        "cos_to_mean_dir": float(x @ mu / np.linalg.norm(mu)),
        "share_in_mean_top3": float(spec_sq[order[:3]].sum()),
        "share_in_mean_top100": float(spec_sq[order[:100]].sum()),
        "own_top3_share": _shares(x)["top3"],
        "own_top100_share": _shares(x)["top100"],
        "own_loudest": [int(j) for j in np.argsort(spec_sq)[::-1][:10]],
    }

    obs = _shares(mu)
    verdict = "rogue" if obs["top3"] >= 0.5 else "spread" if obs["top100"] < 0.6 else "mixed"
    out = {
        "n": int(n),
        "d": int(d),
        "n_by_kind": {k: int((kinds == k).sum()) for k in ("vid", "mem", "seg")},
        "mean_norm": float(np.linalg.norm(mu)),
        "mean_pair_cos": float(c_tot),
        "kind_mean_cos": kind_cos,
        "shares": obs,
        "loudest": [int(j) for j in order[:20]],
        "loudest_values": [float(mu[j]) for j in order[:20]],
        "sign_agreement_top10": agree,
        "pair_cos_shares": {f"top{k}": float(contrib[c_order[:k]].sum() / c_tot) for k in TOP_KS},
        "pair_cos_loudest": [int(j) for j in c_order[:20]],
        "null_isotropic": {
            **{k: [float(np.mean(v)), float(np.std(v))] for k, v in iso.items()},
            "mean_norm": [float(np.mean(iso_norm)), float(np.std(iso_norm))],
        },
        "null_shuffle": {
            **{k: [float(np.mean(v)), float(np.std(v))] for k, v in shuf.items()},
            "mean_norm": [float(np.mean(shuf_norm)), float(np.std(shuf_norm))],
        },
        "null_draws": NULL_DRAWS,
        "specimen": spec,
        "verdict": verdict,
        "seconds": round(time.time() - t0),
    }
    # sidecar: the mean, the specimen, and the null draws for the figure
    SECTION.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        SECTION / "coords.npz",
        mu=mu.astype(np.float32),
        specimen=x.astype(np.float32),
        iso_top3=np.array(iso["top3"]),
        iso_top100=np.array(iso["top100"]),
        shuf_top3=np.array(shuf["top3"]),
        shuf_top100=np.array(shuf["top100"]),
        iso_sorted=np.sort(_unit(rng.standard_normal((n, d))).mean(0) ** 2)[::-1].astype(
            np.float32
        ),
        shuf_sorted=np.sort(rng.permuted(X, axis=1).mean(0) ** 2)[::-1].astype(np.float32),
    )
    r = _load_results()
    r["coordinates"] = out
    _save_results(r)
    print(f"n={n} d={d}  ||mu||={out['mean_norm']:.3f}  mean pair cos {c_tot:.3f}")
    print("  shares of mean's squared length: " + "  ".join(f"{k} {v:.3f}" for k, v in obs.items()))
    print(
        "  isotropic null: "
        + "  ".join(f"{k} {v[0]:.4f}±{v[1]:.4f}" for k, v in out["null_isotropic"].items())
    )
    print(
        "  shuffle null:   "
        + "  ".join(f"{k} {v[0]:.4f}±{v[1]:.4f}" for k, v in out["null_shuffle"].items())
    )
    print(
        "  pair-cos shares: " + "  ".join(f"{k} {v:.3f}" for k, v in out["pair_cos_shares"].items())
    )
    print(
        f"  loudest coords {out['loudest'][:10]}  values {[round(v, 3) for v in out['loudest_values'][:10]]}"
    )
    print(f"  kind means cos {kind_cos}")
    print(
        f"  specimen cos-to-mean {spec['cos_to_mean_dir']:.3f}  share in mean top3/top100 {spec['share_in_mean_top3']:.3f}/{spec['share_in_mean_top100']:.3f}"
    )
    print(f"  verdict by the registered bar: {verdict}   ({out['seconds']}s)")
    return out


# --------------------------------------------------------------------- exam


def _query_vectors(queries: list[dict]) -> np.ndarray:
    """156 query embeddings through the production query path, cached on the
    query file's hash so the exam re-runs without the model."""
    from ytk import retrieval_gate as rg
    from ytk import store

    digest = hashlib.sha256(Path(rg.QUERIES_PATH).read_bytes()).hexdigest()
    if QUERIES.exists():
        z = np.load(QUERIES)
        if str(z["sha256"]) == digest:
            return z["Q"].astype(np.float64)
    t0 = time.time()
    Q = np.array([store._embed_query(q["query"]) for q in queries], dtype=np.float32)
    np.savez_compressed(QUERIES, Q=Q, sha256=digest)
    print(f"embedded {len(Q)} queries in {time.time() - t0:.0f}s")
    return Q.astype(np.float64)


def _searchers(Xd: np.ndarray, Qd: np.ndarray, keys, kinds, queries):
    """Numpy twins of retrieval_gate._live_searchers: exact cosine over every
    stored vector, memory parts collapsed to their best part, videos and
    memories merged by score, segments ranked alone."""
    qidx = {q["query"]: i for i, q in enumerate(queries)}
    vm = np.flatnonzero(kinds != "seg")
    sg = np.flatnonzero(kinds == "seg")
    vm_keys = keys[vm]
    uniq, inv = np.unique(vm_keys, return_inverse=True)
    S_vm = Qd @ Xd[vm].T  # (156, n_vm)
    S_sg = Qd @ Xd[sg].T
    sg_keys = keys[sg]
    unified_cache: dict[int, list[str]] = {}
    seg_cache: dict[int, list[str]] = {}

    def unified(query: str) -> list[str]:
        i = qidx[query]
        if i not in unified_cache:
            best = np.full(len(uniq), -np.inf)
            np.maximum.at(best, inv, S_vm[i])
            top = np.argsort(best)[::-1][:FETCH_K]
            unified_cache[i] = [str(uniq[j]) for j in top]
        return unified_cache[i]

    def segments(query: str) -> list[str]:
        i = qidx[query]
        if i not in seg_cache:
            top = np.argsort(S_sg[i])[::-1][:FETCH_K]
            seg_cache[i] = [str(sg_keys[j]) for j in top]
        return seg_cache[i]

    return {"videos": unified, "memories": unified, "segments": segments}


def exam() -> dict:
    from ytk import retrieval_gate as rg

    X, keys, kinds, _ = _store()
    queries = rg.load_queries(rg.QUERIES_PATH)
    frozen = rg.load_frozen_ids()
    resolve = rg._live_resolver()
    baseline = json.loads((REPO / "eval/retrieval/baseline.json").read_text())
    tol = baseline.get("tolerance", 0.02)
    Q = _unit(_query_vectors(queries))

    mu = X.mean(0)
    arms = {
        "raw": (X, Q),
        "centred": (_unit(X - mu), _unit(Q - mu)),
        # side arm, disclosed: queries centred on their own mean, which the 156
        # exam queries supply, so this is a ceiling and not a shippable path
        "centred-split": (_unit(X - mu), _unit(Q - Q.mean(0))),
    }
    reports = {}
    for name, (Xd, Qd) in arms.items():
        t0 = time.time()
        rep = rg.evaluate(
            queries,
            _searchers(Xd, Qd, keys, kinds, queries),
            resolve,
            top_k=10,
            frozen_ids=frozen,
            fetch_k=FETCH_K,
        )
        rep.pop("rankings", None)
        reports[name] = rep
        print(
            f"[{name}] "
            + "  ".join(f"{k} {v:.3f}" for k, v in rep["overall"].items())
            + f"  missing {len(rep['missing_gold'])} starved {len(rep['freeze_starved'])}  ({time.time() - t0:.0f}s)"
        )
    # evaluate() reports only the misses per query; the paired bootstrap needs
    # every query's rank, so the same filter-then-cut is replayed in order
    per_query = {}
    for name, (Xd, Qd) in arms.items():
        s = _searchers(Xd, Qd, keys, kinds, queries)
        rows = []
        for q in queries:
            gold = resolve(q["gold_id"])
            if gold is None:
                continue
            res = [r for r in s[q["bucket"]](q["query"]) if r in frozen][:10]
            rows.append(res.index(gold) if gold in res else -1)
        per_query[name] = np.array(rows)
    rng = np.random.default_rng(SEED)
    m = len(per_query["raw"])
    idx = rng.integers(0, m, size=(BOOT_DRAWS, m))
    boot = {}
    for name, rk in per_query.items():
        boot[name] = {}
        for k in (1, 5, 10):
            hit = ((rk >= 0) & (rk < k)).astype(float)
            boot[name][f"hit@{k}"] = hit[idx].mean(1)
    diff = {k: boot["centred"][k] - boot["raw"][k] for k in ("hit@1", "hit@5", "hit@10")}
    base = baseline["overall"]
    c = reports["centred"]["overall"]
    passes = (
        c["hit@5"] > base["hit@5"] + tol
        and c["hit@10"] > base["hit@10"] + tol
        and c["hit@1"] >= base["hit@1"]
    )
    out = {
        "baseline": base,
        "tolerance": tol,
        "arms": {
            n: {
                "overall": r["overall"],
                "per_bucket": r["per_bucket"],
                "n_evaluated": r["n_evaluated"],
                "missing_gold": len(r["missing_gold"]),
                "freeze_starved": len(r["freeze_starved"]),
            }
            for n, r in reports.items()
        },
        "bootstrap": {
            n: {
                k: [float(v.mean()), float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
                for k, v in b.items()
            }
            for n, b in boot.items()
        },
        "diff_centred_minus_raw": {
            k: [
                float(v.mean()),
                float(np.percentile(v, 2.5)),
                float(np.percentile(v, 97.5)),
                float((v > 0).mean()),
            ]
            for k, v in diff.items()
        },
        "boot_draws": BOOT_DRAWS,
        "fetch_k": FETCH_K,
        "ships": bool(passes),
    }
    np.savez_compressed(
        SECTION / "exam.npz",
        **{f"{n}_{k.replace('@', '')}": v for n, b in boot.items() for k, v in b.items()},
        **{f"rank_{n}": v for n, v in per_query.items()},
    )
    r = _load_results()
    r["exam"] = out
    _save_results(r)
    for k, v in out["diff_centred_minus_raw"].items():
        print(f"  centred - raw {k}: {v[0]:+.3f}  [{v[1]:+.3f}, {v[2]:+.3f}]  P(>0) {v[3]:.2f}")
    print(f"  ships under the gate's bar: {passes}")
    return out


# ------------------------------------------------------------------ figures


def figures() -> None:
    import plot_assets as pa

    pa.OUTDIR = SECTION
    r = _load_results()
    c = r["coordinates"]
    z = np.load(SECTION / "coords.npz")
    mu, x = z["mu"].astype(float), z["specimen"].astype(float)
    d = len(mu)
    order = np.argsort(mu**2)[::-1]
    sq = (mu**2)[order]
    spec_title = c["specimen"]["title"]

    # ---- figure 01: the coordinates
    fig, top = pa.figure(
        18,
        11,
        1,
        "section 58, D1: the shipped vector's coordinates",
        "The cone is spread, not rogue: the mean vector's squared length over its 1024 coordinates",
        meta=(
            f"{c['n']:,} stored vectors (videos {c['n_by_kind']['vid']}, memory parts {c['n_by_kind']['mem']}, "
            f"segments {c['n_by_kind']['seg']}), d = {c['d']}, ||mean|| = {c['mean_norm']:.3f}, mean pair cosine "
            f"{c['mean_pair_cos']:.3f}. Top 3 coordinates carry {c['shares']['top3'] * 100:.1f}% of the mean's squared length, "
            f"top 100 carry {c['shares']['top100'] * 100:.1f}%. Isotropic null {c['null_draws']} draws: top 3 "
            f"{c['null_isotropic']['top3'][0] * 100:.2f}%, top 100 {c['null_isotropic']['top100'][0] * 100:.1f}%. "
            f"Within-note shuffle null: top 3 {c['null_shuffle']['top3'][0] * 100:.2f}%, top 100 "
            f"{c['null_shuffle']['top100'][0] * 100:.1f}%. Specimen: {spec_title}"
        ),
    )
    gs = fig.add_gridspec(
        2,
        3,
        left=pa.MARGIN,
        right=1 - pa.MARGIN,
        top=top,
        bottom=0.07,
        hspace=0.42,
        wspace=0.22,
        width_ratios=[1.3, 1, 1],
    )
    # A: sorted coordinate field, log y, the two nulls in DIM
    ax = fig.add_subplot(gs[0, :2])
    pa.style_axes(ax)
    k = np.arange(1, d + 1)
    # each profile as a share of its own squared length: the isotropic mean is
    # 70x shorter, so raw magnitudes cannot share an axis and the shape is the claim
    prof = sq / sq.sum()
    iso_p = z["iso_sorted"] / z["iso_sorted"].sum()
    shuf_p = z["shuf_sorted"] / z["shuf_sorted"].sum()
    floor = 1e-6
    ax.fill_between(
        k,
        floor,
        prof,
        color=pa.GOLD,
        alpha=0.95,
        lw=0,
        label="the mean vector, sorted by magnitude",
    )
    ax.fill_between(
        k, floor, iso_p, color=pa.DIM, alpha=0.9, lw=0, label="isotropic null, same n and d"
    )
    ax.plot(
        k, shuf_p, color=pa.MUTED, lw=1.0, ls="--", label="coordinates shuffled within each note"
    )
    ax.plot(k, prof, color=pa.GOLD, lw=1.4)
    ax.set_yscale("log")
    ax.set_ylim(floor, 0.05)
    ax.set_xlim(0, d)
    ax.set_xlabel("coordinate rank (sorted by squared magnitude)")
    ax.set_ylabel("share of the profile's squared length (log)")
    ax.axvline(3, color=pa.RED, lw=0.8, ls=":")
    ax.axvline(100, color=pa.RED, lw=0.8, ls=":")
    ax.text(6, 0.035, "3", color=pa.RED, fontsize=pa.TICK_SIZE, va="top")
    ax.text(103, 0.035, "100", color=pa.RED, fontsize=pa.TICK_SIZE, va="top")
    ax.legend(
        loc="lower left",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        "A. The mean's 1024 coordinates, loudest first, each profile scaled to its own length. A rogue mean would fall off a cliff; this one hugs the noise profile",
        100,
    )

    # B: cumulative share with the bars
    ax = fig.add_subplot(gs[0, 2])
    pa.style_axes(ax)
    cum = np.cumsum(sq) / sq.sum()
    ax.plot(
        k,
        np.cumsum(z["iso_sorted"]) / z["iso_sorted"].sum(),
        color=pa.DIM,
        lw=2.2,
        label="isotropic null",
    )
    ax.plot(
        k,
        np.cumsum(z["shuf_sorted"]) / z["shuf_sorted"].sum(),
        color=pa.MUTED,
        lw=1.2,
        ls="--",
        label="shuffle null",
    )
    ax.plot(k, cum, color=pa.GOLD, lw=2.2, label="the mean")
    ax.set_xscale("log")
    ax.set_xlim(1, d)
    ax.set_ylim(0, 1)
    ax.axhline(0.5, color=pa.RED, lw=0.8, ls=":")
    ax.axvline(3, color=pa.RED, lw=0.8, ls=":")
    ax.axhline(0.6, color=pa.RED, lw=0.8, ls=":")
    ax.axvline(100, color=pa.RED, lw=0.8, ls=":")
    ax.text(3.2, 0.52, "rogue bar: top 3 >= 50%", color=pa.RED, fontsize=pa.TICK_SIZE)
    ax.text(105, 0.62, "spread bar: top 100 < 60%", color=pa.RED, fontsize=pa.TICK_SIZE)
    ax.scatter([3, 100], [cum[2], cum[99]], color=pa.GOLD, s=40, zorder=5)
    ax.set_xlabel("top k coordinates")
    ax.set_ylabel("share of the mean's squared length")
    ax.legend(
        loc="upper left",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(ax, "B. Cumulative share against the registered bars", 40)

    # C: the specimen in index order, mean behind, loudest mean coordinates marked
    ax = fig.add_subplot(gs[1, :2])
    pa.style_axes(ax)
    idx = np.arange(d)
    ax.bar(idx, x, width=1.0, color=pa.CYAN, lw=0, alpha=0.8, label="the specimen's shipped vector")
    ax.bar(idx, mu, width=1.0, color=pa.GOLD, lw=0, alpha=0.95, label="the mean (same scale)")
    ymax = float(np.abs(x).max()) * 1.12
    ax.scatter(
        order[:10],
        [ymax * 0.97] * 10,
        marker="v",
        color=pa.GOLD,
        s=30,
        zorder=5,
        label="the mean's ten loudest",
    )
    ax.set_ylim(-ymax, ymax)
    ax.set_xlim(0, d)
    ax.set_xlabel("coordinate index (as stored)")
    ax.set_ylabel("value")
    ax.legend(
        loc="upper right",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    sp = c["specimen"]
    pa.panel_title(
        ax,
        f"C. The specimen, {spec_title[:60]}: cosine {sp['cos_to_mean_dir']:.2f} to the mean direction; "
        f"the mean's loudest coordinates hold {sp['share_in_mean_top3'] * 100:.1f}% (top 3) "
        f"and {sp['share_in_mean_top100'] * 100:.0f}% (top 100) of the specimen's own squared length",
        95,
    )

    # D: the nulls as distributions the observation sits inside
    ax = fig.add_subplot(gs[1, 2])
    pa.style_axes(ax)
    for key, col, lab in (
        ("iso_top100", pa.DIM, "isotropic null"),
        ("shuf_top100", pa.MUTED, "shuffle null"),
    ):
        ax.hist(z[key] * 100, bins=30, color=col, alpha=0.9, label=f"top-100 share, {lab}")
    ax.axvline(c["shares"]["top100"] * 100, color=pa.GOLD, lw=2.5, label="observed top-100 share")
    ax.axvline(60, color=pa.RED, lw=0.8, ls=":")
    ax.set_xlabel("top-100 share of the mean's squared length (%)")
    ax.set_ylabel(f"draws of {c['null_draws']}")
    ax.legend(
        loc="upper center",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        f"D. Top-100 share: observed {c['shares']['top100'] * 100:.1f}% against both nulls "
        f"(isotropic {c['null_isotropic']['top100'][0] * 100:.1f}%, shuffle {c['null_shuffle']['top100'][0] * 100:.1f}%)",
        48,
    )
    pa.verdict(
        fig,
        f"{c['verdict'].upper()}: top 3 carry {c['shares']['top3'] * 100:.1f}%, top 100 carry {c['shares']['top100'] * 100:.1f}% "
        f"(bar: rogue >= 50% in 3, spread < 60% in 100)",
    )
    pa.save(fig, "01-the-coordinates.png")

    # ---- figure 02: the exam
    if "exam" not in r:
        return
    e = r["exam"]
    zb = np.load(SECTION / "exam.npz")
    base, tol = e["baseline"], e["tolerance"]
    raw, cen = e["arms"]["raw"]["overall"], e["arms"]["centred"]["overall"]
    fig, top = pa.figure(
        18,
        9.5,
        2,
        "section 58, D1: the centred exam",
        "Subtracting the cone and sitting the retrieval gate: raw cosine against centred cosine on the 156 frozen queries",
        meta=(
            f"Baseline (2026-07-26 stamp) hit@1 {base['hit@1']:.3f}, hit@5 {base['hit@5']:.3f}, hit@10 {base['hit@10']:.3f}, tolerance {tol}. "
            f"Raw, exact cosine in numpy: {raw['hit@1']:.3f} / {raw['hit@5']:.3f} / {raw['hit@10']:.3f}. "
            f"Centred (document mean subtracted from both sides): {cen['hit@1']:.3f} / {cen['hit@5']:.3f} / {cen['hit@10']:.3f}. "
            f"{e['boot_draws']} paired bootstrap resamples of the {e['arms']['raw']['n_evaluated']} evaluated queries, "
            f"scored inside the frozen corpus of {11005:,} ids."
        ),
    )
    gs = fig.add_gridspec(
        1, 3, left=pa.MARGIN, right=1 - pa.MARGIN, top=top, bottom=0.09, wspace=0.25
    )
    # A: bootstrap distributions per k, raw vs centred, with baseline and band
    ax = fig.add_subplot(gs[0, 0])
    pa.style_axes(ax)
    ks = ("hit@1", "hit@5", "hit@10")
    for i, kk in enumerate(ks):
        b = base[kk]
        ax.axhspan(
            b - tol,
            b + tol,
            xmin=(i + 0.08) / 3,
            xmax=(i + 0.92) / 3,
            color=pa.DIM,
            alpha=0.9,
            lw=0,
        )
        ax.hlines(b, i - 0.42, i + 0.42, color=pa.MUTED, lw=1.0)
        for name, col, off in (("raw", pa.BLUE, -0.18), ("centred", pa.GOLD, 0.18)):
            v = zb[f"{name}_{kk.replace('@', '')}"]
            parts = ax.violinplot([v], positions=[i + off], widths=0.3, showextrema=False)
            for body in parts["bodies"]:
                body.set_facecolor(col)
                body.set_alpha(0.75)
                body.set_edgecolor("none")
            ax.scatter([i + off], [e["arms"][name]["overall"][kk]], color=col, s=28, zorder=5)
    ax.set_xticks(range(3))
    ax.set_xticklabels(ks)
    ax.set_ylabel("hit rate over bootstrap resamples")
    ax.set_ylim(0.6, 1.0)
    from matplotlib.patches import Patch

    ax.legend(
        handles=[
            Patch(color=pa.BLUE, label="raw cosine (production)"),
            Patch(color=pa.GOLD, label="centred cosine"),
            Patch(color=pa.DIM, label="baseline, its 0.02 tolerance"),
        ],
        loc="center",
        bbox_to_anchor=(0.5, 0.42),
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    d1 = e["arms"]["centred"]["overall"]["hit@1"] - base["hit@1"]
    pa.panel_title(
        ax,
        f"A. Raw reproduces the stamp exactly; centred falls {abs(d1):.3f} at hit@1, past the band's floor, and stays inside it at 5 and 10",
        78,
    )

    # B: paired differences
    ax = fig.add_subplot(gs[0, 1])
    pa.style_axes(ax)
    ax.axhspan(-tol, tol, color=pa.DIM, alpha=0.9, lw=0, label="inside the tolerance")
    ax.axhline(0, color=pa.MUTED, lw=1.0)
    for i, kk in enumerate(ks):
        v = zb[f"centred_{kk.replace('@', '')}"] - zb[f"raw_{kk.replace('@', '')}"]
        parts = ax.violinplot([v], positions=[i], widths=0.6, showextrema=False)
        for body in parts["bodies"]:
            body.set_facecolor(pa.GOLD)
            body.set_alpha(0.8)
            body.set_edgecolor("none")
        dd = e["diff_centred_minus_raw"][kk]
        ax.scatter([i], [dd[0]], color=pa.TEXT, s=22, zorder=5)
        ax.text(
            i,
            dd[2] + 0.004,
            f"{dd[0]:+.3f}\nP(>0) {dd[3]:.2f}",
            color=pa.TEXT,
            ha="center",
            fontsize=pa.TICK_SIZE,
        )
    ax.set_xticks(range(3))
    ax.set_xticklabels(ks)
    ax.set_ylabel("centred minus raw, paired resamples")
    ax.set_ylim(-0.08, 0.08)
    ax.legend(
        loc="lower left",
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(ax, "B. What centring changes, query by query: the paired difference", 46)

    # C: per bucket, all three arms
    ax = fig.add_subplot(gs[0, 2])
    pa.style_axes(ax)
    buckets = ("videos", "memories", "segments")
    arms = (("raw", pa.BLUE), ("centred", pa.GOLD), ("centred-split", pa.PURPLE))
    w = 0.26
    for j, (name, col) in enumerate(arms):
        vals = [e["arms"][name]["per_bucket"].get(b, {}).get("hit@5", 0) for b in buckets]
        ax.bar(np.arange(3) + (j - 1) * w, vals, width=w, color=col, label=name, lw=0)
        for i, v in enumerate(vals):
            ax.text(
                i + (j - 1) * w,
                v + 0.01,
                f"{v:.2f}",
                color=pa.TEXT,
                ha="center",
                fontsize=pa.TICK_SIZE - 1,
            )
    ax.set_xticks(range(3))
    ax.set_xticklabels(
        [f"{b}\n(n={e['arms']['raw']['per_bucket'].get(b, {}).get('n', 0)})" for b in buckets]
    )
    ax.set_ylim(0.5, 1.16)
    ax.set_ylabel("hit@5")
    ax.legend(
        loc="upper left",
        ncol=3,
        fontsize=pa.TICK_SIZE,
        facecolor=pa.PANEL,
        edgecolor=pa.FRAME,
        labelcolor=pa.TEXT,
    )
    pa.panel_title(
        ax,
        "C. hit@5 by bucket; the split arm centres queries on their own mean (disclosed ceiling, not shippable)",
        50,
    )
    dd = {k: e["diff_centred_minus_raw"][k][0] for k in ks}
    pa.verdict(
        fig,
        ("CENTRING EARNS THE SLOT" if e["ships"] else "NOT EARNED")
        + f": centred minus raw hit@1 {dd['hit@1']:+.3f}, hit@5 {dd['hit@5']:+.3f}, hit@10 {dd['hit@10']:+.3f}; the bar was +0.02 at 5 and 10 with no fall at 1",
    )
    pa.save(fig, "02-the-exam.png")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "coords"
    {"harvest": harvest, "coords": coords, "exam": exam, "figures": figures}[cmd]()
