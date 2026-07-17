"""#86 benchmark: what fraction of the reranker headroom does Qwen3-Reranker-0.6B capture?

Headroom measured 2026-07-17 (issue #86 comment): 12/156 golds sit at rank
5-29 — a perfect reranker over top-30 lifts hit@5 0.904 -> 0.981. This
script retrieves top-30 per eval query through the production merge rules
(same collapse logic as retrieval_gate's live adapters, but keeping
documents), reranks with the cross-encoder, and compares gold ranks
before/after, plus per-query rerank latency against the +1s budget.

    uv run python experiments/rerank_bench.py [--limit N] [--depth 30] \
        [--out experiments/rerank_bench_results.json]
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RERANK_MODEL = "Qwen/Qwen3-Reranker-0.6B"
# same instruction the v2 embedder's query prefix uses (store._EPOCHS)
INSTRUCT = "Given a web search query, retrieve relevant passages that answer the query"
PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements "
    'based on the Query and the Instruct provided. Note that the answer can '
    'only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
MAX_LENGTH = 2560  # memories cap at 8000 chars (~2k tokens); truncate outliers
BATCH = 4  # MPS fp16: same caution as store.py's encode_batch lesson


class Reranker:
    def __init__(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(RERANK_MODEL, padding_side="left")
        self.model = AutoModelForCausalLM.from_pretrained(
            RERANK_MODEL, torch_dtype=torch.float16
        ).to("mps").eval()
        self.yes_id = self.tokenizer.convert_tokens_to_ids("yes")
        self.no_id = self.tokenizer.convert_tokens_to_ids("no")

    def score(self, query: str, docs: list[str]) -> list[float]:
        """P(yes) for each (query, doc) pair, batched."""
        import torch

        texts = [
            f"{PREFIX}<Instruct>: {INSTRUCT}\n<Query>: {query}\n<Document>: {d}{SUFFIX}"
            for d in docs
        ]
        scores: list[float] = []
        with torch.no_grad():
            for i in range(0, len(texts), BATCH):
                batch = self.tokenizer(
                    texts[i:i + BATCH], padding=True, truncation=True,
                    max_length=MAX_LENGTH, return_tensors="pt",
                ).to("mps")
                # logits_to_keep=1: full-sequence logits are batch x seq x
                # 152k vocab — ~3 GB fp16 per forward at 2560 tokens, which
                # thrashes MPS memory; we only need the final position
                logits = self.model(**batch, logits_to_keep=1).logits[:, -1, :]
                pair = torch.stack(
                    [logits[:, self.no_id], logits[:, self.yes_id]], dim=1
                ).float()
                scores.extend(torch.softmax(pair, dim=1)[:, 1].tolist())
        return scores


def retrieve_with_docs(depth: int):
    """Top-`depth` (key, doc) lists through the production merge rules.

    Mirrors retrieval_gate._live_searchers, which mirrors store.search_all:
    fetch depth*3 per collection, collapse parts to one hit per doc, merge
    by distance. Kept separate because production surfaces don't expose
    full documents.
    """
    from ytk import store

    def unified(query: str) -> list[tuple[str, str]]:
        emb = store._embed_query(query)
        merged: list[tuple[float, str, str]] = []
        vcol = store._videos_collection()
        if vcol.count():
            vr = vcol.query(query_embeddings=[emb], n_results=min(depth * 3, vcol.count()),
                            include=["metadatas", "documents", "distances"])
            seen: set[str] = set()
            for meta, doc, dist in zip(vr["metadatas"][0], vr["documents"][0], vr["distances"][0]):
                if meta["video_id"] in seen:
                    continue
                seen.add(meta["video_id"])
                merged.append((dist, f"vid::{meta['video_id']}", doc))
        mcol = store._memories_collection()
        if mcol.count():
            mr = mcol.query(query_embeddings=[emb], n_results=min(depth * 3, mcol.count()),
                            include=["metadatas", "documents", "distances"])
            seen = set()
            for meta, doc, dist in zip(mr["metadatas"][0], mr["documents"][0], mr["distances"][0]):
                if meta["doc_id"] in seen:
                    continue
                seen.add(meta["doc_id"])
                merged.append((dist, f"mem::{meta['doc_id']}", doc))
        merged.sort(key=lambda t: t[0])
        return [(key, doc) for _, key, doc in merged[:depth]]

    def segments(query: str) -> list[tuple[str, str]]:
        scol = store._segments_collection()
        if not scol.count():
            return []
        emb = store._embed_query(query)
        sr = scol.query(query_embeddings=[emb], n_results=min(depth, scol.count()),
                        include=["documents"])
        return [(f"seg::{i}", d) for i, d in zip(sr["ids"][0], sr["documents"][0])]

    return {"videos": unified, "memories": unified, "segments": segments}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="first N queries (smoke test)")
    ap.add_argument("--depth", type=int, default=30)
    ap.add_argument("--out", default="experiments/rerank_bench_results.json")
    args = ap.parse_args()

    from ytk import ops, retrieval_gate

    queries = retrieval_gate.load_queries(retrieval_gate.QUERIES_PATH)
    if args.limit:
        queries = queries[: args.limit]

    ops.start_run("rerank-bench", f"{len(queries)} queries, depth {args.depth}")
    ops.step("rerank", "running", f"max_length {MAX_LENGTH}, batch {BATCH}")
    resolve = retrieval_gate._live_resolver()
    searchers = retrieve_with_docs(args.depth)
    reranker = Reranker()

    t_start = time.perf_counter()
    rows: list[dict] = []
    for n, q in enumerate(queries, 1):
        gold = resolve(q["gold_id"])
        if gold is None:
            continue
        pairs = searchers[q["bucket"]](q["query"])
        keys = [k for k, _ in pairs]
        before = keys.index(gold) if gold in keys else None

        t0 = time.perf_counter()
        scores = reranker.score(q["query"], [d for _, d in pairs])
        latency = time.perf_counter() - t0

        order = sorted(range(len(keys)), key=lambda i: scores[i], reverse=True)
        after = order.index(before) if before is not None else None
        row = {
            "query": q["query"], "bucket": q["bucket"], "gold_id": q["gold_id"],
            "rank_before": before, "rank_after": after,
            "latency_s": round(latency, 3),
        }
        rows.append(row)
        # stream rows so a killed run keeps its partial data
        with Path(args.out).with_suffix(".partial.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        if n % 10 == 0 or n == len(queries):
            print(f"  {n}/{len(queries)} reranked", flush=True)
            ops.progress(n, len(queries),
                         rate=n / (time.perf_counter() - t_start), label="rerank")

    def hits(rs, field, k):
        return sum(1 for r in rs if r[field] is not None and r[field] < k) / max(len(rs), 1)

    summary = {"n": len(rows), "depth": args.depth, "model": RERANK_MODEL,
               "overall": {}, "per_bucket": {}, "latency_s": {}}
    for field, tag in (("rank_before", "before"), ("rank_after", "after")):
        summary["overall"][tag] = {f"hit@{k}": round(hits(rows, field, k), 4) for k in (1, 5, 10)}
    for b in sorted({r["bucket"] for r in rows}):
        rs = [r for r in rows if r["bucket"] == b]
        summary["per_bucket"][b] = {
            "n": len(rs),
            "before": {f"hit@{k}": round(hits(rs, "rank_before", k), 4) for k in (1, 5, 10)},
            "after": {f"hit@{k}": round(hits(rs, "rank_after", k), 4) for k in (1, 5, 10)},
        }
    lats = sorted(r["latency_s"] for r in rows)
    summary["latency_s"] = {
        "mean": round(sum(lats) / len(lats), 3),
        "p50": round(lats[len(lats) // 2], 3),
        "p95": round(lats[int(len(lats) * 0.95)], 3),
    }
    promoted = [r for r in rows if r["rank_before"] is not None and r["rank_before"] >= 5
                and r["rank_after"] is not None and r["rank_after"] < 5]
    demoted = [r for r in rows if r["rank_before"] is not None and r["rank_before"] < 5
               and (r["rank_after"] is None or r["rank_after"] >= 5)]
    summary["promoted_into_top5"] = len(promoted)
    summary["demoted_out_of_top5"] = len(demoted)
    summary["demoted_queries"] = [
        {"query": r["query"], "before": r["rank_before"], "after": r["rank_after"]}
        for r in demoted
    ]

    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))
    after5 = summary["overall"]["after"]["hit@5"]
    before5 = summary["overall"]["before"]["hit@5"]
    ops.step("rerank", "done",
             f"hit@5 {before5} -> {after5}, p50 {summary['latency_s']['p50']}s",
             notify=True)


if __name__ == "__main__":
    main()
