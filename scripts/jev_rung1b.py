"""Section 55: a second Jev arm against section 54's standing bars.

Registration is docs/assets/55-jev-second-arm/README.md, committed with this
script before `collect` first ran. Primary arm: reciprocal rank fusion of
served order and a Noul with title fields and stricter wording. Secondary:
that Noul alone.

    uv run python scripts/jev_rung1b.py collect
    uv run python scripts/jev_rung1b.py stability
    uv run python scripts/jev_rung1b.py score
    uv run --with matplotlib python scripts/jev_rung1b.py draw
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
from jev_rung0 import ROOT, commit_sha
from jev_rung1 import BARS, DEPTH, N_NULL, SPLIT_CHARS, WINDOW, _ndcg

OUTDIR = ROOT / "docs" / "assets" / "55-jev-second-arm"
SIDECAR = OUTDIR / "rung1b.json"
PARTIAL = OUTDIR / "rung1b.partial.jsonl"
STABILITY = OUTDIR / "rung1b-stability.json"
SCORES = OUTDIR / "rung1b-scores.json"
PRIOR_STAB = ROOT / "docs" / "assets" / "54-jev-gate-replay" / "rung1-stability.json"
PRIOR_SCORES = ROOT / "docs" / "assets" / "54-jev-gate-replay" / "rung1-scores.json"
RRF_K = 60
SEED = 55
STAB_BAR = 18

ASK = "Does `candidates.{k}` hold the specific thing `query` asks for, not merely a similar topic?"
TRUE = "Its title or text names the specific item, decision, session, person or fact in `query`."
FALSE = "The same project or topic only, a different item, or nothing related."


def titles_for(store, keys: list[str]) -> dict[str, str]:
    """Title per key: stored metadata for videos and segments, filename stem for memories."""
    out: dict[str, str] = {}
    vids = [k.split("::", 1)[1] for k in keys if k.startswith("vid::")]
    mems = [k.split("::", 1)[1] for k in keys if k.startswith("mem::")]
    segs = [k.split("::", 1)[1] for k in keys if k.startswith("seg::")]
    if vids:
        got = store._videos_collection().get(
            where={"video_id": {"$in": vids}}, include=["metadatas"]
        )
        for m in got["metadatas"]:
            out[f"vid::{m['video_id']}"] = str(m.get("title", ""))
    if mems:
        got = store._memories_collection().get(
            where={"doc_id": {"$in": mems}}, include=["metadatas"]
        )
        for m in got["metadatas"]:
            out[f"mem::{m['doc_id']}"] = Path(str(m.get("source_path", ""))).stem
    if segs:
        got = store._segments_collection().get(ids=segs, include=["metadatas"])
        for i, m in zip(got["ids"], got["metadatas"]):
            out[f"seg::{i}"] = str(m.get("title", ""))
    return {k: out.get(k, "") for k in keys}


def requests_for(query: str, pairs: list[tuple[str, str, str]]):
    chars = sum(len(d) for _, _, d in pairs)
    chunks = (
        [pairs] if chars <= SPLIT_CHARS else [pairs[: len(pairs) // 2], pairs[len(pairs) // 2 :]]
    )
    for chunk in chunks:
        keys = [k for k, _, _ in chunk]
        state = {
            "query": query,
            "candidates": {
                f"c{i:02d}": {"title": t, "text": d} for i, (_, t, d) in enumerate(chunk, 1)
            },
        }
        yield keys, state, [f"c{i:02d}" for i in range(1, len(chunk) + 1)]


def ask(state, names, tag):
    import jev_client as jev

    qs = {k: jev.noul(ASK.format(k=k), TRUE, FALSE) for k in names}
    r = jev.system_one(state, qs, tag=tag)
    return [r.answers[k]["noul"] for k in names], r.input_tokens, r.latency_s, r.model


def rrf(keys: list[str], nouls: list[float]) -> list[str]:
    noul_rank = {k: i for i, k in enumerate(sorted(keys, key=lambda k: -nouls[keys.index(k)]))}
    score = {k: 1 / (RRF_K + i + 1) + 1 / (RRF_K + noul_rank[k] + 1) for i, k in enumerate(keys)}
    return sorted(keys, key=lambda k: (-score[k], keys.index(k)))


def collect() -> None:
    from rerank_bench import retrieve_with_docs

    from ytk import retrieval_gate, store

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
        titles = titles_for(store, [k for k, _ in pairs])
        triples = [(k, titles[k], d) for k, d in pairs]
        keys, nouls, tokens, lat = [], [], 0, []
        for ck, state, names in requests_for(q["query"], triples):
            vals, tok, s, model = ask(state, names, tag="rung1b-noul")
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
            "titles": [titles[k] for k in keys],
            "noul": nouls,
            "requests": len(lat),
            "latency_s": lat,
            "wall_s": sum(lat),
            "input_tokens": tokens,
        }
        rows.append(row)
        with PARTIAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        before = keys.index(gold) if gold in keys else None
        fused = rrf(keys, nouls)
        print(
            f"{n:3}/{len(queries)} {q['bucket']:8} gold {before!s:>4} -> rrf {fused.index(gold) if gold in fused else None!s:>4} "
            f"| {sum(lat) * 1000:5.0f} ms {tokens:6} tok | {q['query'][:46]}"
        )
    SIDECAR.write_text(
        json.dumps(
            {
                "generated": datetime.now(UTC).isoformat(timespec="seconds"),
                "commit": commit_sha(),
                "model": model,
                "depth": DEPTH,
                "rrf_k": RRF_K,
                "questions": {"noul": ASK, "true": TRUE, "false": FALSE},
                "rows": rows,
            },
            indent=1,
        )
    )
    PARTIAL.unlink(missing_ok=True)
    print(f"wrote {SIDECAR.relative_to(ROOT)}")


def frozen_rank(keys: list[str], gold: str, frozen: set[str]):
    kept = [k for k in keys if k in frozen][:WINDOW]
    return (kept.index(gold) if gold in kept else None), kept


def stability() -> None:
    from rerank_bench import retrieve_with_docs

    from ytk import retrieval_gate

    data = json.loads(SIDECAR.read_text())
    frozen = retrieval_gate.load_frozen_ids()
    used = {r["query"] for r in json.loads(PRIOR_STAB.read_text())["rows"]}
    pool = [i for i, r in enumerate(data["rows"]) if r["query"] not in used]
    rng = np.random.default_rng(SEED)
    picks = sorted(rng.choice(pool, 20, replace=False))
    searchers = retrieve_with_docs(DEPTH)
    out = []
    for i in picks:
        row = data["rows"][i]
        by_key = dict(searchers[row["bucket"]](row["query"]))
        if any(k not in by_key for k in row["keys"]):
            print(f"skip {row['query'][:40]}: candidate set changed")
            continue
        triples = [(k, t, by_key[k]) for k, t in zip(row["keys"], row["titles"])]
        nouls = []
        for _, state, names in requests_for(row["query"], triples):
            vals, *_ = ask(state, names, tag="rung1b-stability")
            nouls += vals
        a1, k1 = frozen_rank(rrf(row["keys"], row["noul"]), row["gold"], frozen)
        a2, k2 = frozen_rank(rrf(row["keys"], nouls), row["gold"], frozen)
        out.append(
            {
                "query": row["query"],
                "noul_rerun": nouls,
                "same_top1": k1[:1] == k2[:1],
                "same_gold_rank": a1 == a2,
                "dp_median": float(np.median(np.abs(np.array(nouls) - np.array(row["noul"])))),
            }
        )
        print(
            f"{row['query'][:50]:50} top1 {'same' if k1[:1] == k2[:1] else 'MOVED'} gold {a1} -> {a2}"
        )
    summary = {
        "n": len(out),
        "same_top1": sum(o["same_top1"] for o in out),
        "same_gold_rank": sum(o["same_gold_rank"] for o in out),
        "bar": STAB_BAR,
        "pass": bool(
            sum(o["same_top1"] for o in out) >= STAB_BAR
            and sum(o["same_gold_rank"] for o in out) >= STAB_BAR
        ),
    }
    STABILITY.write_text(
        json.dumps(
            {"generated": datetime.now(UTC).isoformat(timespec="seconds"), **summary, "rows": out},
            indent=1,
        )
    )
    print(json.dumps(summary, indent=1))


def score() -> dict:
    from ytk import retrieval_gate

    data = json.loads(SIDECAR.read_text())
    frozen = retrieval_gate.load_frozen_ids()
    qrels = json.load(retrieval_gate.QRELS_PATH.open())
    grades: dict[str, dict[str, int]] = {}
    for lab in qrels["labels"]:
        grades.setdefault(lab["query_id"], {})[lab["doc_id"]] = int(lab["grade"])
    prior = {p["query"]: p for p in json.loads(PRIOR_SCORES.read_text())["rows"]}
    rng = np.random.default_rng(SEED)
    names = ["served", "rrf", "noul"]
    arms = {n: [] for n in names}
    nd = {n: [] for n in names}
    null_nd, null_h = [], {1: [], 5: [], 10: []}
    per_row = []
    for r in data["rows"]:
        g = grades.get(r["gold_id"], {})
        served = r["keys"]
        noul = [k for _, k in sorted(zip(r["noul"], served), key=lambda t: -t[0])]
        fused = rrf(served, r["noul"])
        ranks = {}
        for n, keys in (("served", served), ("rrf", fused), ("noul", noul)):
            rk, kept = frozen_rank(keys, r["gold"], frozen)
            ranks[n] = rk
            arms[n].append(rk)
            nd[n].append(_ndcg(kept, g))
        p = prior.get(r["query"], {}).get("ranks", {})
        ranks["jev54"] = p.get("jev")
        ranks["qwen3"] = p.get("qwen3")
        pool = [k for k in served if k in frozen]
        pn, ph = [], {1: [], 5: [], 10: []}
        for _ in range(N_NULL):
            perm = list(rng.permutation(pool))[:WINDOW]
            pn.append(_ndcg(perm, g))
            rk = perm.index(r["gold"]) if r["gold"] in perm else None
            for k in ph:
                ph[k].append(rk is not None and rk < k)
        null_nd.append(pn)
        for k in ph:
            null_h[k].append(ph[k])
        per_row.append(
            {
                "query": r["query"],
                "bucket": r["bucket"],
                "ranks": ranks,
                "ndcg": {n: nd[n][-1] for n in nd},
                "wall_s": r["wall_s"],
            }
        )

    def hits(rs, k):
        return sum(1 for x in rs if x is not None and x < k) / len(rs)

    n = len(data["rows"])
    out = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": commit_sha(),
        "model": data["model"],
        "n": n,
        "hit": {nm: {f"hit@{k}": hits(arms[nm], k) for k in (1, 5, 10)} for nm in names},
        "hit_reference": {
            nm: {f"hit@{k}": hits([p["ranks"][nm] for p in per_row], k) for k in (1, 5, 10)}
            for nm in ("jev54", "qwen3")
        },
        "per_bucket": {
            b: {
                nm: {
                    f"hit@{k}": hits([p["ranks"][nm] for p in per_row if p["bucket"] == b], k)
                    for k in (1, 5, 10)
                }
                for nm in names
            }
            for b in sorted({p["bucket"] for p in per_row})
        },
        "ndcg10": {nm: float(np.nanmean(nd[nm])) for nm in names},
        "null": {
            "ndcg10_mean": float(np.nanmean(np.array(null_nd), axis=0).mean()),
            "ndcg10_sd": float(np.nanmean(np.array(null_nd), axis=0).std()),
            **{f"hit@{k}_mean": float(np.array(null_h[k]).mean()) for k in null_h},
        },
        "wall_s": {},
        "requests": sum(r["requests"] for r in data["rows"]),
        "input_tokens": sum(r["input_tokens"] for r in data["rows"]),
        "bars": BARS,
        "rows": per_row,
    }
    walls = sorted(r["wall_s"] for r in data["rows"])
    out["wall_s"] = {
        "median": walls[len(walls) // 2],
        "p95": walls[int(0.95 * len(walls))],
        "max": walls[-1],
    }
    for nm in ("rrf", "noul"):
        d = np.array(nd[nm]) - np.array(nd["served"])
        boots = [rng.choice(d, len(d), replace=True).mean() for _ in range(N_NULL)]
        demoted = sum(
            1
            for p in per_row
            if p["ranks"]["served"] is not None
            and p["ranks"]["served"] < 5
            and (p["ranks"][nm] is None or p["ranks"][nm] >= 5)
        )
        promoted = sum(
            1
            for p in per_row
            if (p["ranks"]["served"] is None or p["ranks"]["served"] >= 5)
            and p["ranks"][nm] is not None
            and p["ranks"][nm] < 5
        )
        out[f"{nm}_paired"] = {
            "wins": int((d > 1e-9).sum()),
            "ties": int((np.abs(d) <= 1e-9).sum()),
            "losses": int((d < -1e-9).sum()),
            "mean": float(d.mean()),
            "lo": float(np.quantile(boots, 0.025)),
            "hi": float(np.quantile(boots, 0.975)),
            "demoted": demoted,
            "promoted": promoted,
        }
    h = out["hit"]["rrf"]
    pr = out["rrf_paired"]
    out["verdict"] = {
        "B1_gain": bool(h["hit@1"] >= BARS["hit@1"] and h["hit@5"] >= BARS["hit@5"]),
        "B2_speed": bool(out["wall_s"]["median"] <= BARS["wall_s"]),
        "B3_damage": bool(pr["demoted"] <= BARS["demoted"] and pr["lo"] > 0),
    }
    if STABILITY.exists():
        st = json.loads(STABILITY.read_text())
        out["stability"] = {k: v for k, v in st.items() if k != "rows"}
        out["verdict"]["S_stability"] = bool(st["pass"])
    out["verdict"]["rung1_pass"] = all(out["verdict"].values())
    SCORES.write_text(json.dumps(out, indent=1))
    for nm in names:
        print(
            f"{nm:7}",
            {k: round(v, 4) for k, v in out["hit"][nm].items()},
            f"nDCG@10 {out['ndcg10'][nm]:.4f}",
        )
    for nm in ("jev54", "qwen3"):
        print(
            f"{nm:7}",
            {k: round(v, 4) for k, v in out["hit_reference"][nm].items()},
            "(reference, from disk)",
        )
    print("null   ", {k: round(v, 4) for k, v in out["null"].items()})
    for nm in ("rrf", "noul"):
        print(f"{nm} vs served", out[f"{nm}_paired"])
    print(
        f"wall median {out['wall_s']['median']:.3f}s p95 {out['wall_s']['p95']:.3f}s max {out['wall_s']['max']:.3f}s"
    )
    print("verdict", out["verdict"])
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
        PURPLE,
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
    miss = WINDOW

    def rk(v):
        return miss if v is None else v

    fig, top = figure(
        17,
        8.6,
        1,
        "jev, second arm",
        "The gate's 156 golds again: served order against the fused arm, the Noul alone, and section 54's Noul",
        meta=(
            f"{n} frozen queries, production top-{DEPTH}, frozen filter, window {WINDOW} | primary arm: reciprocal rank fusion "
            f"(k = {RRF_K}) of served rank and a Noul with titles and stricter wording; secondary: that Noul alone; section 54's "
            f"Noul from disk | right: hit@k, red: the standing bars, grey: random order per k | {s['requests']} requests, "
            f"{s['input_tokens']:,} tokens, wall median {s['wall_s']['median'] * 1000:.0f} ms | {s['model']} {s['commit']}"
        ),
    )
    h = top - 0.19
    rng = np.random.default_rng(1)
    panels = (
        ("rrf", GOLD, "served -> fused (primary)"),
        ("noul", PURPLE, "served -> new Noul alone"),
        ("jev54", BLUE, "served -> section 54's Noul"),
    )
    for j, (arm, col, title) in enumerate(panels):
        ax = fig.add_axes([MARGIN + 0.015 + j * 0.215, 0.13, 0.19, h])
        style_axes(ax)
        pts = [(rk(p["ranks"]["served"]), rk(p["ranks"][arm])) for p in rows if arm in p["ranks"]]
        xs = np.array([a for a, _ in pts], dtype=float)
        ys = np.array([b for _, b in pts], dtype=float)
        ax.plot([-0.5, miss + 0.5], [-0.5, miss + 0.5], color=RED, linewidth=0.9)
        ax.scatter(
            xs + rng.uniform(-0.3, 0.3, len(xs)),
            ys + rng.uniform(-0.3, 0.3, len(ys)),
            s=14,
            color=col,
            alpha=0.75,
        )
        ax.set_xlim(-0.6, miss + 0.6)
        ax.set_ylim(miss + 0.6, -0.6)
        ticks = list(range(WINDOW)) + [miss]
        labels = [str(t + 1) for t in range(WINDOW)] + [">"]
        ax.set_xticks(ticks)
        ax.set_xticklabels(labels)
        ax.set_yticks(ticks)
        ax.set_yticklabels(labels if j == 0 else [])
        ax.set_xlabel("gold rank, served")
        if j == 0:
            ax.set_ylabel("gold rank after")
        ax.text(
            0.98,
            0.04,
            f"{int((ys < xs).sum())} up, {int((ys > xs).sum())} down",
            transform=ax.transAxes,
            color=TEXT,
            fontsize=9,
            ha="right",
        )
        panel_title(ax, title, width=32)

    ax = fig.add_axes([MARGIN + 0.015 + 3 * 0.215, 0.13, 0.27, h])
    style_axes(ax)
    ks = ["hit@1", "hit@5", "hit@10"]
    x = np.arange(len(ks))
    w = 0.2
    series = (
        ("served", TEXT, s["hit"]["served"]),
        ("jev54", BLUE, s["hit_reference"]["jev54"]),
        ("noul", PURPLE, s["hit"]["noul"]),
        ("rrf", GOLD, s["hit"]["rrf"]),
    )
    for j, (nm, col, vals) in enumerate(series):
        v = [vals[k] for k in ks]
        ax.bar(x + (j - 1.5) * w, v, w, color=col, edgecolor=BG)
        for xi, val in zip(x + (j - 1.5) * w, v):
            ax.text(xi, val + 0.01, f"{val:.3f}", color=col, fontsize=7, ha="center")
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
    panel_title(
        ax,
        "hit@k: served (white), 54's Noul (blue), new Noul (purple), fused (gold); red: bars",
        width=44,
    )

    v = s["verdict"]
    pr = s["rrf_paired"]
    verdict(
        fig,
        f"primary arm: B1 {'pass' if v['B1_gain'] else 'FAIL'} (hit@1 {s['hit']['rrf']['hit@1']:.3f}, hit@5 {s['hit']['rrf']['hit@5']:.3f}) · "
        f"B2 {'pass' if v['B2_speed'] else 'FAIL'} ({s['wall_s']['median'] * 1000:.0f} ms) · B3 {'pass' if v['B3_damage'] else 'FAIL'} "
        f"({pr['demoted']} demoted, nDCG [{pr['lo']:+.3f}, {pr['hi']:+.3f}]) · stability "
        f"{'pass' if v.get('S_stability') else 'FAIL'} · rung 1 {'PASS' if v['rung1_pass'] else 'FAIL'}",
    )
    frame_panels(fig)
    out = OUTDIR / "01-rank-shift.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    {"collect": collect, "stability": stability, "score": score, "draw": draw}[sys.argv[1]]()
