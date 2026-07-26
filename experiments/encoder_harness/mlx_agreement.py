"""Phase 0.3 pre-flight: MLX runtime spike for Qwen3-Embedding-0.6B.

Acceptance (spec Phase 0.3): per-vector cosine agreement with the PyTorch
reference (data/qwen3-0.6b.npz, fp16 + max-seq 3072) > 0.999 on ~100 docs.
Adoption threshold: >= 3x the PyTorch 2.0 vectors/s to become the serving path.

Agreement runs at batch=1 (no padding in play); batch=8 is then compared to
batch=1 to validate padded last-token pooling separately. Also times a warm
single prefixed query for the interactive path.

    uv run --with mlx-embeddings python experiments/encoder_harness/mlx_agreement.py
"""

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from embed import MODELS

LOG = Path("/tmp/ytk-encoder-eval.log")
N_DOCS = 100
MAX_SEQ = 3072


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] mlx_agreement: {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def embed_batch(model, tokenizer, texts: list[str]):
    import mlx.core as mx
    import numpy as np

    enc = tokenizer(texts, return_tensors="mlx", padding=True, truncation=True, max_length=MAX_SEQ)
    out = model(enc["input_ids"], attention_mask=enc.get("attention_mask"))
    embs = np.asarray(out.text_embeds.astype(mx.float32))
    return embs / np.linalg.norm(embs, axis=1, keepdims=True)


def main() -> None:
    import numpy as np
    from mlx_embeddings.utils import load

    cfg = MODELS["qwen3-0.6b"]
    data = Path("experiments/encoder_harness/data")
    ref = np.load(data / "qwen3-0.6b.npz", allow_pickle=True)
    with (data / "corpus.jsonl").open(encoding="utf-8") as f:
        texts = [json.loads(l)["text"] for l in f if l.strip()][:N_DOCS]
    ref_vecs = ref["reps"][:N_DOCS].astype(np.float32)
    ref_vecs /= np.linalg.norm(ref_vecs, axis=1, keepdims=True)

    log(f"loading {cfg['hf']} via mlx-embeddings")
    t0 = time.perf_counter()
    model, tokenizer = load(cfg["hf"])
    log(f"loaded in {time.perf_counter() - t0:.2f} s")

    t0 = time.perf_counter()
    b1 = np.vstack([embed_batch(model, tokenizer, [t]) for t in texts])
    t_b1 = time.perf_counter() - t0
    cos = (b1 * ref_vecs).sum(axis=1)
    log(
        f"batch=1: {N_DOCS / t_b1:.1f} vec/s | cosine vs PyTorch: "
        f"min {cos.min():.5f}, mean {cos.mean():.5f}, "
        f">{0.999} for {(cos > 0.999).mean():.0%}"
    )

    t0 = time.perf_counter()
    b8 = np.vstack([embed_batch(model, tokenizer, texts[i : i + 8]) for i in range(0, N_DOCS, 8)])
    t_b8 = time.perf_counter() - t0
    cos_b8_b1 = (b8 * b1).sum(axis=1)
    log(
        f"batch=8: {N_DOCS / t_b8:.1f} vec/s | cosine vs batch=1: "
        f"min {cos_b8_b1.min():.5f} (padding/pooling check)"
    )

    queries = [
        json.loads(l)["query"] for l in (data / "queries.jsonl").open(encoding="utf-8") if l.strip()
    ][:20]
    times = []
    for q in queries:
        t0 = time.perf_counter()
        embed_batch(model, tokenizer, [cfg["query_prefix"] + q])
        times.append((time.perf_counter() - t0) * 1000)
    q_med = statistics.median(times)
    log(f"warm prefixed query: median {q_med:.1f} ms (n={len(times)})")

    report = {
        "model": cfg["hf"],
        "runtime": "mlx-embeddings",
        "n_docs": N_DOCS,
        "max_seq": MAX_SEQ,
        "cosine_vs_pytorch": {
            "min": round(float(cos.min()), 5),
            "mean": round(float(cos.mean()), 5),
            "frac_above_0.999": round(float((cos > 0.999).mean()), 3),
        },
        "batch8_vs_batch1_min_cosine": round(float(cos_b8_b1.min()), 5),
        "vectors_per_s_batch1": round(N_DOCS / t_b1, 1),
        "vectors_per_s_batch8": round(N_DOCS / t_b8, 1),
        "query_median_ms": round(q_med, 1),
        "pytorch_reference_vectors_per_s": 2.0,
        "agreement_pass": bool(cos.min() > 0.999),
        "speed_3x_pass": bool(N_DOCS / t_b8 >= 6.0),
    }
    out = data / "mlx_agreement.json"
    out.write_text(json.dumps(report, indent=2))
    log(
        f"agreement_pass={report['agreement_pass']} "
        f"speed_3x_pass={report['speed_3x_pass']} -> {out}"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
