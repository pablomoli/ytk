"""Phase 0.2 pre-flight: interactive latency bench for Qwen3-Embedding-0.6B.

Measures what the hub /search path will actually feel like:
  - cold start: model load + first single-query encode (hub loads lazily)
  - warm single-query encodes with the retrieval instruction prefix
  - warm single-query encodes without prefix (clustering consumers)
  - warm single-doc encode (median-length corpus doc, ingest path)

Queries are drawn from data/queries.jsonl so token lengths match the eval.
Target (spec Phase 0.2): warm prefixed query < 500 ms.

    uv run python experiments/encoder_harness/bench_latency.py --fp16 --max-seq 3072
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from embed import MODELS

LOG = Path("/tmp/ytk-encoder-eval.log")


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] bench_latency: {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def timed_encodes(model, texts: list[str], label: str) -> dict:
    times = []
    for t in texts:
        t0 = time.perf_counter()
        model.encode([t], normalize_embeddings=True, show_progress_bar=False)
        times.append((time.perf_counter() - t0) * 1000)
    stats = {
        "n": len(times),
        "median_ms": round(statistics.median(times), 1),
        "p95_ms": round(sorted(times)[int(0.95 * (len(times) - 1))], 1),
        "min_ms": round(min(times), 1),
        "max_ms": round(max(times), 1),
    }
    log(
        f"{label}: median {stats['median_ms']} ms, p95 {stats['p95_ms']} ms "
        f"(min {stats['min_ms']}, max {stats['max_ms']}, n={stats['n']})"
    )
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3-0.6b", choices=sorted(MODELS))
    ap.add_argument("--data", default="experiments/encoder_harness/data")
    ap.add_argument("--fp16", action="store_true")
    ap.add_argument("--max-seq", type=int, default=0)
    ap.add_argument("--n-queries", type=int, default=30)
    args = ap.parse_args()

    cfg = MODELS[args.model]
    data = Path(args.data)
    with (data / "queries.jsonl").open(encoding="utf-8") as f:
        queries = [json.loads(l)["query"] for l in f if l.strip()][: args.n_queries]
    with (data / "corpus.jsonl").open(encoding="utf-8") as f:
        docs = [json.loads(l)["text"] for l in f if l.strip()]
    median_doc = sorted(docs, key=len)[len(docs) // 2][:8000]

    log(f"loading {cfg['hf']} (fp16={args.fp16}, max_seq={args.max_seq or 'native'})")
    t0 = time.perf_counter()
    kwargs = {}
    if args.fp16:
        import torch

        kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(cfg["hf"], **kwargs)
    if args.max_seq:
        model.max_seq_length = args.max_seq
    t_load = time.perf_counter() - t0

    t0 = time.perf_counter()
    model.encode(
        [cfg["query_prefix"] + queries[0]], normalize_embeddings=True, show_progress_bar=False
    )
    t_first = time.perf_counter() - t0
    log(
        f"cold start: load {t_load:.2f} s + first encode {t_first * 1000:.0f} ms "
        f"= {t_load + t_first:.2f} s total (device {model.device})"
    )

    report = {
        "model": cfg["hf"],
        "fp16": args.fp16,
        "max_seq": args.max_seq,
        "device": str(model.device),
        "cold_load_s": round(t_load, 2),
        "cold_first_encode_ms": round(t_first * 1000),
        "warm_query_prefixed": timed_encodes(
            model, [cfg["query_prefix"] + q for q in queries], "warm query (prefixed)"
        ),
        "warm_query_plain": timed_encodes(model, queries, "warm query (plain)"),
        "warm_doc_median_len": timed_encodes(
            model, [median_doc] * 5, f"warm doc ({len(median_doc)} chars)"
        ),
        "target_ms": 500,
    }
    report["passes_target"] = report["warm_query_prefixed"]["p95_ms"] < report["target_ms"]
    out = data / "latency.bench.json"
    out.write_text(json.dumps(report, indent=2))
    log(f"PASS={report['passes_target']} -> {out}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
