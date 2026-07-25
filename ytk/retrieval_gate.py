# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
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

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

# hit@k reported everywhere; hit@5 and hit@10 gate pass/fail, hit@1 is
# informational (too noisy at ~150 queries to gate on)
_KS = (1, 5, 10)
_GATED_METRICS = ("hit@5", "hit@10")
_DEFAULT_TOLERANCE = 0.02
# above this fraction of unresolvable golds the query set itself is stale
# and shrinking denominators would mask real regressions
_MAX_MISSING_FRACTION = 0.10
# above this fraction the freeze is no longer being honoured: post-baseline
# documents ate so much of the over-fetch that scores understate retrieval
_MAX_STARVED_FRACTION = 0.10
# over-fetch multiple on top_k, so filtering to the frozen corpus still
# leaves a full window. Scaled by observed growth in run_live_gate.
_MIN_OVERFETCH = 3
_MAX_OVERFETCH = 20

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "eval" / "retrieval"
QUERIES_PATH = DATA_DIR / "queries.jsonl"
BASELINE_PATH = DATA_DIR / "baseline.json"
QRELS_PATH = DATA_DIR / "qrels.json"
FROZEN_CORPUS_PATH = DATA_DIR / "frozen_corpus.json"


def overfetch_factor(frozen_size: int, live_size: int) -> int:
    """How many multiples of top_k to fetch before filtering to the freeze.

    Every post-baseline document is a potential window-filler that yields
    nothing scoreable, so the window has to grow with the corpus. Scaling by
    the observed growth ratio keeps the frozen top-k full without pinning a
    constant that rots as the vault fills up.
    """
    if frozen_size <= 0:
        return _MIN_OVERFETCH
    growth = -(-live_size // frozen_size)  # ceil, ints only
    return max(_MIN_OVERFETCH, min(_MAX_OVERFETCH, growth + 1))


def frozen_corpus_sha256(frozen_ids: set[str]) -> str:
    """Identity of the frozen scoring surface — order-independent."""
    digest = hashlib.sha256()
    for key in sorted(frozen_ids):
        digest.update(key.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_frozen_corpus(frozen_ids: set[str], path: Path | str | None = None) -> None:
    """Pin the scoring surface. Sorted so the file diffs meaningfully.

    path resolves at call time rather than as a captured default, so
    redirecting FROZEN_CORPUS_PATH actually redirects the write.
    """
    path = FROZEN_CORPUS_PATH if path is None else path
    payload = {
        "note": (
            "Document ids that existed when the baseline was stamped (#111). "
            "ytk eval scores only these, so ordinary corpus growth cannot move "
            "hit@k. Re-stamp deliberately with: ytk eval --update-baseline"
        ),
        "sha256": frozen_corpus_sha256(frozen_ids),
        "count": len(frozen_ids),
        "ids": sorted(frozen_ids),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_frozen_ids(path: Path | str | None = None) -> set[str] | None:
    """Load the pinned surface, or None if it was never stamped.

    None rather than an empty set: an unstamped freeze must fail provenance
    and ask for a re-stamp, not silently score against the live corpus.
    """
    path = Path(FROZEN_CORPUS_PATH if path is None else path)
    if not path.exists():
        return None
    return set(json.loads(path.read_text(encoding="utf-8"))["ids"])


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
    frozen_ids: set[str] | None = None,
    fetch_k: int | None = None,
) -> dict:
    """Score the query set: rank of each resolved gold in its searcher's list.

    Queries whose gold cannot be resolved in the live store are excluded from
    the hit rates and reported in missing_gold — a deleted note is fixture
    rot, not a retrieval regression (compare_to_baseline caps how much rot
    is tolerated).

    frozen_ids pins the measurement surface to the documents that existed
    when the baseline was stamped (#111). Results outside it are dropped
    before ranking, so ordinary corpus growth cannot push a gold down a rank
    it never actually lost. Searchers must over-fetch for this to be lossless
    — see _live_searchers.
    """
    window = fetch_k if fetch_k is not None else top_k
    missing: list[str] = []
    outcomes: list[dict] = []
    rankings: dict[str, list[str]] = {}
    starved: list[str] = []
    for q in queries:
        gold_key = resolve_gold(q["gold_id"])
        if gold_key is None:
            missing.append(q["gold_id"])
            continue
        results = searchers[q["bucket"]](q["query"])
        if frozen_ids is not None:
            fetched = len(results)
            results = [r for r in results if r in frozen_ids]
            # Too few frozen survivors to fill the window means post-baseline
            # documents ate the over-fetch, leaving frozen docs deeper down
            # unseen — ranks past the survivors are unmeasured, not lost.
            # Only a saturated fetch proves the window was the binding
            # constraint: a searcher that returned less than it was asked for
            # has simply exhausted a small corpus, and nothing deeper exists.
            if len(results) < top_k and fetched >= window:
                starved.append(q["query"])
        results = results[:top_k]
        rankings[q["gold_id"]] = results
        rank = results.index(gold_key) if gold_key in results else None
        outcomes.append(
            {
                "query": q["query"],
                "bucket": q["bucket"],
                "gold_id": q["gold_id"],
                "rank": rank,
            }
        )

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
        "freeze_starved": starved,
        "overall": {f"hit@{k}": hits(outcomes, k) for k in _KS},
        "per_bucket": {
            b: {**{f"hit@{k}": hits(rows, k) for k in _KS}, "n": len(rows)}
            for b, rows in sorted(by_bucket.items())
        },
        "misses": [r for r in outcomes if r["rank"] is None or r["rank"] >= 5],
        "rankings": rankings,
    }


def make_baseline(report: dict, epoch: str, authored: str) -> dict:
    """Freeze a report as the baseline the next run is compared against."""
    baseline = {
        "epoch": epoch,
        "authored": authored,
        "frozen_corpus": (
            "Scoring is restricted to the document ids listed in "
            "eval/retrieval/frozen_corpus.json, captured when this baseline was "
            "stamped (#111). Documents ingested since then are retrieved but not "
            "scored, so ordinary corpus growth cannot move hit@k and a red gate "
            "means a real regression. Re-stamp both together — deliberately, "
            "never to launder a regression — with: ytk eval --update-baseline"
        ),
        "top_k": report["top_k"],
        "n_queries": report["n_queries"],
        "tolerance": _DEFAULT_TOLERANCE,
        "overall": report["overall"],
        "per_bucket": report["per_bucket"],
    }
    if "provenance" in report:
        baseline["provenance"] = report["provenance"]
    if "graded" in report:
        baseline["graded"] = report["graded"]
    return baseline


def compare_to_baseline(report: dict, baseline: dict) -> list[str]:
    """Return regression messages (empty list = gate passes).

    Gates on overall hit@5/hit@10 with the baseline's tolerance, and on
    fixture rot (too many golds missing from the store). Per-bucket numbers
    are reported for diagnosis but do not gate: at ~30-80 queries per bucket
    a single flipped query moves them past any sane threshold.
    """
    failures: list[str] = []
    report_prov = report.get("provenance")
    baseline_prov = baseline.get("provenance")
    if report_prov is not None or baseline_prov is not None:
        if report_prov is None or baseline_prov is None:
            failures.append(
                "baseline provenance is missing or incomplete; re-stamp with "
                "ytk eval --update-baseline"
            )
        else:
            # producing_git_commit is traceability, not an equality gate: a
            # baseline necessarily survives later commits. Everything that
            # determines the measured query/model surface must match.
            #
            # corpus_fingerprint is deliberately absent (#111). It hashes the
            # whole live store, which grows every day by design, so gating on
            # it made the gate permanently red for a non-quality reason and
            # trained everyone to --no-verify past it. The scored surface is
            # pinned by frozen_corpus_sha256 instead: growth no longer moves
            # the measurement, and redefining the freeze is what now fails.
            for field in (
                "query_file_sha256",
                "query_count",
                "frozen_corpus_sha256",
                "collection_epoch",
                "embedding_model",
                "embedding_revision",
                "query_instruction",
                "max_seq_length",
                "top_k",
            ):
                if report_prov.get(field) != baseline_prov.get(field):
                    failures.append(
                        f"provenance mismatch for {field}: current "
                        f"{report_prov.get(field)!r} != baseline "
                        f"{baseline_prov.get(field)!r}"
                    )
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
        starved = report.get("freeze_starved", [])
        starved_fraction = len(starved) / report["n_queries"]
        if starved_fraction > _MAX_STARVED_FRACTION:
            failures.append(
                f"{len(starved)}/{report['n_queries']} queries had their frozen "
                f"window starved by post-baseline documents ({starved_fraction:.0%}) "
                "— raise the over-fetch factor or re-stamp the baseline with "
                "ytk eval --update-baseline"
            )
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

    video_ids = {i for i in store._videos_collection().get(include=[])["ids"] if "#" not in i}
    segment_ids = set(store._segments_collection().get(include=[])["ids"])

    mem = store._memories_collection().get(include=["metadatas"])
    by_path: dict[str, str] = {}
    for meta in store.chroma_field(mem["metadatas"], "metadatas"):
        sp = store.meta_str(meta, "source_path")
        if sp:
            # Subscript, not meta_str: a memory without a doc_id should still
            # blow up here rather than resolve to "" and score as a silent miss.
            doc_id = meta["doc_id"]
            by_path[sp] = doc_id if isinstance(doc_id, str) else str(doc_id)

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


def _live_searchers(fetch_k: int) -> dict[str, Callable[[str], list[str]]]:
    """Production-path searchers.

    videos and memories rank in search_all's merged list — the ranking users
    actually see, gold competing across buckets. segments rank in the
    segments collection, mirroring search_segments (which does not expose
    ids, so the query call is inlined here with the same arguments).

    fetch_k is the over-fetch window, not the scoring window: evaluate()
    filters these lists to the frozen corpus and only then truncates to
    top_k (#111).
    """
    from ytk import store

    def unified(query: str) -> list[str]:
        prefix = {"video": "vid", "memory": "mem"}
        return [f"{prefix[r.type]}::{r.doc_id}" for r in store.search_all(query, n=fetch_k)]

    def segments(query: str) -> list[str]:
        col = store._segments_collection()
        if col.count() == 0:
            return []
        res = col.query(
            query_embeddings=[store._embed_query(query)],
            n_results=min(fetch_k, col.count()),
        )
        return [f"seg::{i}" for i in res["ids"][0]]

    return {"videos": unified, "memories": unified, "segments": segments}


def snapshot_frozen_ids() -> set[str]:
    """Every live document id, in the key space the searchers emit.

    Memory chunks (doc_id#1, doc_id#2 …) collapse to their base doc_id
    because search_all collapses them before ranking — the freeze has to
    match what a searcher can actually return, not what chroma stores.
    """
    from ytk import store

    frozen = {
        f"vid::{i}" for i in store._videos_collection().get(include=[])["ids"] if "#" not in i
    }
    frozen |= {f"seg::{i}" for i in store._segments_collection().get(include=[])["ids"]}

    mem = store._memories_collection().get(include=["metadatas"])
    for meta in store.chroma_field(mem["metadatas"], "metadatas"):
        doc_id = meta.get("doc_id")
        if doc_id:
            frozen.add(f"mem::{doc_id}")
    return frozen


def live_provenance(
    queries_path: Path | str,
    top_k: int,
    frozen_ids: set[str] | None = None,
) -> dict:
    """Fingerprint the exact live retrieval surface behind one gate run."""
    from ytk import store

    path = Path(queries_path)
    digest = hashlib.sha256()
    counts: dict[str, int] = {}
    for name, col in (
        ("videos", store._videos_collection()),
        ("memories", store._memories_collection()),
        ("segments", store._segments_collection()),
    ):
        got = col.get(include=["documents", "metadatas"])
        rows = sorted(
            zip(
                got["ids"],
                store.chroma_field(got["documents"], "documents"),
                store.chroma_field(got["metadatas"], "metadatas"),
            ),
            key=lambda row: row[0],
        )
        counts[name] = len(rows)
        for vector_id, document, metadata in rows:
            digest.update(
                json.dumps(
                    [name, vector_id, document or "", metadata or {}],
                    sort_keys=True,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            digest.update(b"\n")

    cfg = store._EPOCHS[store.EMBEDDING_EPOCH]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    return {
        "query_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "query_count": len(load_queries(path)),
        # traceability only — the scored surface is frozen_corpus_sha256.
        # This moves on every ingest and is deliberately not gated (#111).
        "corpus_fingerprint": digest.hexdigest(),
        "frozen_corpus_sha256": (
            frozen_corpus_sha256(frozen_ids) if frozen_ids is not None else None
        ),
        "frozen_corpus_size": len(frozen_ids) if frozen_ids is not None else None,
        "collection_counts": counts,
        "collection_epoch": store.EMBEDDING_EPOCH,
        "embedding_model": cfg["model"],
        "embedding_revision": cfg.get("revision"),
        "query_instruction": cfg["query_prefix"],
        "max_seq_length": cfg["max_seq"],
        "top_k": top_k,
        "producing_git_commit": commit,
    }


def run_live_gate(queries_path: Path | str = QUERIES_PATH, top_k: int = 10) -> dict:
    """Run the frozen query set against the live store via production paths.

    Scoring is restricted to the frozen corpus (#111) so daily ingest cannot
    move hit@k. The live store is still queried — over-fetched, then filtered
    — so a genuine ranking regression inside the frozen set still shows up.
    """
    queries = load_queries(queries_path)
    frozen_ids = load_frozen_ids()
    if frozen_ids is None:
        fetch_k = top_k
    else:
        fetch_k = top_k * overfetch_factor(len(frozen_ids), len(snapshot_frozen_ids()))
    report = evaluate(
        queries,
        _live_searchers(fetch_k),
        _live_resolver(),
        top_k=top_k,
        frozen_ids=frozen_ids,
        fetch_k=fetch_k,
    )
    report["fetch_k"] = fetch_k
    report["provenance"] = live_provenance(queries_path, top_k, frozen_ids)
    if QRELS_PATH.exists() and top_k >= 10:
        from .relevance import load_qrels, ndcg_report

        report["graded"] = ndcg_report(queries, report["rankings"], load_qrels(QRELS_PATH), k=10)
    return report
