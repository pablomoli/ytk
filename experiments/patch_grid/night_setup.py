"""Night setup: SAM masks + one SigLIP-2 pass per image, cached.

HF_HUB_OFFLINE=1 uv run --with torchvision python experiments/patch_grid/night_setup.py
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
    from transformers import pipeline

    N.CACHE.mkdir(parents=True, exist_ok=True)
    model, processor, device = visual._load()
    vision = model.vision_model
    sam = pipeline("mask-generation", model=N.SAM_MODEL, device="mps")
    for name in N.IMAGES:
        f = N.cache_file(name)
        if f.exists():
            print("cached", name)
            continue
        t0 = time.time()
        pil = Image.open(N.image_path(name)).convert("RGB")
        out = sam(pil, **N.SAM_KW)
        masks = np.stack([np.asarray(m, dtype=bool) for m in out["masks"]])
        area = masks.reshape(len(masks), -1).mean(1)
        keep = (area > N.AREA_MIN) & (area < N.AREA_MAX)
        masks = masks[keep]
        order = np.argsort(-masks.reshape(len(masks), -1).mean(1))  # large first
        masks = masks[order]
        t_sam = time.time() - t0
        grids = np.stack([N.patch_grid_from_mask(m) for m in masks])
        px = (
            processor(images=[pil], return_tensors="pt")["pixel_values"]
            .to(device)
            .to(torch.float16)
        )
        with torch.no_grad():
            o = vision(pixel_values=px)
        tokens = o.last_hidden_state[0].float().cpu().numpy()
        pooled = o.pooler_output[0].float().cpu().numpy()
        np.savez_compressed(
            f,
            masks=masks,
            grids=grids,
            tokens=tokens.astype(np.float32),
            pooled=pooled.astype(np.float32),
            size=np.array(pil.size),
            sam_seconds=t_sam,
        )
        empty = int((grids.sum(axis=(1, 2)) == 0).sum())
        print(
            f"{name}: {len(masks)} masks in {t_sam:.0f}s, {empty} with no patch at half coverage, {time.time() - t0:.0f}s total",
            flush=True,
        )


if __name__ == "__main__":
    main()
