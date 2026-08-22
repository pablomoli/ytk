"""Export what the hub's /atlas page needs, torch-free (#183 rung 6).

The hub must not grow a torch dependency for one page, so the SAE's weights
leave their checkpoint here: ~/.ytk/atlas_sae.npz carries the encoder and
decoder as plain arrays, the per-latent corpus max activation (the knob's
calibrated unit, section 35), and the doc-level retrieval bed (unit vectors +
row metadata) the knob ranks against. Annotation layer only — production
search reads none of this.

    uv run --with torch python experiments/sae_qwen/export_hub_assets.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from paths import CKPT, DATA

HERE = Path(__file__).resolve().parent
OUT = Path.home() / ".ytk"


def main() -> None:
    blob = torch.load(CKPT / "final_d2048_k32_s0.pt", map_location="cpu", weights_only=False)
    st = blob["state"]

    z = np.load(DATA / "acts_final_d2048_k32_s0.npz")
    idx, val = z["idx"], z["val"]
    maxa = np.zeros(2048, np.float32)
    flat_i, flat_v = idx.ravel(), val.ravel()
    live = flat_v > 0
    np.maximum.at(maxa, flat_i[live], flat_v[live])

    rows = [json.loads(x) for x in (DATA / "rows.jsonl").read_text().splitlines()]
    doc_idx = [i for i, r in enumerate(rows) if r["kind"] != "segment"]
    X = np.load(DATA / "vectors.npz")["X"].astype(np.float32)
    Xd = X[doc_idx]
    Xd /= np.maximum(np.linalg.norm(Xd, axis=1, keepdims=True), 1e-9)
    meta = [
        {
            "title": rows[i]["title"] or rows[i]["text"][:60],
            "note_key": rows[i]["note_key"],
            "kind": rows[i]["kind"],
            "source": rows[i]["source"],
        }
        for i in doc_idx
    ]

    # the share transform's temperature: std of background doc-pair cosines
    # (section 50's measured null) — carried as data so it is never re-typed
    rng = np.random.default_rng(50)
    pairs = rng.choice(len(Xd), (5000, 2))
    pairs = pairs[pairs[:, 0] != pairs[:, 1]]
    bg_std = float(np.einsum("ij,ij->i", Xd[pairs[:, 0]], Xd[pairs[:, 1]]).std())

    np.savez_compressed(
        OUT / "atlas_sae.npz",
        W_enc=st["enc.weight"].numpy().astype(np.float32),
        b_enc=st["enc.bias"].numpy().astype(np.float32),
        b_pre=st["b_pre"].numpy().astype(np.float32),
        W_dec=st["W_dec"].numpy().astype(np.float32),
        maxa=maxa,
        docs=Xd,
        k=np.int64(32),
        bg_std=np.float32(bg_std),
    )
    (OUT / "atlas_docs.json").write_text(json.dumps(meta))
    print(
        f"wrote {OUT / 'atlas_sae.npz'} ({(OUT / 'atlas_sae.npz').stat().st_size // 1024}KB), "
        f"{len(meta)} doc rows"
    )


if __name__ == "__main__":
    main()
