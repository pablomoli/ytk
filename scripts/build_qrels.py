"""Build and judge the pooled retrieval qrels artifact (#91).

The benchmark input must contain ``ranking_before`` and ``ranking_after`` for
each frozen query (experiments/rerank_bench.py writes both). Candidate origins
are discarded in the pool handed to Claude, keeping the judge blind.

    uv run python scripts/build_qrels.py \
      --benchmark experiments/rerank_bench_10x512_results.json

The committed pool contains ids only; private document text is read from the
live store and never written into the public repository. Qrels are checkpointed
after every Claude batch, while written reasons go to ~/.ytk for spot checks.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ytk import retrieval_gate
from ytk.relevance import ndcg_report

PROMPT_VERSION = "qrels-v1"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
POOL_DEPTH = 30  # top-10 metric plus the reranker/HNSW candidate horizon
RUBRIC = """Grade how relevant the Document is to the Query on this scale:
3 = directly answers or is the clearly sought item, with specific matching substance
2 = substantially relevant and useful, but incomplete or not the primary sought item
1 = tangentially related; shares a topic but would be a weak search result
0 = irrelevant or misleading for this query

Judge only semantic relevance. Do not reward wording overlap by itself. A concise
document can earn 3. Return one grade, a brief reason, and confidence for every
pair. You are not told which retrieval system produced any document."""


def _document(doc_id: str) -> str:
    from ytk import store

    namespace, _, key = doc_id.partition("::")
    if namespace == "vid":
        col = store._videos_collection()
    elif namespace == "mem":
        col = store._memories_collection()
    elif namespace == "seg":
        col = store._segments_collection()
    else:
        raise ValueError(f"unknown candidate namespace: {doc_id}")
    got = col.get(ids=[key], include=["documents"])
    if not got["ids"]:
        raise ValueError(f"candidate missing from live store: {doc_id}")
    return got["documents"][0] or ""


def build_pool(benchmark_path: Path) -> dict:
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    by_query = {row["gold_id"]: row for row in benchmark["rows"]}
    queries = retrieval_gate.load_queries(retrieval_gate.QUERIES_PATH)
    live = retrieval_gate.run_live_gate(top_k=POOL_DEPTH)
    pairs: list[dict] = []
    for query in queries:
        query_id = query["gold_id"]
        row = by_query.get(query_id)
        if row is None:
            raise ValueError(f"benchmark has no row for {query_id}")
        candidates = list(dict.fromkeys(
            row["ranking_before"][:10]
            + row["ranking_after"][:10]
            + live["rankings"].get(query_id, [])[:POOL_DEPTH]
        ))
        for doc_id in candidates:
            pairs.append({
                "query_id": query_id,
                "query": query["query"],
                "bucket": query["bucket"],
                "doc_id": doc_id,
                "document": _document(doc_id),
            })
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "variants": [
            "v2-bi-encoder",
            "v2-live-production",
            "v2-live-production-depth15-guard",
            f"v2-live-production-depth{POOL_DEPTH}-guard",
            (
                f"v2+{benchmark['summary']['model']}"
                f"@{benchmark['summary'].get('model_revision', 'unversioned')}"
                f"-depth{benchmark['summary']['depth']}"
                f"-maxlen{benchmark['summary']['max_length']}"
            ),
        ],
        "provenance": retrieval_gate.live_provenance(
            retrieval_gate.QUERIES_PATH, top_k=10
        ),
        "pairs": pairs,
        # Used to score the exact current production ordering, stripped by
        # public_pool before the repo artifact is written.
        "live_rankings": live["rankings"],
    }


def public_pool(pool: dict) -> dict:
    """Strip private live-store text before writing the repo artifact."""
    return {
        **{key: value for key, value in pool.items() if key != "live_rankings"},
        "pairs": [
            {key: value for key, value in pair.items() if key != "document"}
            for pair in pool["pairs"]
        ],
    }


def _schema(pair_ids: list[str]) -> str:
    return json.dumps({
        "type": "object",
        "properties": {
            "labels": {
                "type": "array",
                "minItems": len(pair_ids),
                "maxItems": len(pair_ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "pair_id": {"type": "string", "enum": pair_ids},
                        "grade": {"type": "integer", "minimum": 0, "maximum": 3},
                        "reason": {"type": "string"},
                        "confidence": {
                            "type": "string", "enum": ["low", "medium", "high"]
                        },
                    },
                    "required": ["pair_id", "grade", "reason", "confidence"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["labels"],
        "additionalProperties": False,
    }, separators=(",", ":"))


def _batches(pairs: list[dict], max_pairs: int = 75,
             max_chars: int = 180_000) -> list[list[dict]]:
    batches: list[list[dict]] = []
    current: list[dict] = []
    chars = 0
    for pair in pairs:
        size = len(pair["query"]) + len(pair["document"])
        if current and (len(current) >= max_pairs or chars + size > max_chars):
            batches.append(current)
            current, chars = [], 0
        current.append(pair)
        chars += size
    if current:
        batches.append(current)
    return batches


def _judge_batch(pairs: list[dict], model: str) -> list[dict]:
    opaque = []
    pair_ids = []
    for index, pair in enumerate(pairs):
        pair_id = f"p{index}"
        pair_ids.append(pair_id)
        opaque.append({
            "pair_id": pair_id,
            "query": pair["query"],
            "document": pair["document"],
        })
    prompt = (
        RUBRIC + "\n\nPairs to grade:\n"
        + json.dumps(opaque, ensure_ascii=False, separators=(",", ":"))
    )
    result = subprocess.run(
        [
            "claude", "-p", "--safe-mode", "--model", model,
            "--tools", "", "--no-session-persistence",
            "--output-format", "json", "--json-schema", _schema(pair_ids),
            prompt,
        ],
        capture_output=True, text=True, check=True,
    )
    outer = json.loads(result.stdout)
    structured = outer.get("structured_output")
    if not structured:
        raise RuntimeError(f"Claude returned no structured output: {outer.get('result')}")
    by_id = {row["pair_id"]: row for row in structured["labels"]}
    if set(by_id) != set(pair_ids):
        raise RuntimeError("Claude did not return every opaque pair exactly once")
    return [by_id[pair_id] for pair_id in pair_ids]


def judge_pool(pool: dict, qrels_path: Path, model: str, review_path: Path,
               workers: int = 1) -> dict:
    pool_stamp = {
        "variants": pool["variants"],
        "provenance": pool["provenance"],
        "pair_count": len(pool["pairs"]),
    }
    if qrels_path.exists():
        qrels = json.loads(qrels_path.read_text(encoding="utf-8"))
        if qrels.get("judge") != {"model": model, "prompt_version": PROMPT_VERSION}:
            raise ValueError("existing qrels uses a different judge or prompt version")
        prior_pool = qrels.get("pool") or {}
        prior_prov = {
            key: value for key, value in prior_pool.get("provenance", {}).items()
            if key != "producing_git_commit"
        }
        current_prov = {
            key: value for key, value in pool_stamp["provenance"].items()
            if key != "producing_git_commit"
        }
        if prior_prov != current_prov:
            raise ValueError("existing qrels belongs to a different corpus/query pool")
        if not set(prior_pool.get("variants", [])).issubset(pool_stamp["variants"]):
            raise ValueError("existing qrels variants are not present in the new pool")
        current_pairs = {(row["query_id"], row["doc_id"]) for row in pool["pairs"]}
        existing_pairs = {(row["query_id"], row["doc_id"]) for row in qrels["labels"]}
        if not existing_pairs.issubset(current_pairs):
            raise ValueError("new candidate pool dropped already-judged pairs")
        qrels["pool"] = pool_stamp
    else:
        qrels = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "judge": {"model": model, "prompt_version": PROMPT_VERSION},
            "rubric": RUBRIC,
            "pool": pool_stamp,
            "labels": [],
        }

    done = {(row["query_id"], row["doc_id"]) for row in qrels["labels"]}
    pending = [pair for pair in pool["pairs"]
               if (pair["query_id"], pair["doc_id"]) not in done]
    if review_path.exists():
        review = json.loads(review_path.read_text(encoding="utf-8"))
    else:
        review = []
    batches = _batches(pending)

    def checkpoint(batch: list[dict], judged: list[dict], number: int) -> None:
        for pair, label in zip(batch, judged):
            qrels["labels"].append({
                "query_id": pair["query_id"],
                "doc_id": pair["doc_id"],
                "grade": label["grade"],
                "confidence": label["confidence"],
            })
            review.append({
                "query_id": pair["query_id"],
                "doc_id": pair["doc_id"],
                "reason": label["reason"],
            })
        qrels["labels"].sort(key=lambda row: (row["query_id"], row["doc_id"]))
        temp = qrels_path.with_suffix(qrels_path.suffix + ".tmp")
        temp.write_text(json.dumps(qrels, indent=2) + "\n", encoding="utf-8")
        temp.replace(qrels_path)
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        print(
            f"judged batch {number}/{len(batches)} "
            f"({len(qrels['labels'])}/{len(pool['pairs'])} pairs)",
            flush=True,
        )

    if workers <= 1:
        for number, batch in enumerate(batches, 1):
            checkpoint(batch, _judge_batch(batch, model), number)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_judge_batch, batch, model): (number, batch)
                for number, batch in enumerate(batches, 1)
            }
            completed = 0
            for future in as_completed(futures):
                _, batch = futures[future]
                completed += 1
                checkpoint(batch, future.result(), completed)
    return qrels


def measure_benchmark(benchmark: dict, qrels: dict,
                      live_rankings: dict[str, list[str]]) -> dict:
    """Score both pooled variants against the frozen labels."""
    queries = retrieval_gate.load_queries(retrieval_gate.QUERIES_PATH)
    after = {row["gold_id"]: row["ranking_after"] for row in benchmark["rows"]}
    return {
        "v2-live-production": ndcg_report(queries, live_rankings, qrels, k=10),
        "v2+reranker": ndcg_report(queries, after, qrels, k=10),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--pool", type=Path,
                        default=retrieval_gate.DATA_DIR / "candidate_pool.json")
    parser.add_argument("--qrels", type=Path, default=retrieval_gate.QRELS_PATH)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument(
        "--review", type=Path,
        default=Path.home() / ".ytk" / "eval" / "qrels-review.json",
    )
    parser.add_argument("--pool-only", action="store_true")
    args = parser.parse_args()

    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    pool = build_pool(args.benchmark)
    args.pool.parent.mkdir(parents=True, exist_ok=True)
    args.pool.write_text(
        json.dumps(public_pool(pool), indent=2) + "\n", encoding="utf-8"
    )
    print(f"pool: {len(pool['pairs'])} pairs -> {args.pool}", flush=True)
    if not args.pool_only:
        qrels = judge_pool(
            pool, args.qrels, args.model, args.review, workers=args.workers
        )
        qrels["evaluations"] = measure_benchmark(
            benchmark, qrels, pool["live_rankings"]
        )
        args.qrels.write_text(json.dumps(qrels, indent=2) + "\n", encoding="utf-8")
        low = sum(row["confidence"] == "low" for row in qrels["labels"])
        print(f"qrels: {len(qrels['labels'])} labels, {low} low-confidence")
        for variant, report in qrels["evaluations"].items():
            print(
                f"  {variant}: nDCG@10 {report['ndcg@10']:.4f}, "
                f"coverage {report['label_coverage']:.1%}"
            )


if __name__ == "__main__":
    main()
