"""E1 (#149): lexical-first hybrid retrieval — FTS5 (BM25) + Chroma via RRF.

Builds an FTS5 index over the same documents the store embeds, scores the 156
frozen queries per arm through retrieval_gate.evaluate (identical plumbing,
frozen-corpus pinning included), stratifies queries lexical/semantic/mixed,
and renders e1-hybrid-retrieval.png with paired bootstrap deltas.

    uv run --with matplotlib python scripts/e1_hybrid.py
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_field_audits import figure, footer, save, stamp
from plot_assets import BLUE, GOLD, MARGIN, RED, TEXT, panel_title, style_axes

REPO = Path(__file__).resolve().parents[1]
QUERIES = REPO / "eval" / "retrieval" / "queries.jsonl"
FTS_DB = Path.home() / ".ytk" / "e1-fts5.db"
FETCH_K = 30
TOP_K = 10
RRF_KS = [10, 60]
TOKEN = re.compile(r"[a-z0-9]{3,}")
COMMON = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "have",
        "was",
        "were",
        "are",
        "is",
        "not",
        "you",
        "your",
        "what",
        "how",
        "when",
        "where",
        "why",
        "about",
        "video",
        "note",
        "memory",
        "using",
        "used",
        "use",
        "new",
        "one",
        "two",
        "like",
        "just",
        "really",
        "them",
        "then",
        "than",
        "can",
        "does",
        "did",
        "into",
        "over",
        "some",
        "more",
        "most",
        "all",
        "any",
        "his",
        "her",
        "she",
        "he",
        "they",
        "it",
        "its",
        "our",
        "out",
        "get",
        "got",
    ]
)


def collection_docs():
    """(key, text) rows in the searchers' key space; parts concatenated."""
    from ytk import store

    rows: dict[str, list[str]] = {}
    for prefix, col in (
        ("vid", store._videos_collection()),
        ("mem", store._memories_collection()),
    ):
        got = col.get(include=["documents", "metadatas"])
        for doc, meta in zip(
            store.chroma_field(got["documents"], "documents"),
            store.chroma_field(got["metadatas"], "metadatas"),
        ):
            base = (
                store.meta_str(meta, "video_id")
                if prefix == "vid"
                else store.meta_str(meta, "doc_id")
            )
            if base:
                rows.setdefault(f"{prefix}::{base}", []).append(doc)
    got = store._segments_collection().get(include=["documents"])
    for i, doc in zip(got["ids"], store.chroma_field(got["documents"], "documents")):
        rows.setdefault(f"seg::{i}", []).append(doc)
    return {k: "\n".join(v) for k, v in rows.items()}


def build_fts(docs: dict[str, str]) -> sqlite3.Connection:
    FTS_DB.unlink(missing_ok=True)
    con = sqlite3.connect(FTS_DB)
    con.execute("CREATE VIRTUAL TABLE docs USING fts5(key UNINDEXED, surface UNINDEXED, text)")
    con.executemany(
        "INSERT INTO docs VALUES (?, ?, ?)",
        [(k, "seg" if k.startswith("seg::") else "uni", t) for k, t in docs.items()],
    )
    con.commit()
    return con


def fts_query(con: sqlite3.Connection, query: str, surface: str, n: int) -> list[str]:
    toks = list(TOKEN.findall(query.lower()))
    if not toks:
        return []
    match = " OR ".join(f'"{t}"' for t in dict.fromkeys(toks))
    cur = con.execute(
        "SELECT key FROM docs WHERE docs MATCH ? AND surface = ? ORDER BY bm25(docs) LIMIT ?",
        (match, surface, n),
    )
    return [r[0] for r in cur.fetchall()]


def rrf(a: list[str], b: list[str], k: int, n: int) -> list[str]:
    score: dict[str, float] = {}
    for lst in (a, b):
        for rank, key in enumerate(lst):
            score[key] = score.get(key, 0.0) + 1.0 / (k + rank + 1)
    return sorted(score, key=score.get, reverse=True)[:n]


def stratify(query: str, gold_text: str) -> str:
    rare = [t for t in TOKEN.findall(query.lower()) if t not in COMMON]
    verbatim = sum(1 for t in rare if t in gold_text.lower())
    if not rare:
        return "semantic"
    frac = verbatim / len(rare)
    return "lexical" if frac >= 0.75 else ("semantic" if frac <= 0.25 else "mixed")


