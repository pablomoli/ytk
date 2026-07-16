"""Gate 3 + embedding production: embed corpus.jsonl with one model.

Mirrors production faithfully per model class:
  - 512-token-window models (gte-small, bge-small) embed each doc as PARTS via
    ytk.store._split_doc with the first-line context prefix — exactly what the
    store does — and the head part is the representative vector.
  - long-context models (qwen3-0.6b) embed the whole doc as one vector; a
    "-parts" variant isolates chunking effects from the model change.

Outputs {out}/{key}.npz: reps (docs x dim), parts (parts x dim),
part_doc (part -> doc index), plus a timing/memory sidecar {key}.bench.json.

    uv run python experiments/encoder_harness/embed.py --model gte-small
    uv run python experiments/encoder_harness/embed.py --model qwen3-0.6b --dims 384
"""

import argparse
import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

MODELS = {
    "gte-small": {
        "hf": "thenlper/gte-small", "window": 512, "query_prefix": "",
    },
    "bge-small": {
        "hf": "BAAI/bge-small-en-v1.5", "window": 512,
        "query_prefix": "Represent this sentence for searching relevant passages: ",
    },
    "qwen3-0.6b": {
        "hf": "Qwen/Qwen3-Embedding-0.6B", "window": 32768,
        "query_prefix": "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: ",
    },
}


def doc_parts(text: str) -> list[str]:
    from ytk.store import _split_doc

    chunks = _split_doc(text)
    context = next(
        (line.strip().lstrip("# ") for line in text.splitlines() if line.strip()), ""
    )[:120]
    return [chunks[0]] + [f"{context}\n\n{c}" for c in chunks[1:]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=sorted(MODELS))
    ap.add_argument("--data", default="experiments/encoder_harness/data")
    ap.add_argument("--dims", type=int, default=0, help="MRL-truncate to N dims (0 = native)")
    ap.add_argument("--force-parts", action="store_true",
                    help="use the parts strategy even on long-context models")
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()

    import numpy as np
    from sentence_transformers import SentenceTransformer

    cfg = MODELS[args.model]
    data = Path(args.data)
    # newline-only iteration: splitlines() would also split on U+2028/U+2029
    with (data / "corpus.jsonl").open(encoding="utf-8") as f:
        corpus = [json.loads(l) for l in f if l.strip()]

    use_parts = cfg["window"] <= 512 or args.force_parts
    texts: list[str] = []
    part_doc: list[int] = []
    rep_rows: list[int] = []
    for di, row in enumerate(corpus):
        chunks = doc_parts(row["text"]) if use_parts else [row["text"]]
        rep_rows.append(len(texts))
        for c in chunks:
            texts.append(c)
            part_doc.append(di)

    t0 = time.perf_counter()
    model = SentenceTransformer(cfg["hf"])
    t_load = time.perf_counter() - t0

    t0 = time.perf_counter()
    embs = model.encode(
        texts, batch_size=args.batch, normalize_embeddings=True,
        show_progress_bar=False,
    )
    t_encode = time.perf_counter() - t0

    embs = np.asarray(embs, dtype=np.float32)
    if args.dims and args.dims < embs.shape[1]:
        embs = embs[:, : args.dims]
        embs /= np.linalg.norm(embs, axis=1, keepdims=True)

    key = args.model + (f"-{args.dims}d" if args.dims else "") + ("-parts" if args.force_parts else "")
    reps = embs[rep_rows]
    np.savez_compressed(
        data / f"{key}.npz",
        reps=reps, parts=embs,
        part_doc=np.asarray(part_doc, dtype=np.int32),
        ids=np.asarray([r["id"] for r in corpus]),
        buckets=np.asarray([r["bucket"] for r in corpus]),
    )

    bench = {
        "key": key, "hf": cfg["hf"], "dims": int(embs.shape[1]),
        "docs": len(corpus), "vectors": len(texts), "parts_strategy": use_parts,
        "load_s": round(t_load, 2), "encode_s": round(t_encode, 2),
        "vectors_per_s": round(len(texts) / t_encode, 1),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6),
        "device": str(model.device),
    }
    (data / f"{key}.bench.json").write_text(json.dumps(bench, indent=2))
    print(json.dumps(bench))


if __name__ == "__main__":
    main()
