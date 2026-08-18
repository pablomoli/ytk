"""Rung 7 of #183: the GEN gate — measure the Qwen->CLIP translator.

Pre-registered in docs/assets/47-gen-gate/README.md (committed before this
ran): ridge Qwen(1024) -> CLIP ViT-L/14 text(768), 80/20 split at seed 47,
gate = mean top-10 neighbor agreement in CLIP space on held-out notes,
PASS >= 0.40, shuffled-pairs control must sit > 0.10 below the real score.

    uv run --with torch --with open_clip_torch python \
        experiments/sae_qwen/gen_translator.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SEED = 47
RIDGE = 1.0
K = 10


def embed_clip(texts: list[str]) -> np.ndarray:
    import open_clip
    import torch

    model, _, _ = open_clip.create_model_and_transforms("ViT-L-14", pretrained="openai")
    tokenizer = open_clip.get_tokenizer("ViT-L-14")
    model.eval()
    outs = []
    with torch.no_grad():
        for i in range(0, len(texts), 256):
            toks = tokenizer(texts[i : i + 256])  # truncates at 77 tokens, disclosed
            e = model.encode_text(toks)
            outs.append(e.float().numpy())
            print(f"  clip {i + len(toks)}/{len(texts)}", flush=True)
    E = np.concatenate(outs)
    return E / np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-9)


def main() -> None:
    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    doc_idx = [i for i, r in enumerate(rows) if r["kind"] != "segment" and r["text"].strip()]
    X = np.load(DATA / "vectors.npz")["X"].astype(np.float32)[doc_idx]
    texts = [rows[i]["text"] for i in doc_idx]

    cache = DATA / "clip_text.npz"
    if cache.exists():
        C = np.load(cache)["C"]
    else:
        C = embed_clip(texts)
        np.savez_compressed(cache, C=C)
    assert len(C) == len(X)

    rng = np.random.default_rng(SEED)
    n = len(X)
    perm = rng.permutation(n)
    n_tr = int(n * 0.8)
    tr, va = perm[:n_tr], perm[n_tr:]

    def fit(Xa: np.ndarray, Ca: np.ndarray) -> np.ndarray:
        # ridge: W = (X^T X + lam I)^-1 X^T C
        d = Xa.shape[1]
        return np.linalg.solve(Xa.T @ Xa + RIDGE * np.eye(d, dtype=np.float64), Xa.T @ Ca)

    def agreement(W: np.ndarray) -> np.ndarray:
        P = X[va] @ W
        P = P / np.maximum(np.linalg.norm(P, axis=1, keepdims=True), 1e-9)
        agr = np.zeros(len(va))
        for j, vi in enumerate(va):
            native = C @ C[vi]
            trans = C @ P[j]
            native[vi] = -np.inf
            trans[vi] = -np.inf
            a = set(np.argsort(-native)[:K].tolist())
            b = set(np.argsort(-trans)[:K].tolist())
            agr[j] = len(a & b) / K
        return agr

    W = fit(X[tr].astype(np.float64), C[tr].astype(np.float64))
    agr = agreement(W)

    sh = rng.permutation(n_tr)
    W0 = fit(X[tr].astype(np.float64), C[tr][sh].astype(np.float64))
    agr0 = agreement(W0)

    mean, ctrl = float(agr.mean()), float(agr0.mean())
    result = {
        "registered": "mean agreement@10 >= 0.40; control must sit > 0.10 below",
        "n_pairs": n,
        "n_heldout": len(va),
        "mean_agreement": round(mean, 4),
        "median_agreement": round(float(np.median(agr)), 4),
        "p10_agreement": round(float(np.percentile(agr, 10)), 4),
        "control_mean": round(ctrl, 4),
        "gate": "PASS" if (mean >= 0.40 and mean - ctrl > 0.10) else "FAIL",
        "clip_model": "open_clip ViT-L-14 openai; text tower, 77-token truncation",
        "ridge_lambda": RIDGE,
        "seed": SEED,
    }
    np.savez_compressed(DATA / "gen_translator.npz", W=W.astype(np.float32), agr=agr, agr0=agr0)
    (HERE / "gen_translator.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