def main() -> None:
    from ytk.retrieval_gate import (
        _live_resolver,
        _live_searchers,
        evaluate,
        load_frozen_ids,
        load_queries,
    )

    queries = load_queries(QUERIES)
    frozen = load_frozen_ids()
    resolve = _live_resolver()
    live = _live_searchers(FETCH_K)

    print("building FTS5 index over store documents...")
    docs = collection_docs()
    con = build_fts(docs)
    print(f"  {len(docs)} docs indexed")

    # fetch each query once per engine; arms are derived lookups
    chroma_rank: dict[str, list[str]] = {}
    fts_rank: dict[str, list[str]] = {}
    for q in queries:
        surface = "seg" if q["bucket"] == "segments" else "uni"
        chroma_rank[q["query"]] = live[q["bucket"]](q["query"])
        fts_rank[q["query"]] = fts_query(con, q["query"], surface, FETCH_K)

    def arm(fn):
        return dict.fromkeys(("videos", "memories", "segments"), fn)

    arms: dict[str, dict] = {
        "chroma": arm(lambda q: chroma_rank[q]),
        "fts5": arm(lambda q: fts_rank[q]),
    }
    for k in RRF_KS:
        arms[f"rrf{k}"] = arm(lambda q, k=k: rrf(chroma_rank[q], fts_rank[q], k, FETCH_K))

    reports = {
        name: evaluate(queries, searchers, resolve, top_k=TOP_K, frozen_ids=frozen, fetch_k=FETCH_K)
        for name, searchers in arms.items()
    }
    for name, rep in reports.items():
        o = rep["overall"]
        print(
            f"  {name:<7} hit@1 {o['hit@1']:.3f}  hit@5 {o['hit@5']:.3f}  hit@10 {o['hit@10']:.3f}  (n={rep['n_evaluated']})"
        )

    # strata from gold text; per-query rank tables aligned by gold_id
    gold_text = {}
    for q in queries:
        g = resolve(q["gold_id"])
        gold_text[q["gold_id"]] = docs.get(g, "") if g else ""
    strata = {q["gold_id"]: stratify(q["query"], gold_text[q["gold_id"]]) for q in queries}

    def ranks(rep):
        return {o["gold_id"]: o["rank"] for o in (rep.get("misses", []) and []) or []}

    # evaluate() doesn't return all ranks — recompute per-outcome from rankings
    def outcome_ranks(name):
        out = {}
        rep = reports[name]
        for q in queries:
            lst = rep["rankings"].get(q["gold_id"])
            g = resolve(q["gold_id"])
            if lst is None or g is None:
                continue
            out[q["gold_id"]] = lst.index(g) if g in lst else None
        return out

    best_rrf = max((f"rrf{k}" for k in RRF_KS), key=lambda n: reports[n]["overall"]["hit@5"])
    base_r, fuse_r = outcome_ranks("chroma"), outcome_ranks(best_rrf)
    common = [g for g in base_r if g in fuse_r]

    def rr(rank):
        return 1.0 / (rank + 1) if rank is not None else 0.0

    deltas = np.array([rr(fuse_r[g]) - rr(base_r[g]) for g in common])
    rng = np.random.default_rng(0)
    boots = np.array([rng.choice(deltas, len(deltas)).mean() for _ in range(10_000)])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    ci_line = f"{best_rrf} vs chroma MRR delta {deltas.mean():+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}] (n={len(common)})"
    print(ci_line)

    # per-stratum hit@1/hit@5 for figure
    names = ["chroma", "fts5", best_rrf]
    strat_order = ["lexical", "mixed", "semantic"]
    per = {
        name: {
            s: (
                lambda rows: (
                    sum(
                        1
                        for g in rows
                        if outcome_ranks(name).get(g) is not None and outcome_ranks(name)[g] < 5
                    )
                    / len(rows)
                    if rows
                    else 0.0
                )
            )([g for g in common if strata[g] == s])
            for s in strat_order
        }
        for name in names
    }
    counts = {s: sum(1 for g in common if strata[g] == s) for s in strat_order}

    meta = (
        f"156 frozen queries, gate plumbing (frozen corpus, fetch {FETCH_K}) · "
        f"hit@5 overall: chroma {reports['chroma']['overall']['hit@5']:.3f} / fts5 {reports['fts5']['overall']['hit@5']:.3f} / "
        f"{best_rrf} {reports[best_rrf]['overall']['hit@5']:.3f} · {ci_line}"
    )
    fig, top = figure(
        10.5,
        6.6,
        7,
        "#149 E1 — lexical-first hybrid retrieval",
        "FTS5 + Chroma fusion vs each engine alone, hit@5 by stratum",
        meta,
    )
    ax = fig.add_axes([MARGIN + 0.05, 0.16, 1 - 2 * MARGIN - 0.09, top - 0.20])
    style_axes(ax)
    x = np.arange(len(strat_order))
    width = 0.26
    for off, (name, color) in enumerate(zip(names, (BLUE, GOLD, RED))):
        ax.bar(
            x + (off - 1) * width,
            [per[name][s] for s in strat_order],
            width,
            color=color,
            alpha=0.85,
            label=name,
        )
    ax.set_xticks(x, [f"{s}\n(n={counts[s]})" for s in strat_order])
    ax.set_ylabel("hit@5")
    ax.legend(loc="upper right", frameon=False, labelcolor=TEXT, fontsize=9)
    panel_title(ax, "Strata: fraction of the query's rare terms found verbatim in the gold doc")
    footer(
        fig,
        f"{stamp()} · encoder epoch v2 · confounds: known-item set favors lexical by construction (a fusion win is an "
        "upper bound on real-usage benefit); strata auto-tagged; FTS5 arm sees identical docs to the embedded corpus",
    )
    save(fig, "e1-hybrid-retrieval.png")


if __name__ == "__main__":
    main()
