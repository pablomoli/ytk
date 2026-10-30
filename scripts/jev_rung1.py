"""Section 54, rung 1: the retrieval gate's 156 queries through Jev's Noul.

Registration (bars, arm, scoring) is in docs/assets/54-jev-gate-replay/README.md
and was committed before `collect` first ran.

    uv run python scripts/jev_rung1.py collect     # 156 queries, ~170 requests
    uv run python scripts/jev_rung1.py stability   # 20 queries re-sent
    uv run python scripts/jev_rung1.py score       # frozen-filtered metrics, null, bars
    uv run --with matplotlib python scripts/jev_rung1.py draw
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
from jev_rung0 import ASK_NOUL, NOUL_FALSE, NOUL_TRUE2, ROOT, commit_sha

OUTDIR = ROOT / "docs" / "assets" / "54-jev-gate-replay"
SIDECAR = OUTDIR / "rung1.json"
PARTIAL = OUTDIR / "rung1.partial.jsonl"
STABILITY = OUTDIR / "rung1-stability.json"
SCORES = OUTDIR / "rung1-scores.json"
BENCH30 = ROOT / "experiments" / "rerank_bench_results.json"
DEPTH = 30
SPLIT_CHARS = 80_000  # above this the state risks the 32k per-question limit; send two halves
WINDOW = 10
N_NULL = 1000
SEED = 54
BARS = {"hit@1": 0.79, "hit@5": 0.93, "wall_s": 1.0, "demoted": 3}


def _requests_for(query: str, pairs: list[tuple[str, str]]):
    """One request, or two of 15 when the state is too large. Yields (keys, state, questions)."""
    chars = sum(len(d) for _, d in pairs)
    chunks = (
        [pairs] if chars <= SPLIT_CHARS else [pairs[: len(pairs) // 2], pairs[len(pairs) // 2 :]]
    )
    for chunk in chunks:
        keys = [k for k, _ in chunk]
        state = {
            "query": query,
            "candidates": {f"c{i:02d}": {"text": d} for i, (_, d) in enumerate(chunk, 1)},
        }
        qs = {f"c{i:02d}": None for i in range(1, len(chunk) + 1)}
        yield keys, state, qs


def _ask(state, qs, tag):
    import jev_client as jev

    questions = {k: jev.noul(ASK_NOUL.format(k=k), NOUL_TRUE2, NOUL_FALSE) for k in qs}
    r = jev.system_one(state, questions, tag=tag)
    return [r.answers[k]["noul"] for k in qs], r.input_tokens, r.latency_s, r.model


def collect() -> None:
    from rerank_bench import retrieve_with_docs

    from ytk import retrieval_gate

    queries = retrieval_gate.load_queries(retrieval_gate.QUERIES_PATH)
    resolve = retrieval_gate._live_resolver()
    searchers = retrieve_with_docs(DEPTH)
    PARTIAL.unlink(missing_ok=True)
    rows, model = [], None
    for n, q in enumerate(queries, 1):
        gold = resolve(q["gold_id"])
        if gold is None:
            continue
        pairs = searchers[q["bucket"]](q["query"])
        keys, nouls, tokens, lat = [], [], 0, []
        for ck, state, qs in _requests_for(q["query"], pairs):
            vals, tok, s, model = _ask(state, qs, tag="rung1-noul")
            keys += ck
            nouls += vals
            tokens += tok
            lat.append(s)
        row = {
            "query": q["query"],
            "bucket": q["bucket"],
            "gold_id": q["gold_id"],
            "gold": gold,
            "keys": keys,
            "noul": nouls,
            "chars": sum(len(d) for _, d in pairs),
            "requests": len(lat),
            "latency_s": lat,
            "wall_s": sum(lat),
            "input_tokens": tokens,
        }
        rows.append(row)
        with PARTIAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        before = keys.index(gold) if gold in keys else None
        after = [k for _, k in sorted(zip(nouls, keys), key=lambda t: -t[0])]
        after_r = after.index(gold) if gold in after else None
        print(
            f"{n:3}/{len(queries)} {q['bucket']:8} gold {before!s:>4} -> {after_r!s:>4} | {len(lat)} req "
            f"{sum(lat) * 1000:5.0f} ms {tokens:6} tok | {q['query'][:48]}"
        )
    SIDECAR.write_text(
        json.dumps(
            {
                "generated": datetime.now(UTC).isoformat(timespec="seconds"),
                "commit": commit_sha(),
                "model": model,
                "depth": DEPTH,
                "split_chars": SPLIT_CHARS,
                "questions": {"noul": ASK_NOUL, "true": NOUL_TRUE2, "false": NOUL_FALSE},
                "rows": rows,
            },
            indent=1,
        )
    )
    PARTIAL.unlink(missing_ok=True)
    print(f"wrote {SIDECAR.relative_to(ROOT)}")


def stability() -> None:
    """Re-send 20 queries' requests unchanged; the texts come from the live store again."""
    from rerank_bench import retrieve_with_docs

    data = json.loads(SIDECAR.read_text())
    rng = np.random.default_rng(SEED)
    picks = sorted(rng.choice(len(data["rows"]), 20, replace=False))
    searchers = retrieve_with_docs(DEPTH)
    out = []
    for i in picks:
        row = data["rows"][i]
        pairs = searchers[row["bucket"]](row["query"])
        by_key = dict(pairs)
        # same keys in the same order as the first run, so the states match byte for byte
        pairs = [(k, by_key[k]) for k in row["keys"] if k in by_key]
        if len(pairs) != len(row["keys"]):
            print(f"skip {row['query'][:40]}: candidate set changed since the first run")
            continue
        nouls = []
        for _, state, qs in _requests_for(row["query"], pairs):
            vals, *_ = _ask(state, qs, tag="rung1-stability")
            nouls += vals
        d = np.abs(np.array(nouls) - np.array(row["noul"]))
        out.append(
            {
                "query": row["query"],
                "noul_rerun": nouls,
                "dp_median": float(np.median(d)),
                "dp_max": float(d.max()),
            }
        )
        print(f"{row['query'][:50]:50} |dP| median {np.median(d):.3f} max {d.max():.3f}")
    dp = np.abs(
        np.concatenate(
            [
                np.array(o["noul_rerun"])
                - np.array(next(r["noul"] for r in data["rows"] if r["query"] == o["query"]))
                for o in out
            ]
        )
    )
    summary = {
        "n_queries": len(out),
        "n_nouls": int(dp.size),
        "dp_median": float(np.median(dp)),
        "dp_p90": float(np.quantile(dp, 0.9)),
        "dp_max": float(dp.max()),
        "bar": {"dp_median": 0.005, "dp_p90": 0.03},
        "pass": bool(np.median(dp) <= 0.005 and np.quantile(dp, 0.9) <= 0.03),
    }
    STABILITY.write_text(
        json.dumps(
            {"generated": datetime.now(UTC).isoformat(timespec="seconds"), **summary, "rows": out},
            indent=1,
        )
    )
    print(json.dumps(summary, indent=1))


