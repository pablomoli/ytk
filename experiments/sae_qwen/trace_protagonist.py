"""Rung 5 of #183: the protagonist trace — one note through the whole system.

Gathers everything the A1 figure series needs into trace.json: the note's
embedded text head, its Qwen vector, its SAE code, its top named latents,
its neighbors under both lenses (Qwen cosine vs SAE-code cosine, section
37's pair), and the calibrated-honesty numbers (how much of its own code
mass the named head explains).

    YTK_VISUAL_INDEX=off uv run --with torch python \
        experiments/sae_qwen/trace_protagonist.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from paths import CKPT, DATA

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

PROT_VIDEO = "UZDiGooFs54"
PROT = 1597
N_NEIGH = 5


def main() -> None:
    import torch
    import train_sae as T

    from ytk import store

    got = store._videos_collection().get(
        where={"video_id": PROT_VIDEO}, include=["embeddings", "documents", "metadatas"]
    )
    v = np.asarray(got["embeddings"][0], np.float32)
    v /= np.linalg.norm(v)
    text = (got["documents"][0] or "")[:600]

    m = T.TopKSAE(1024, 2048, 32)
    m.load_state_dict(torch.load(CKPT / "final_d2048_k32_s0.pt", map_location="cpu")["state"])
    m.eval()
    with torch.no_grad():
        pre = m.pre_acts(torch.as_tensor(v[None]))
        zc, _ = m.topk(pre, 32)
    code = zc[0].numpy()

    names = {
        f["feature"]: f.get("name")
        for f in json.loads((HERE / "features.json").read_text())["features"]
    }
    head = {
        f["feature"]
        for f in sorted(
            json.loads((HERE / "features.json").read_text())["features"],
            key=lambda t: -t["freq"],
        )[:100]
    }
    active = np.where(code > 0)[0]
    named_active = [int(f) for f in active if names.get(int(f))]
    head_active = [int(f) for f in active if int(f) in head]
    mass = float(code.sum())

    # neighbors under both lenses, over doc-level cached rows
    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    doc_idx = [i for i, r in enumerate(rows) if r["kind"] != "segment"]
    X = np.load(DATA / "vectors.npz")["X"]
    Xd = X[doc_idx]
    qwen_sims = Xd @ v

    z = np.load(DATA / "acts_final_d2048_k32_s0.npz")
    idx, val = z["idx"], z["val"]
    code_n = code / np.linalg.norm(code)
    sae_sims = np.zeros(len(doc_idx))
    for k, ri in enumerate(doc_idx):
        vv = val[ri]
        live = vv > 0
        c = np.zeros(2048, np.float32)
        c[idx[ri][live]] = vv[live]
        n = np.linalg.norm(c)
        if n > 0:
            sae_sims[k] = float(c @ code_n / n)

    def top(sims):
        out = []
        for k in np.argsort(-sims)[:N_NEIGH]:
            r = rows[doc_idx[k]]
            out.append(
                {
                    "title": r["title"] or r["text"][:60],
                    "kind": r["kind"],
                    "source": r["source"],
                    "sim": round(float(sims[k]), 4),
                }
            )
        return out

    atlas = json.loads((HERE / "atlas.json").read_text())
    out = {
        "video_id": PROT_VIDEO,
        "title": "The moment we stopped understanding AI [AlexNet]",
        "text_head": text,
        "vector_sample": [round(float(x), 4) for x in v[:6]],
        "vector_norm_dims": 1024,
        "code_active": len(active),
        "code_mass": round(mass, 4),
        "named_mass_frac": round(float(sum(code[f] for f in named_active) / mass), 4),
        "head_mass_frac": round(float(sum(code[f] for f in head_active) / mass), 4),
        "top_latents": [
            {"latent": int(f), "act": round(float(code[f]), 4), "name": names.get(int(f))}
            for f in active[np.argsort(-code[active])][:10]
        ],
        "neighbors_qwen": top(qwen_sims),
        "neighbors_sae": top(sae_sims),
        "neighbor_overlap": len(
            {n["title"] for n in top(qwen_sims)} & {n["title"] for n in top(sae_sims)}
        ),
        "atlas_cell": atlas["protagonist"],
        "code": {int(f): round(float(code[f]), 4) for f in active},
        "vector": [round(float(x), 5) for x in v],
    }
    (HERE / "trace.json").write_text(json.dumps(out, indent=1))
    print(
        f"active {out['code_active']}, named mass {out['named_mass_frac']:.0%}, "
        f"head mass {out['head_mass_frac']:.0%}, neighbor overlap "
        f"{out['neighbor_overlap']}/{N_NEIGH}"
    )
    print("qwen:", [n["title"][:40] for n in out["neighbors_qwen"]])
    print("sae: ", [n["title"][:40] for n in out["neighbors_sae"]])


if __name__ == "__main__":
    main()
