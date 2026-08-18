"""Rung 0 of #183: inventory the atlas's inputs, with numbers.

Read-only everywhere. Answers, into rung0.json:
  - OOD fraction of the live store vs the Aug-8 training cache (per kind)
  - the protagonist note's loudest latent (raw, and excluding the native cone)
  - the native SAE's always-on latents (freq >= 0.5 over cached vectors)
  - thumbnail coverage per map group, from the frozen ~/.ytk/map.json
  - segment-store coverage: video notes with at least one segment

    YTK_VISUAL_INDEX=off uv run --with torch python experiments/sae_qwen/rung0_inventory.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
DATA = HERE / "data"

PROTAGONIST_VIDEO = "UZDiGooFs54"  # The moment we stopped understanding AI [AlexNet]
CONE_FREQ = 0.5  # a latent firing on half the corpus shapes cells, not content


def live_ids() -> dict[str, set[str]]:
    from ytk import store

    out: dict[str, set[str]] = {}
    out["video"] = set(store._videos_collection().get(include=[])["ids"])
    out["segment"] = set(store._segments_collection().get(include=[])["ids"])
    out["memory"] = set(store._memories_collection().get(include=[])["ids"])
    return out


def protagonist_latents(features: dict) -> dict:
    import torch
    import train_sae as T

    from ytk import store

    got = store._videos_collection().get(
        where={"video_id": PROTAGONIST_VIDEO}, include=["embeddings", "metadatas"]
    )
    if not got["ids"]:
        return {"error": f"no video rows for {PROTAGONIST_VIDEO}"}
    X = np.asarray(got["embeddings"], dtype=np.float32)
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)

    blob = torch.load(HERE / "checkpoints" / features["checkpoint"], map_location="cpu")
    c = blob["cfg"]
    m = T.TopKSAE(X.shape[1], c["d_sae"], c["k"])
    m.load_state_dict(blob["state"])
    m.eval()
    with torch.no_grad():
        pre = m.pre_acts(torch.as_tensor(X))
        v, ix = pre.topk(c["k"], dim=-1)

    named = {f["feature"]: f for f in features["features"]}
    rows = []
    for rid, vals, idxs in zip(got["ids"], v.numpy(), ix.numpy()):
        rows.append(
            {
                "chroma_id": rid,
                "top": [
                    {
                        "latent": int(f),
                        "act": round(float(a), 4),
                        "name": (named.get(int(f)) or {}).get("name"),
                        "freq": (named.get(int(f)) or {}).get("freq"),
                    }
                    for a, f in zip(vals, idxs)
                    if a > 0
                ][:12],
            }
        )
    return {"video_id": PROTAGONIST_VIDEO, "rows": rows}


def native_cone(features: dict) -> dict:
    z = np.load(DATA / features["acts"])
    idx, val, d_sae = z["idx"], z["val"], int(z["d_sae"])
    freq = np.bincount(idx.ravel()[val.ravel() > 0], minlength=d_sae) / len(idx)
    cone = np.where(freq >= CONE_FREQ)[0]
    return {
        "threshold": CONE_FREQ,
        "n_vectors": len(idx),
        "latents": [{"latent": int(f), "freq": round(float(freq[f]), 4)} for f in cone],
        "freq_top10": [round(float(f), 4) for f in np.sort(freq)[::-1][:10]],
    }


def map_coverage() -> dict:
    m = json.loads((Path.home() / ".ytk" / "map.json").read_text())
    pts = m["points"]
    per: dict[int, list[int]] = {}
    for p in pts:
        g = per.setdefault(int(p.get("g", -1)), [0, 0])
        g[0] += 1
        g[1] += 1 if p.get("img") else 0
    return {
        "n_points": len(pts),
        "img_total": sum(1 for p in pts if p.get("img")),
        "groups": {
            str(g): {"n": n, "img": i, "img_frac": round(i / n, 3)}
            for g, (n, i) in sorted(per.items())
        },
    }


def main() -> None:
    features = json.loads((HERE / "features.json").read_text())
    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    train = {k: set() for k in ("video", "segment", "memory")}
    for r in rows:
        train[r["kind"]].add(r["id"])

    live = live_ids()
    ood = {}
    for kind in train:
        new = live[kind] - train[kind]
        gone = train[kind] - live[kind]
        ood[kind] = {
            "live": len(live[kind]),
            "trained_on": len(train[kind]),
            "new_since_training": len(new),
            "removed_since_training": len(gone),
            "ood_frac_of_live": round(len(new) / max(len(live[kind]), 1), 4),
        }
    all_live = sum(len(v) for v in live.values())
    all_new = sum(v["new_since_training"] for v in ood.values())
    ood["overall"] = {
        "live": all_live,
        "new_since_training": all_new,
        "ood_frac_of_live": round(all_new / all_live, 4),
    }

    from ytk import store

    seg_meta = store._segments_collection().get(include=["metadatas"])
    seg_vids = {str((m or {}).get("video_id", "")) for m in seg_meta["metadatas"]}
    vid_meta = store._videos_collection().get(include=["metadatas"])
    note_vids = {str((m or {}).get("video_id", "")) for m in vid_meta["metadatas"]}
    segments = {
        "video_notes": len(note_vids),
        "with_segments": len(note_vids & seg_vids),
        "coverage": round(len(note_vids & seg_vids) / max(len(note_vids), 1), 4),
    }

    out = {
        "checkpoint": features["checkpoint"],
        "ood": ood,
        "train_kinds": dict(Counter(r["kind"] for r in rows)),
        "native_cone": native_cone(features),
        "protagonist": protagonist_latents(features),
        "map_thumbnails": map_coverage(),
        "segment_coverage": segments,
    }
    (HERE / "rung0.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