def _ndcg(keys: list[str], grades: dict[str, int], k: int = WINDOW) -> float:
    g = np.array([grades.get(x, 0) for x in keys[:k]], dtype=float)
    ideal = np.sort(np.array(list(grades.values()) or [0], dtype=float))[::-1][:k]
    disc = np.log2(np.arange(2, k + 2))
    num = ((2.0**g - 1) / disc[: len(g)]).sum()
    den = ((2.0**ideal - 1) / disc[: len(ideal)]).sum()
    return float(num / den) if den > 0 else float("nan")


def score() -> dict:
    from ytk import retrieval_gate

    data = json.loads(SIDECAR.read_text())
    frozen = retrieval_gate.load_frozen_ids()
    qrels = json.load(retrieval_gate.QRELS_PATH.open())
    grades: dict[str, dict[str, int]] = {}
    for lab in qrels["labels"]:
        grades.setdefault(lab["query_id"], {})[lab["doc_id"]] = int(lab["grade"])
    bench = {r["query"]: r for r in json.load(BENCH30.open())["rows"]}
    rng = np.random.default_rng(SEED)

    def frozen_rank(keys: list[str], gold: str):
        kept = [k for k in keys if k in frozen][:WINDOW]
        return (kept.index(gold) if gold in kept else None), kept

    arms = {"served": [], "qwen3": [], "jev": []}
    nd = {"served": [], "qwen3": [], "jev": []}
    null_nd, null_h1, null_h5, null_h10 = [], [], [], []
    per_row = []
    for r in data["rows"]:
        g = grades.get(r["gold_id"], {})
        served = r["keys"]
        jev = [k for _, k in sorted(zip(r["noul"], served), key=lambda t: -t[0])]
        ranks = {}
        for name, keys in (("served", served), ("jev", jev)):
            rk, kept = frozen_rank(keys, r["gold"])
            ranks[name] = rk
            arms[name].append(rk)
            nd[name].append(_ndcg(kept, g))
        # The July bench kept only the gold's rank, not the ordering: hit@k for
        # Qwen3, no nDCG, and no frozen filter (it predates the freeze).
        qr = bench.get(r["query"], {}).get("rank_after")
        ranks["qwen3"] = qr if qr is None or qr < WINDOW else None
        arms["qwen3"].append(ranks["qwen3"])
        nd["qwen3"].append(float("nan"))
        pool = [k for k in served if k in frozen]
        perm_nd, perm_h1, perm_h5, perm_h10 = [], [], [], []
        for _ in range(N_NULL):
            p = list(rng.permutation(pool))[:WINDOW]
            perm_nd.append(_ndcg(p, g))
            rk = p.index(r["gold"]) if r["gold"] in p else None
            perm_h1.append(rk == 0)
            perm_h5.append(rk is not None and rk < 5)
            perm_h10.append(rk is not None)
        null_nd.append(perm_nd)
        null_h1.append(perm_h1)
        null_h5.append(perm_h5)
        null_h10.append(perm_h10)
        per_row.append(
            {
                "query": r["query"],
                "bucket": r["bucket"],
                "ranks": ranks,
                "ndcg": {k: nd[k][-1] for k in nd},
                "wall_s": r["wall_s"],
            }
        )

    def hits(rs, k):
        return sum(1 for x in rs if x is not None and x < k) / len(rs)

    n = len(data["rows"])
    nd_s, nd_j = np.array(nd["served"]), np.array(nd["jev"])
    d = nd_j - nd_s
    boots = [rng.choice(d, len(d), replace=True).mean() for _ in range(N_NULL)]
    demoted = sum(
        1
        for p in per_row
        if p["ranks"]["served"] is not None
        and p["ranks"]["served"] < 5
        and (p["ranks"]["jev"] is None or p["ranks"]["jev"] >= 5)
    )
    promoted = sum(
        1
        for p in per_row
        if (p["ranks"]["served"] is None or p["ranks"]["served"] >= 5)
        and p["ranks"]["jev"] is not None
        and p["ranks"]["jev"] < 5
    )
    walls = sorted(r["wall_s"] for r in data["rows"])
    null_nd_mean = np.nanmean(np.array(null_nd), axis=0)
    out = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": commit_sha(),
        "model": data["model"],
        "n": n,
        "hit": {name: {f"hit@{k}": hits(arms[name], k) for k in (1, 5, 10)} for name in arms},
        "per_bucket": {
            b: {
                name: {
                    f"hit@{k}": hits([p["ranks"][name] for p in per_row if p["bucket"] == b], k)
                    for k in (1, 5, 10)
                }
                for name in arms
            }
            for b in sorted({p["bucket"] for p in per_row})
        },
        "ndcg10": {name: float(np.nanmean(nd[name])) for name in nd},
        "ndcg10_paired": {
            "wins": int((d > 1e-9).sum()),
            "ties": int((np.abs(d) <= 1e-9).sum()),
            "losses": int((d < -1e-9).sum()),
            "mean": float(d.mean()),
            "lo": float(np.quantile(boots, 0.025)),
            "hi": float(np.quantile(boots, 0.975)),
        },
        "null": {
            "ndcg10_mean": float(null_nd_mean.mean()),
            "ndcg10_sd": float(null_nd_mean.std()),
            "hit@1_mean": float(np.array(null_h1).mean()),
            "hit@5_mean": float(np.array(null_h5).mean()),
            "hit@10_mean": float(np.array(null_h10).mean()),
        },
        "demoted_out_of_top5": demoted,
        "promoted_into_top5": promoted,
        "wall_s": {
            "median": walls[len(walls) // 2],
            "p95": walls[int(0.95 * len(walls))],
            "max": walls[-1],
        },
        "requests": sum(r["requests"] for r in data["rows"]),
        "input_tokens": sum(r["input_tokens"] for r in data["rows"]),
        "bars": BARS,
        "rows": per_row,
    }
    h = out["hit"]["jev"]
    out["verdict"] = {
        "B1_gain": bool(h["hit@1"] >= BARS["hit@1"] and h["hit@5"] >= BARS["hit@5"]),
        "B2_speed": bool(out["wall_s"]["median"] <= BARS["wall_s"]),
        "B3_damage": bool(demoted <= BARS["demoted"] and out["ndcg10_paired"]["lo"] > 0),
    }
    if STABILITY.exists():
        st = json.loads(STABILITY.read_text())
        out["stability"] = {k: v for k, v in st.items() if k != "rows"}
        # Post hoc, not registered: what the measured jitter does in rank space.
        by_q = {r["query"]: r for r in data["rows"]}
        same_top1 = same_gold = same_top10 = 0
        for o in st["rows"]:
            r = by_q[o["query"]]
            o1 = [k for _, k in sorted(zip(r["noul"], r["keys"]), key=lambda t: -t[0])]
            o2 = [k for _, k in sorted(zip(o["noul_rerun"], r["keys"]), key=lambda t: -t[0])]
            k1, k2 = frozen_rank(o1, r["gold"])[1], frozen_rank(o2, r["gold"])[1]
            same_top1 += k1[:1] == k2[:1]
            same_top10 += k1 == k2
            same_gold += frozen_rank(o1, r["gold"])[0] == frozen_rank(o2, r["gold"])[0]
        out["stability"]["rank_consequence_post_hoc"] = {
            "n": len(st["rows"]),
            "same_top1": same_top1,
            "same_gold_rank": same_gold,
            "identical_top10_order": same_top10,
        }
    SCORES.write_text(json.dumps(out, indent=1))
    for name in arms:
        print(
            f"{name:7}",
            {k: round(v, 4) for k, v in out["hit"][name].items()},
            f"nDCG@10 {out['ndcg10'][name]:.4f}",
        )
    print("null   ", {k: round(v, 4) for k, v in out["null"].items()})
    print("paired jev-served", out["ndcg10_paired"])
    print(
        f"demoted {demoted} promoted {promoted} | wall median {out['wall_s']['median']:.3f}s p95 {out['wall_s']['p95']:.3f}s max {out['wall_s']['max']:.3f}s"
    )
    print("verdict", out["verdict"], "stability", out.get("stability", {}).get("pass"))
    return out


