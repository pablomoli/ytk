"""Section 56 (#218): a sturdier referee. Whole-object occlusion on all ten, RISE on three.

Both stages store text-independent pooled vectors, so any query's map is one
dot product at plot time.

    HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run56.py objects   # ~5 min GPU
    HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run56.py rise      # ~35 min GPU, three images
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
from run54 import cover, pooled, unit

from ytk import visual

RISE_IMAGES = ("woman-river", "goat", "sewing-cabinet")
RISE_N = 2000
RISE_GRID = 7  # low-resolution binary grid per mask, as in arXiv 1806.07421
RISE_P = 0.5


def objects() -> None:
    model, processor, device = visual._load()
    vision = model.vision_model
    qs = N.queries()
    t0 = time.time()
    for name in N.IMAGES:
        f = N.CACHE / f"56_objects_{name}.npz"
        if f.exists():
            print("cached", name)
            continue
        d = N.load(name)
        pil = Image.open(N.image_path(name)).convert("RGB")
        covered = unit(pooled(vision, processor, device, [cover(pil, m) for m in d["masks"]]))
        txt = unit(np.array(visual.embed_texts(qs[name])))
        base = unit(d["pooled"][None])[0]
        np.savez_compressed(
            f,
            covered=covered.astype(np.float16),
            txt=txt.astype(np.float32),
            base=base.astype(np.float32),
        )
        drop = (base @ txt.T) - covered @ txt.T
        print(
            f"{name:18} {len(covered):3d} regions covered  largest drop per query {np.round(drop.max(0), 3).tolist()}  {time.time() - t0:.0f}s",
            flush=True,
        )


def rise_masks(n: int, rng: np.random.Generator) -> np.ndarray:
    """RISE masks at 24 x 24: a random 7 x 7 binary grid, bilinearly upsampled
    with a random sub-cell shift, so every patch sees soft random covers."""
    cell = int(np.ceil(N.SIDE / RISE_GRID))
    up = (RISE_GRID + 1) * cell
    out = np.zeros((n, N.SIDE, N.SIDE), dtype=np.float32)
    for i in range(n):
        g = (rng.random((RISE_GRID, RISE_GRID)) < RISE_P).astype(np.float32)
        big = (
            np.asarray(Image.fromarray(g * 255).resize((up, up), Image.BILINEAR), dtype=np.float32)
            / 255.0
        )
        dx, dy = rng.integers(0, cell, size=2)
        out[i] = big[dy : dy + N.SIDE, dx : dx + N.SIDE]
    return out


def rise() -> None:
    model, processor, device = visual._load()
    vision = model.vision_model
    qs = N.queries()
    rng = np.random.default_rng(56)
    t0 = time.time()
    for name in RISE_IMAGES:
        f = N.CACHE / f"56_rise_{name}.npz"
        if f.exists():
            print("cached", name)
            continue
        pil = Image.open(N.image_path(name)).convert("RGB")
        px = processor(images=[pil], return_tensors="pt")["pixel_values"][0]
        masks = rise_masks(RISE_N, rng)
        P = []
        with torch.no_grad():
            for s in range(0, RISE_N, 16):
                m = torch.as_tensor(masks[s : s + 16])[:, None]  # (b, 1, 24, 24)
                m = torch.nn.functional.interpolate(
                    m, size=(N.INPUT, N.INPUT), mode="bilinear", align_corners=False
                )
                batch = px[None] * m  # zero in normalised space is mid grey, as in section 53
                P.append(
                    vision(pixel_values=batch.to(device).to(torch.float16))
                    .pooler_output.float()
                    .cpu()
                    .numpy()
                )
                if s % 400 == 0:
                    print(f"  {name} {s}/{RISE_N} {time.time() - t0:.0f}s", flush=True)
        P = unit(np.concatenate(P))
        txt = unit(np.array(visual.embed_texts(qs[name])))
        np.savez_compressed(
            f,
            masks=masks.astype(np.float16),
            pooled=P.astype(np.float16),
            txt=txt.astype(np.float32),
        )
        print(f"{name}: {RISE_N} masks in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    {"objects": objects, "rise": rise}[sys.argv[1]]()
