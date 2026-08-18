"""Rung 4 of #183: segment strips — the SAE code as a timeline per video.

Two questions gate the strips before any renders:
  1. Aggregation validity: does the mean of a video's per-segment codes point
     at the video's own document code? Measured as cosine, against the
     mismatched-video null (every doc paired with another video's segments).
  2. Temporal structure: do latent activations run in contiguous stretches
     along the timeline, or is a strip just noise with a palette? Measured as
     lag-1 autocorrelation of each video's top-8 latent series, against the
     order-shuffle null (which preserves values, destroys order).

Also encodes the protagonist's segments live from Chroma (its video
postdates the acts cache) and ships the strip matrix for the figure.

    YTK_VISUAL_INDEX=off uv run --with torch python \
        experiments/sae_qwen/segment_strips.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
DATA = HERE / "data"

D_SAE = 2048
PROT_VIDEO = "UZDiGooFs54"
N_STRIP_LATENTS = 8
N_SHUFFLE = 100


def codes_dense(idx: np.ndarray, val: np.ndarray, rows_sel: list[int]) -> np.ndarray:
    Z = np.zeros((len(rows_sel), D_SAE), np.float32)
    for r, ri in enumerate(rows_sel):
        v = val[ri]
        Z[r, idx[ri][v > 0]] = v[v > 0]
    return Z


def lag1(series: np.ndarray) -> float | None:
    a, b = series[:-1], series[1:]
    if a.std() < 1e-9 or b.std() < 1e-9:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def video_autocorr(S: np.ndarray, rng: np.random.Generator | None = None) -> float | None:
    """Mean lag-1 autocorrelation over the video's top-8 latents by mass."""
    if rng is not None:
        S = S[rng.permutation(len(S))]
    top = np.argsort(-S.mean(0))[:N_STRIP_LATENTS]
    vals = [lag1(S[:, f]) for f in top]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else None


def main() -> None:
    import torch
    import train_sae as T

    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    z = np.load(DATA / "acts_final_d2048_k32_s0.npz")
    idx, val = z["idx"], z["val"]

    doc_row = {}
    seg_rows: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for i, r in enumerate(rows):
        if r["kind"] == "video":
            doc_row[r["id"]] = i
        elif r["kind"] == "segment":
            vid, n = r["id"].rsplit("_", 1)
            if n.isdigit():
                seg_rows[vid].append((int(n), i))

    vids = sorted(v for v in doc_row if len(seg_rows.get(v, [])) >= 8)
    print(f"videos with doc code + >=8 ordered segments: {len(vids)}")

    # --- gate 1: aggregation validity
    doc_codes, seg_means = {}, {}
    for v in vids:
        doc_codes[v] = codes_dense(idx, val, [doc_row[v]])[0]
        order = [i for _, i in sorted(seg_rows[v])]
        seg_means[v] = codes_dense(idx, val, order).mean(0)

    def cos(a, b):
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

    matched = np.array([cos(doc_codes[v], seg_means[v]) for v in vids])
    rng = np.random.default_rng(45)
    others = rng.permutation(len(vids))
    others = np.where(others == np.arange(len(vids)), (others + 1) % len(vids), others)
    mismatched = np.array(
        [cos(doc_codes[vids[i]], seg_means[vids[j]]) for i, j in enumerate(others)]
    )

    # --- gate 2: temporal structure vs order-shuffle null
    obs_ac, null_ac = [], []
    for v in vids:
        order = [i for _, i in sorted(seg_rows[v])]
        S = codes_dense(idx, val, order)
        a = video_autocorr(S)
        if a is None:
            continue
        obs_ac.append(a)
        sh = [video_autocorr(S, rng) for _ in range(N_SHUFFLE)]
        null_ac.append(float(np.mean([x for x in sh if x is not None])))
    obs_ac, null_ac = np.array(obs_ac), np.array(null_ac)

    # --- protagonist strip, encoded live (video postdates the cache)
    from ytk import store

    got = store._segments_collection().get(
        where={"video_id": PROT_VIDEO}, include=["embeddings", "metadatas", "documents"]
    )
    order = np.argsort(
        [
            int(str(i).rsplit("_", 1)[-1]) if str(i).rsplit("_", 1)[-1].isdigit() else 0
            for i in got["ids"]
        ]
    )
    X = np.asarray(got["embeddings"], np.float32)[order]
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)
    m = T.TopKSAE(1024, D_SAE, 32)
    m.load_state_dict(
        torch.load(HERE / "checkpoints" / "final_d2048_k32_s0.pt", map_location="cpu")["state"]
    )
    m.eval()
    with torch.no_grad():
        pre = m.pre_acts(torch.as_tensor(X))
        zc, _ = m.topk(pre, 32)
    S_prot = zc.numpy()
    names = {
        f["feature"]: f.get("name")
        for f in json.loads((HERE / "features.json").read_text())["features"]
    }
    top = [int(f) for f in np.argsort(-S_prot.mean(0))[:N_STRIP_LATENTS]]
    prot_ac = video_autocorr(S_prot)
    prot_null = float(np.mean([video_autocorr(S_prot, rng) for _ in range(N_SHUFFLE)]))

    out = {
        "n_videos": len(vids),
        "gate_aggregation": {
            "matched_median": round(float(np.median(matched)), 4),
            "matched_p10": round(float(np.percentile(matched, 10)), 4),
            "mismatched_median": round(float(np.median(mismatched)), 4),
            "mismatched_max": round(float(mismatched.max()), 4),
            "matched_below_mismatched_max": int((matched <= mismatched.max()).sum()),
        },
        "gate_temporal": {
            "obs_median": round(float(np.median(obs_ac)), 4),
            "null_median": round(float(np.median(null_ac)), 4),
            "videos_above_own_null": int((obs_ac > null_ac).sum()),
            "n": len(obs_ac),
        },
        "protagonist": {
            "video_id": PROT_VIDEO,
            "n_segments": len(S_prot),
            "encoded": "live from Chroma (video postdates the acts cache)",
            "top_latents": [{"latent": f, "name": names.get(f)} for f in top],
            "autocorr": round(prot_ac, 4) if prot_ac is not None else None,
            "autocorr_shuffle_null": round(prot_null, 4),
        },
    }
    np.savez_compressed(
        DATA / "strips.npz",
        prot_strip=S_prot[:, top],
        prot_top=np.array(top),
        matched=matched,
        mismatched=mismatched,
        obs_ac=obs_ac,
        null_ac=null_ac,
    )
    (HERE / "strips.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
