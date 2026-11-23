"""SigLIP-2 over the taste test frames on a CUDA machine, keeping what the pooled vector throws away.

Per frame: the pooled vector, and at three depths of the vision tower the per-channel mean
and spread of the patch features and a Gram matrix of the patches after a fixed random
projection to 64 channels (channel correlations, with where things are discarded).
Standalone: no ytk import. Same checkpoint and revision as ytk/visual.py.

    python taste_embed_cuda.py <flat_dir> <order.json> <out.npz>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

MODEL_ID = "google/siglip2-so400m-patch16-384"
MODEL_REVISION = "dd658faac399427308559e2c3ac1e99cbe43845d"
DEPTHS, PROJ, BATCH = (9, 18, 27), 64, 32


def main() -> None:
    flat, order, out = (
        Path(sys.argv[1]),
        json.loads(Path(sys.argv[2]).read_text()),
        Path(sys.argv[3]),
    )
    model = (
        AutoModel.from_pretrained(MODEL_ID, revision=MODEL_REVISION, dtype=torch.float16)
        .to("cuda")
        .eval()
    )
    proc = AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    gen = torch.Generator(device="cpu").manual_seed(0)
    width = model.config.vision_config.hidden_size
    # One fixed projection for every frame and depth, so Gram matrices are comparable.
    proj = (torch.randn(width, PROJ, generator=gen) / PROJ**0.5).to("cuda")
    iu = torch.triu_indices(PROJ, PROJ)
    pooled, stats, grams = [], {d: [] for d in DEPTHS}, {d: [] for d in DEPTHS}
    # Hooks, not output_hidden_states: the layer's own output is the one thing every version returns.
    layers, grabbed = model.vision_model.encoder.layers, {}
    for d in DEPTHS:
        layers[min(d, len(layers)) - 1].register_forward_hook(
            lambda _m, _i, o, d=d: grabbed.__setitem__(d, o[0] if isinstance(o, tuple) else o)
        )
    for i in range(0, len(order), BATCH):
        ims = [Image.open(flat / o["name"]).convert("RGB") for o in order[i : i + BATCH]]
        px = proc(images=ims, return_tensors="pt")["pixel_values"].to("cuda").half()
        with torch.inference_mode():
            feat = model.get_image_features(pixel_values=px)
        feat = getattr(feat, "pooler_output", feat)
        pooled.append(torch.nn.functional.normalize(feat.float(), dim=-1).cpu().numpy())
        for d in DEPTHS:
            h = grabbed[d].float()
            stats[d].append(torch.cat([h.mean(1), h.std(1)], dim=1).cpu().numpy())
            z = h @ proj
            z = z - z.mean(1, keepdim=True)
            g = z.transpose(1, 2) @ z / z.shape[1]
            grams[d].append(g[:, iu[0], iu[1]].cpu().numpy())
        print(f"{min(i + BATCH, len(order))}/{len(order)}", flush=True)
    np.savez_compressed(
        out,
        pooled=np.concatenate(pooled).astype(np.float32),
        **{f"stats_{d}": np.concatenate(stats[d]).astype(np.float32) for d in DEPTHS},
        **{f"gram_{d}": np.concatenate(grams[d]).astype(np.float32) for d in DEPTHS},
    )
    print("DONE", len(order))


if __name__ == "__main__":
    main()
