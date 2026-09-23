"""Section 54 (#218): the region-masked head against crop-on-grey and occlusion.

HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run54.py woman   # spike caches only, CPU head
HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run54.py all     # crop-on-grey for all ten, ~3 min GPU
"""

from __future__ import annotations

import copy
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import night as N
from region_head import ensure_one_patch, region_vectors

from ytk import visual


def unit(x: np.ndarray) -> np.ndarray:
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def load_head():
    model, processor, device = visual._load()
    head = copy.deepcopy(model.vision_model.head).float().cpu()
    scale = float(model.logit_scale.exp())
    bias = float(model.logit_bias)
    return model, processor, device, head, scale, bias


def crops_on_grey(pil: Image.Image, masks: np.ndarray, pad: int = 12) -> list[Image.Image]:
    """The spike's method: keep one region, grey the rest, crop to its box."""
    arr = np.asarray(pil)
    grey = np.full_like(arr, 127)
    w, h = pil.size
    out = []
    for m in masks:
        ys, xs = np.where(m)
        x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, w)
        y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, h)
        out.append(Image.fromarray(np.where(m[..., None], arr, grey)[y0:y1, x0:x1]))
    return out


def pooled(vision, processor, device, images: list[Image.Image]) -> np.ndarray:
    P = []
    with torch.no_grad():
        for s in range(0, len(images), 16):
            px = processor(images=images[s : s + 16], return_tensors="pt")["pixel_values"]
            px = px.to(device).to(torch.float16)
            P.append(vision(pixel_values=px).pooler_output.float().cpu().numpy())
    return np.concatenate(P)


def woman() -> None:
    """The spike's 46 masks in the spike's order, so crop-on-grey and the
    sliding occlusion are read from the caches; only the masked head is new."""
    model, processor, device, head, scale, bias = load_head()
    sm = np.load(N.SPIKES / "sam_masks.npz", allow_pickle=True)
    sc = np.load(N.SPIKES / "sam_scores.npz", allow_pickle=True)
    sl = np.load(N.SPIKES / "slide.npz", allow_pickle=True)
    masks = sm["masks"]
    grids = np.stack([N.patch_grid_from_mask(m) for m in masks])
    grids, fixed = ensure_one_patch(grids, masks)
    tokens = N.load("woman-river")["tokens"]
    qs = [str(q) for q in sc["qs"]]
    txt = unit(np.array(visual.embed_texts(qs)))
    V = unit(region_vectors(head, tokens, grids))
    cos_head = V @ txt.T
    np.savez_compressed(
        N.CACHE / "54_woman.npz",
        masks=masks,
        grids=grids,
        qs=np.array(qs),
        cos_head=cos_head,
        cos_crop=sc["cos"][1:],
        base=sc["cos"][0],
        slide_qs=sl["qs"],
        slide_heat=sl["heat"],
        slide_base=sl["base"],
        scale=scale,
        bias=bias,
        fixed=fixed,
    )
    for j, q in enumerate(qs):
        a, b = int(cos_head[:, j].argmax()), int(sc["cos"][1:, j].argmax())
        print(
            f"{q[:40]:42} head winner {a:2d} (area {masks[a].mean():.3f})  crop winner {b:2d} (area {masks[b].mean():.3f})  {'same' if a == b else 'DIFFER'}"
        )
    print("regions given one patch:", fixed)