def draw() -> None:
    import matplotlib

    matplotlib.use("Agg")
    from plot_assets import (
        BG,
        BLUE,
        DIM,
        DPI,
        GOLD,
        MARGIN,
        MUTED,
        RED,
        TEXT,
        figure,
        frame_panels,
        panel_title,
        style_axes,
        verdict,
    )

    s = json.loads(SCORES.read_text())
    rows = s["rows"]
    n = s["n"]
    miss = WINDOW  # golds outside the window drawn in a bin past the last rank

    def rk(v):
        return miss if v is None else v

    fig, top = figure(
        17,
        8.6,
        1,
        "jev, gate replay",
        "The gate's 156 golds: where served order put each one, and where Jev's Noul moved it",
        meta=(
            f"{n} frozen queries, production top-{DEPTH}, frozen filter, window {WINDOW} | left: gold rank served -> Jev, one point "
            f"per query (jitter), ranks past {WINDOW - 1} binned at '>' | middle: the same against the local Qwen3 reranker as measured "
            f"in #86 | right: hit@k per arm, grey band: {N_NULL} random orderings | Jev {s['requests']} requests, "
            f"{s['input_tokens']:,} tokens, wall median {s['wall_s']['median'] * 1000:.0f} ms, p95 {s['wall_s']['p95'] * 1000:.0f} ms | "
            f"{s['model']} {s['commit']}"
        ),
    )
    h = top - 0.19
    rng = np.random.default_rng(1)
    for j, (arm, col, title) in enumerate(
        (
            ("jev", GOLD, "served -> Jev Noul on stored text"),
            ("qwen3", BLUE, "served -> Qwen3 depth 30 (#86, July)"),
        )
    ):
        ax = fig.add_axes([MARGIN + 0.02 + j * 0.30, 0.13, 0.26, h])
        style_axes(ax)
        xs = np.array(
            [rk(p["ranks"]["served"]) for p in rows if p["ranks"][arm] is not None or arm == "jev"],
            dtype=float,
        )
        ys = np.array(
            [rk(p["ranks"][arm]) for p in rows if p["ranks"][arm] is not None or arm == "jev"],
            dtype=float,
        )
        ax.plot([-0.5, miss + 0.5], [-0.5, miss + 0.5], color=RED, linewidth=0.9)
        ax.scatter(
            xs + rng.uniform(-0.3, 0.3, len(xs)),
            ys + rng.uniform(-0.3, 0.3, len(ys)),
            s=16,
            color=col,
            alpha=0.75,
        )
        ax.set_xlim(-0.6, miss + 0.6)
        ax.set_ylim(miss + 0.6, -0.6)
        ticks = list(range(WINDOW)) + [miss]
        ax.set_xticks(ticks)
        ax.set_xticklabels([str(t + 1) for t in range(WINDOW)] + [">"])
        ax.set_yticks(ticks)
        ax.set_yticklabels([str(t + 1) for t in range(WINDOW)] + [">"])
        ax.set_xlabel("gold rank, served order")
        ax.set_ylabel("gold rank after reordering")
        below = int((ys > xs).sum())
        above = int((ys < xs).sum())
        ax.text(
            0.98,
            0.04,
            f"{above} up, {below} down, {int((ys == xs).sum())} unchanged",
            transform=ax.transAxes,
            color=TEXT,
            fontsize=9,
            ha="right",
        )
        panel_title(ax, title, width=40)

    ax = fig.add_axes([MARGIN + 0.02 + 0.60, 0.13, 0.30, h])
    style_axes(ax)
    ks = ["hit@1", "hit@5", "hit@10"]
    x = np.arange(len(ks))
    w = 0.26
    for j, (arm, col) in enumerate((("served", TEXT), ("qwen3", BLUE), ("jev", GOLD))):
        vals = [s["hit"][arm][k] for k in ks]
        ax.bar(x + (j - 1) * w, vals, w, color=col, edgecolor=BG)
        for xi, v in zip(x + (j - 1) * w, vals):
            ax.text(xi, v + 0.01, f"{v:.3f}", color=col, fontsize=8, ha="center")
    for xi, k in zip(x, ks):
        ax.add_patch(
            matplotlib.patches.Rectangle(
                (xi - 0.45, 0),
                0.9,
                s["null"][f"{k}_mean"],
                facecolor=DIM,
                edgecolor="none",
                zorder=0,
            )
        )
    ax.hlines(
        [BARS["hit@1"], BARS["hit@5"]],
        [x[0] - 0.45, x[1] - 0.45],
        [x[0] + 0.45, x[1] + 0.45],
        color=RED,
        linewidth=1.2,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(ks)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("fraction of golds inside k")
    ax.text(x[0] - 0.45, BARS["hit@1"] + 0.012, "bar", color=RED, fontsize=8)
    panel_title(
        ax,
        "hit@k: served (white), Qwen3 (blue), Jev (gold); red: registered bars; grey: random order",
        width=56,
    )

    v = s["verdict"]
    verdict(
        fig,
        f"B1 gain {'pass' if v['B1_gain'] else 'FAIL'} (hit@1 {s['hit']['jev']['hit@1']:.3f}, hit@5 {s['hit']['jev']['hit@5']:.3f}) · "
        f"B2 speed {'pass' if v['B2_speed'] else 'FAIL'} ({s['wall_s']['median'] * 1000:.0f} ms) · "
        f"B3 damage {'pass' if v['B3_damage'] else 'FAIL'} ({s['demoted_out_of_top5']} demoted, nDCG gain "
        f"[{s['ndcg10_paired']['lo']:+.3f}, {s['ndcg10_paired']['hi']:+.3f}])",
    )
    frame_panels(fig)
    out = OUTDIR / "01-rank-shift.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size // 1024}KB)")

    # Figure 02: nDCG@10 per bucket against the shuffle null, and wall time per query.
    fig, top = figure(
        15,
        7.4,
        2,
        "jev, gate replay",
        "Graded relevance per bucket, and the time each query cost",
        meta=(
            f"left: mean nDCG@10 over qrels (4,681 graded pairs; unjudged pairs grade 0), per bucket and overall, grey: shuffle null "
            f"{s['null']['ndcg10_mean']:.3f} +/- {s['null']['ndcg10_sd']:.3f} overall | paired Jev - served: "
            f"{s['ndcg10_paired']['wins']}/{s['ndcg10_paired']['ties']}/{s['ndcg10_paired']['losses']} wins/ties/losses, mean "
            f"{s['ndcg10_paired']['mean']:+.3f} [{s['ndcg10_paired']['lo']:+.3f}, {s['ndcg10_paired']['hi']:+.3f}] | right: Jev wall "
            f"time per query against the 1 s budget | {s['model']} {s['commit']}"
        ),
    )
    h = top - 0.19
    ax = fig.add_axes([MARGIN + 0.03, 0.13, 0.50, h])
    style_axes(ax)
    buckets = ["overall"] + sorted(s["per_bucket"])
    x = np.arange(len(buckets))
    for j, (arm, col) in enumerate((("served", TEXT), ("qwen3", BLUE), ("jev", GOLD))):
        vals = []
        for b in buckets:
            sel = [
                p["ndcg"][arm]
                for p in rows
                if (b == "overall" or p["bucket"] == b) and p["ndcg"][arm] == p["ndcg"][arm]
            ]
            vals.append(float(np.mean(sel)) if sel else float("nan"))
        if all(v != v for v in vals):
            continue  # the July bench has no ordering, so no graded score for Qwen3
        ax.bar(x + (j - 1) * w, vals, w, color=col, edgecolor=BG)
        for xi, val in zip(x + (j - 1) * w, vals):
            ax.text(xi, val + 0.01, f"{val:.2f}", color=col, fontsize=8, ha="center")
    ax.axhspan(0, s["null"]["ndcg10_mean"], color=DIM, alpha=0.9, zorder=0)
    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{b} (n={sum(1 for p in rows if b == 'overall' or p['bucket'] == b)})" for b in buckets]
    )
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("mean nDCG@10")
    panel_title(
        ax,
        "nDCG@10: served (white), Jev (gold); grey: random order (no Qwen3: the July bench kept ranks only)",
        width=56,
    )

    ax2 = fig.add_axes([MARGIN + 0.60, 0.13, 0.33, h])
    style_axes(ax2)
    walls = np.array([p["wall_s"] for p in rows])
    ax2.hist(walls, bins=30, color=GOLD, edgecolor=BG)
    ax2.axvline(BARS["wall_s"], color=RED, linewidth=1.0)
    ax2.text(BARS["wall_s"], ax2.get_ylim()[1] * 0.9, " budget 1 s", color=RED, fontsize=9)
    ax2.axvline(float(np.median(walls)), color=TEXT, linewidth=1.0, linestyle=":")
    ax2.text(
        float(np.median(walls)),
        ax2.get_ylim()[1] * 0.75,
        f" median {np.median(walls) * 1000:.0f} ms",
        color=TEXT,
        fontsize=9,
    )
    ax2.set_xlim(0, max(1.1, walls.max() * 1.05))
    ax2.set_xlabel("Jev wall time per query, seconds (split queries summed)")
    ax2.set_ylabel("queries")
    panel_title(ax2, "Time per query", width=40)
    verdict(
        fig,
        f"nDCG@10 served {s['ndcg10']['served']:.3f} · Jev {s['ndcg10']['jev']:.3f} · null "
        f"{s['null']['ndcg10_mean']:.3f} · Jev beats served in {s['ndcg10_paired']['wins']}/{n}",
    )
    frame_panels(fig)
    out = OUTDIR / "02-graded-and-time.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size // 1024}KB)")
    _ = MUTED


if __name__ == "__main__":
    {"collect": collect, "stability": stability, "score": score, "draw": draw}[sys.argv[1]]()
