"""Section 50: the canonical constellation layout and its registered gate.

Pre-registered in docs/assets/50-constellations/README.md (cd764c1, before
this ran). Layout = 2D PCA of unit decoder rows, sign-fixed, frozen.
Coherence = activation-weighted mean pairwise decoder cosine among a code's
active latents, ambient. G1 = >= 60% of 500 sampled notes beat their
frequency-matched null's p95. Also measures the background-pair null that
sets the share transform's temperature.

    YTK_VISUAL_INDEX=off uv run --with torch python \
        experiments/sae_qwen/constellations.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SEED = 50
N_NOTES = 500
N_NULL = 100
PROT_VIDEO = "UZDiGooFs54"


def decoder() -> np.ndarray:
    import torch

    blob = torch.load(
        HERE / "checkpoints" / "final_d2048_k32_s0.pt", map_location="cpu", weights_only=False
    )
    W = blob["state"]["W_dec"].numpy().astype(np.float32)
    return W / np.maximum(np.linalg.norm(W, axis=1, keepdims=True), 1e-9)


def pca_layout(W: np.ndarray) -> np.ndarray:
    C = W - W.mean(0)
    _, _, Vt = np.linalg.svd(C, full_matrices=False)
    xy = C @ Vt[:2].T
    # deterministic sign: the largest-|value| coordinate of each axis is positive
    for k in range(2):
        if xy[np.abs(xy[:, k]).argmax(), k] < 0:
            xy[:, k] = -xy[:, k]
    return xy.astype(np.float32)


def coherence(G: np.ndarray, lat: np.ndarray, w: np.ndarray) -> float:
    """Activation-weighted mean pairwise decoder cosine of a latent set."""
    sub = G[np.ix_(lat, lat)]
    ww = np.outer(w, w)
    np.fill_diagonal(ww, 0.0)
    return float((sub * ww).sum() / max(ww.sum(), 1e-12))


def main() -> None:
    W = decoder()
    G = W @ W.T
    xy = pca_layout(W)

    z = np.load(DATA / "acts_final_d2048_k32_s0.npz")
    idx, val = z["idx"], z["val"]
    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    doc_idx = [i for i, r in enumerate(rows) if r["kind"] != "segment"]

    fire = val > 0
    freq = np.bincount(idx[fire].ravel(), minlength=2048).astype(np.float64)
    p = freq / freq.sum()

    rng = np.random.default_rng(SEED)
    sample = rng.choice(len(doc_idx), N_NOTES, replace=False)
    obs, null_p95s, beats = [], [], 0
    for si in sample:
        ri = doc_idx[si]
        live = val[ri] > 0
        lat, w = idx[ri][live], val[ri][live]
        c = coherence(G, lat, w)
        nulls = [
            coherence(G, rng.choice(2048, len(lat), replace=False, p=p), w) for _ in range(N_NULL)
        ]
        p95 = float(np.percentile(nulls, 95))
        obs.append(c)
        null_p95s.append(p95)
        beats += c > p95
    obs = np.array(obs)
    null_p95s = np.array(null_p95s)
    frac = beats / len(sample)

    # background-pair null over doc vectors: the share transform's temperature
    X = np.load(DATA / "vectors.npz")["X"].astype(np.float32)[doc_idx]
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)
    pairs = rng.choice(len(X), (5000, 2))
    pairs = pairs[pairs[:, 0] != pairs[:, 1]]
    bg = np.einsum("ij,ij->i", X[pairs[:, 0]], X[pairs[:, 1]])

    # the protagonist's constellation, plus the sampled extremes for the gallery
    from ytk import store

    got = store._videos_collection().get(where={"video_id": PROT_VIDEO}, include=["embeddings"])
    v = np.asarray(got["embeddings"][0], np.float32)
    v /= np.linalg.norm(v)
    import torch

    blob = torch.load(
        HERE / "checkpoints" / "final_d2048_k32_s0.pt", map_location="cpu", weights_only=False
    )
    import sys

    sys.path.insert(0, str(HERE))
    import train_sae as T

    m = T.TopKSAE(1024, 2048, 32)
    m.load_state_dict(blob["state"])
    m.eval()
    with torch.no_grad():
        pre = m.pre_acts(torch.as_tensor(v[None]))
        zc, _ = m.topk(pre, 32)
    code_p = zc[0].numpy()
    live = code_p > 0
    prot = {
        "latents": [int(f) for f in np.where(live)[0]],
        "acts": [round(float(a), 4) for a in code_p[live]],
        "coherence": round(coherence(G, np.where(live)[0], code_p[live]), 4),
    }

    order = np.argsort(obs)
    ex = {}
    for name, si in (("tightest", order[-1]), ("loosest", order[0])):
        ri = doc_idx[sample[si]]
        lv = val[ri] > 0
        ex[name] = {
            "title": rows[ri]["title"] or rows[ri]["text"][:50],
            "coherence": round(float(obs[si]), 4),
            "latents": [int(f) for f in idx[ri][lv]],
            "acts": [round(float(a), 4) for a in val[ri][lv]],
        }

    result = {
        "registered": "G1: >= 60% of 500 sampled notes exceed their frequency-matched null p95",
        "n_notes": len(sample),
        "frac_beat_null_p95": round(float(frac), 4),
        "obs_median": round(float(np.median(obs)), 4),
        "null_p95_median": round(float(np.median(null_p95s)), 4),
        "gate": "PASS" if frac >= 0.60 else "FAIL",
        "background_pairs": {
            "mean": round(float(bg.mean()), 4),
            "std": round(float(bg.std()), 4),
            "n": len(bg),
            "role": "share-transform temperature T = this std",
        },
        "protagonist": prot,
        "extremes": ex,
        "seed": SEED,
    }
    np.savez_compressed(
        DATA / "constellations.npz",
        layout=xy,
        obs=obs,
        null_p95=null_p95s,
        bg=bg,
    )
    (HERE / "constellations.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: result[k] for k in list(result)[:7]}, indent=1))
    print(
        "protagonist coherence:",
        prot["coherence"],
        "| extremes:",
        ex["tightest"]["title"][:40],
        "/",
        ex["loosest"]["title"][:40],
    )


if __name__ == "__main__":
    main()