def everything() -> None:
    model, processor, device, head, scale, bias = load_head()
    vision = model.vision_model
    qs = N.queries()
    out: dict[str, np.ndarray] = {"scale": np.array(scale), "bias": np.array(bias)}
    t0 = time.time()
    for name in N.IMAGES:
        d = N.load(name)
        grids, fixed = ensure_one_patch(d["grids"], d["masks"])
        txt = unit(np.array(visual.embed_texts(qs[name])))
        V = unit(region_vectors(head, d["tokens"], grids))
        pil = Image.open(N.image_path(name)).convert("RGB")
        C = unit(pooled(vision, processor, device, crops_on_grey(pil, d["masks"])))
        out[f"{name}/grids"] = grids
        out[f"{name}/cos_head"] = V @ txt.T
        out[f"{name}/cos_crop"] = C @ txt.T
        out[f"{name}/base"] = unit(d["pooled"][None])[0] @ txt.T
        out[f"{name}/fixed"] = np.array(fixed)
        agree = sum(
            int(out[f"{name}/cos_head"][:, j].argmax() == out[f"{name}/cos_crop"][:, j].argmax())
            for j in range(3)
        )
        print(
            f"{name:18} {len(grids):3d} regions  winners agree on {agree}/3  {time.time() - t0:.0f}s",
            flush=True,
        )
    np.savez_compressed(N.CACHE / "54_all.npz", **out)


def cover(pil: Image.Image, mask: np.ndarray) -> Image.Image:
    arr = np.asarray(pil).copy()
    arr[mask] = 127
    return Image.fromarray(arr)


def tiebreak() -> None:
    """Where crop-on-grey and the masked head pick different winners, cover
    each candidate region in turn and re-encode: the larger drop in the
    image-text cosine is the region the model actually needed."""
    model, processor, device, head, scale, bias = load_head()
    vision = model.vision_model
    a = dict(np.load(N.CACHE / "54_all.npz", allow_pickle=True))
    ceiling = max(float(a[f"{n}/base"][2]) for n in N.IMAGES)
    qs = N.queries()
    rows = []
    for name in N.IMAGES:
        d = N.load(name)
        pil = Image.open(N.image_path(name)).convert("RGB")
        txt = unit(np.array(visual.embed_texts(qs[name])))
        for j in range(3):
            base = float(a[f"{name}/base"][j])
            wc, wh = (
                int(a[f"{name}/cos_crop"][:, j].argmax()),
                int(a[f"{name}/cos_head"][:, j].argmax()),
            )
            if wc == wh or base <= ceiling:
                continue
            P = unit(
                pooled(
                    vision,
                    processor,
                    device,
                    [cover(pil, d["masks"][wc]), cover(pil, d["masks"][wh])],
                )
            )
            drops = base - P @ txt[j]
            rows.append((name, j, wc, wh, float(drops[0]), float(drops[1]), base))
            print(
                f"{name:18} q{j} crop {wc:3d} drop {drops[0]:+.3f}   head {wh:3d} drop {drops[1]:+.3f}   base {base:.3f}  -> {'head' if drops[1] > drops[0] else 'crop'}",
                flush=True,
            )
    np.savez_compressed(
        N.CACHE / "54_tiebreak.npz",
        name=np.array([r[0] for r in rows]),
        q=np.array([r[1] for r in rows]),
        crop=np.array([r[2] for r in rows]),
        head=np.array([r[3] for r in rows]),
        drop_crop=np.array([r[4] for r in rows]),
        drop_head=np.array([r[5] for r in rows]),
        base=np.array([r[6] for r in rows]),
        ceiling=np.array(ceiling),
    )


def attention() -> None:
    """The probe's attention confined to each region of the woman image, and
    unconfined, for the mechanism figure."""
    from region_head import region_attention

    model, processor, device, head, scale, bias = load_head()
    w = np.load(N.CACHE / "54_woman.npz", allow_pickle=True)
    tokens = N.load("woman-river")["tokens"]
    grids = w["grids"]
    att = np.stack([region_attention(head, tokens, g) for g in grids])
    full = region_attention(head, tokens, np.ones((N.SIDE, N.SIDE), dtype=bool))
    np.savez_compressed(N.CACHE / "54_attention.npz", att=att, full=full)
    top = att.reshape(len(att), -1).max(1)
    print(
        "regions",
        len(att),
        "| share on the top token: median",
        np.median(top).round(2),
        "min",
        top.min().round(2),
        "max",
        top.max().round(2),
        "| unconfined top token",
        full.max().round(3),
    )


if __name__ == "__main__":
    {"woman": woman, "all": everything, "tiebreak": tiebreak, "attention": attention}[sys.argv[1]]()
