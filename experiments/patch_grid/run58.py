"""Section 58 (#218): the whole-encoder gradient lens (LeGrad, arXiv 2404.03214).

Gradient of the image-text cosine with respect to every layer's attention map,
clamped at zero, averaged over heads and query rows, one map per layer, then
averaged over layers. One forward and one backward per image-query pair.

    HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run58.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import night as N

from ytk import visual


def main() -> None:
    model, processor, device = visual._load()
    vision = model.vision_model
    vision.config._attn_implementation = "eager"  # the interface is looked up per forward
    layers = vision.encoder.layers
    kept: list[torch.Tensor] = []

    def hook(_m, _i, out):
        w = out[1]
        w.retain_grad()
        kept.append(w)

    resid: list[torch.Tensor] = []

    def hook_out(_m, _i, out):
        h = out[0] if isinstance(out, tuple) else out
        h.retain_grad()
        resid.append(h)

    handles = [layer.self_attn.register_forward_hook(hook) for layer in layers]
    handles += [layer.register_forward_hook(hook_out) for layer in layers]
    qs = N.queries()
    out: dict[str, np.ndarray] = {}
    t0 = time.time()
    for name in N.IMAGES:
        pil = Image.open(N.image_path(name)).convert("RGB")
        px = (
            processor(images=[pil], return_tensors="pt")["pixel_values"]
            .to(device)
            .to(torch.float16)
        )
        txt = torch.tensor(np.array(visual.embed_texts(qs[name])), dtype=torch.float32)
        txt = txt / txt.norm(dim=-1, keepdim=True)
        maps = np.zeros((3, len(layers), N.SIDE, N.SIDE), dtype=np.float32)
        gxa = np.zeros_like(maps)  # gradient x activation on each layer's output tokens
        for j in range(3):
            kept.clear()
            resid.clear()
            vision.zero_grad(set_to_none=True)
            o = vision(pixel_values=px)
            v = o.pooler_output[0].float().cpu()
            s = (v / v.norm()) @ txt[j]
            s.backward()
            for li, w in enumerate(kept):
                g = w.grad.float().clamp(min=0)  # (1, heads, 576, 576)
                maps[j, li] = (
                    g.mean(dim=(0, 1, 2)).cpu().numpy().reshape(N.SIDE, N.SIDE)
                )  # per key patch
            for li, h in enumerate(resid):
                r = (h.grad.float() * h.detach().float())[0].sum(-1).clamp(min=0)
                gxa[j, li] = r.cpu().numpy().reshape(N.SIDE, N.SIDE)
        out[f"{name}/layers"] = maps
        out[f"{name}/lens"] = maps.mean(axis=1)
        out[f"{name}/gxa_layers"] = gxa
        out[f"{name}/gxa"] = gxa.mean(axis=1)
        peak_a = [float(m.max() / m.sum()) for m in maps.mean(axis=1)]
        peak_g = [float(m.max() / max(m.sum(), 1e-12)) for m in gxa.mean(axis=1)]
        print(
            f"{name:18} {time.time() - t0:.0f}s  peak share, attention-gradient {np.round(peak_a, 3).tolist()}  grad x activation {np.round(peak_g, 3).tolist()}",
            flush=True,
        )
    for h in handles:
        h.remove()
    np.savez_compressed(N.CACHE / "58_legrad.npz", **out)


if __name__ == "__main__":
    main()
