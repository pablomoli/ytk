"""Retrieval eval regression gate (#85).

Runs the frozen known-item query set (eval/retrieval/queries.jsonl) against
the live store through the production search paths and compares hit rates to
the stored baseline (eval/retrieval/baseline.json). `ytk eval` is the
one-command entry point; the pre-commit hook runs it when the search stack
changes.

Two layers:
  - pure evaluation logic (evaluate/compare_to_baseline/make_baseline) with
    injected search functions, unit-tested without a store or model
  - live adapters (run_live_gate) that wire the production paths: search_all
    for videos+memories (the merged ranking users actually see) and the
    segments collection for dive-style queries

Gold ids use the encoder-harness namespace: vid::<video_id>,
mem::<vault-rel-path>, seg::<segment_id>. Memory golds resolve to live doc
ids via source_path metadata, so vault reorganizations that re-id notes do
not break the fixture as long as paths survive.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

# hit@k reported everywhere; hit@5 and hit@10 gate pass/fail, hit@1 is
# informational (too noisy at ~150 queries to gate on)
_KS = (1, 5, 10)
_GATED_METRICS = ("hit@5", "hit@10")
_DEFAULT_TOLERANCE = 0.02
# above this fraction of unresolvable golds the query set itself is stale
# and shrinking denominators would mask real regressions
_MAX_MISSING_FRACTION = 0.10

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "eval" / "retrieval"
QUERIES_PATH = DATA_DIR / "queries.jsonl"
BASELINE_PATH = DATA_DIR / "baseline.json"


def load_queries(path: Path | str) -> list[dict]:
    """Load the frozen query set ({"query", "gold_id", "bucket"} per line)."""
    queries = []
    # newline-only iteration: splitlines() would also split on U+2028/U+2029
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                queries.append(json.loads(line))
    return queries


def evaluate(
    queries: list[dict],
    searchers: dict[str, Callable[[str], list[str]]],
    resolve_gold: Callable[[str], str | None],
    top_k: int = 10,
) -> dict:
    """Score the query set: rank of each resolved gold in its searcher's list.

    Queries whose gold cannot be resolved in the live store are excluded from
    the hit rates and reported in missing_gold — a deleted note is fixture
    rot, not a retrieval regression (compare_to_baseline caps how much rot
    is tolerated).
    """
    missing: list[str] = []
    outcomes: list[dict] = []
    for q in queries:
        gold_key = resolve_gold(q["gold_id"])
        if gold_key is None:
            missing.append(q["gold_id"])
            continue
        results = searchers[q["bucket"]](q["query"])[:top_k]
        rank = results.index(gold_key) if gold_key in results else None
        outcomes.append({
            "query": q["query"], "bucket": q["bucket"],
            "gold_id": q["gold_id"], "rank": rank,
        })

    def hits(rows: list[dict], k: int) -> float:
        if not rows:
            return 0.0
        return sum(1 for r in rows if r["rank"] is not None and r["rank"] < k) / len(rows)

    by_bucket: dict[str, list[dict]] = {}
    for r in outcomes:
        by_bucket.setdefault(r["bucket"], []).append(r)

    return {
        "top_k": top_k,
        "n_queries": len(queries),
        "n_evaluated": len(outcomes),
        "missing_gold": missing,
        "overall": {f"hit@{k}": hits(outcomes, k) for k in _KS},
        "per_bucket": {
            b: {**{f"hit@{k}": hits(rows, k) for k in _KS}, "n": len(rows)}
            for b, rows in sorted(by_bucket.items())
        },
        "misses": [
            r for r in outcomes if r["rank"] is None or r["rank"] >= 5
        ],
    }


def make_baseline(report: dict, epoch: str, authored: str) -> dict:
    """Freeze a report as the baseline the next run is compared against."""
    return {
        "epoch": epoch,
        "authored": authored,
        "top_k": report["top_k"],
        "n_queries": report["n_queries"],
        "tolerance": _DEFAULT_TOLERANCE,
        "overall": report["overall"],
        "per_bucket": report["per_bucket"],
    }


def compare_to_baseline(report: dict, baseline: dict) -> list[str]:
    """Return regression messages (empty list = gate passes).

    Gates on overall hit@5/hit@10 with the baseline's tolerance, and on
    fixture rot (too many golds missing from the store). Per-bucket numbers
    are reported for diagnosis but do not gate: at ~30-80 queries per bucket
    a single flipped query moves them past any sane threshold.
    """
    failures: list[str] = []
    tolerance = baseline.get("tolerance", _DEFAULT_TOLERANCE)
    for metric in _GATED_METRICS:
        current = report["overall"][metric]
        floor = baseline["overall"][metric] - tolerance
        if current < floor:
            failures.append(
                f"overall {metric} regressed: {current:.3f} < baseline "
                f"{baseline['overall'][metric]:.3f} - tolerance {tolerance}"
            )
    if report["n_queries"]:
        missing_fraction = len(report["missing_gold"]) / report["n_queries"]
        if missing_fraction > _MAX_MISSING_FRACTION:
            failures.append(
                f"{len(report['missing_gold'])}/{report['n_queries']} gold docs "
                f"missing from the store ({missing_fraction:.0%}) — the query set "
                "needs repair before results are trustworthy"
            )
    return failures


# --- live adapters (import ytk.store lazily: unit tests never touch it) ---


def _live_resolver() -> Callable[[str], str | None]:
    """Map fixture gold ids to the key space the live searchers emit.

    vid:: and seg:: golds pass through if present in their collections.
    mem:: golds carry vault-relative paths; live memory ids are opaque, so
    resolve via source_path suffix match.
    """
    from ytk import store

    video_ids = {
        i for i in store._videos_collection().get(include=[])["ids"] if "#" not in i
    }
    segment_ids = set(store._segments_collection().get(include=[])["ids"])

    mem = store._memories_collection().get(include=["metadatas"])
    by_path: dict[str, str] = {}
    for meta in mem["metadatas"]:
        sp = meta.get("source_path", "")
        if sp:
            by_path[sp] = meta["doc_id"]

    def resolve(gold_id: str) -> str | None:
        kind, _, key = gold_id.partition("::")
        if kind == "vid":
            return gold_id if key in video_ids else None
        if kind == "seg":
            return gold_id if key in segment_ids else None
        if kind == "mem":
            for sp, doc_id in by_path.items():
                if sp.endswith(key):
                    return f"mem::{doc_id}"
            return None
        raise ValueError(f"unknown gold id namespace: {gold_id}")

    return resolve


def _live_searchers(top_k: int) -> dict[str, Callable[[str], list[str]]]:
    """Production-path searchers.

    videos and memories rank in search_all's merged list — the ranking users
    actually see, gold competing across buckets. segments rank in the
    segments collection, mirroring search_segments (which does not expose
    ids, so the query call is inlined here with the same arguments).
    """
    from ytk import store

    def unified(query: str) -> list[str]:
        prefix = {"video": "vid", "memory": "mem"}
        return [
            f"{prefix[r.type]}::{r.doc_id}"
            for r in store.search_all(query, n=top_k)
        ]

    def segments(query: str) -> list[str]:
        col = store._segments_collection()
        if col.count() == 0:
            return []
        res = col.query(
            query_embeddings=[store._embed_query(query)],
            n_results=min(top_k, col.count()),
        )
        return [f"seg::{i}" for i in res["ids"][0]]

    return {"videos": unified, "memories": unified, "segments": segments}


def run_live_gate(queries_path: Path | str = QUERIES_PATH, top_k: int = 10) -> dict:
    """Run the frozen query set against the live store via production paths."""
    queries = load_queries(queries_path)
    return evaluate(queries, _live_searchers(top_k), _live_resolver(), top_k=top_k)
