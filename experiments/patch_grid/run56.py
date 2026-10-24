"""Section 56 (#218): a sturdier referee. Whole-object occlusion on all ten, RISE on three.

Both stages store text-independent pooled vectors, so any query's map is one
dot product at plot time.

    HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run56.py objects   # ~5 min GPU
    HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run56.py rise      # ~35 min GPU, three images
    HF_HUB_OFFLINE=1 uv run python experiments/patch_grid/run56.py area      # ~5 min GPU, the area control
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


AREA_DRAWS = 16
AREA_CANDIDATES = 200  # the null keeps the AREA_DRAWS shifts that overlap the original least


def area() -> None:
    """The control section 56 lacked: each contested region against the same
    mask slid to AREA_DRAWS random places in the frame (wrapping at the edges),
    so shape and area are held and only the place moves. A region larger than
    half the frame cannot be slid off itself; its overlap is recorded. Contested regions are
    section 54's eight disagreements, both sides, and on all ten images the
    small-object query's whole-object winner and crop-on-grey's pick."""
    model, processor, device = visual._load()
    vision = model.vision_model
    a = dict(np.load(N.CACHE / "54_all.npz", allow_pickle=True))
    t = dict(np.load(N.CACHE / "54_tiebreak.npz", allow_pickle=True))
    pairs: set[tuple[str, int, int]] = set()
    for name, q, c, h in zip(t["name"], t["q"], t["crop"], t["head"]):
        pairs |= {(str(name), int(q), int(c)), (str(name), int(q), int(h))}
    for name in N.IMAGES:
        o = dict(np.load(N.CACHE / f"56_objects_{name}.npz"))
        drops = float(o["base"] @ o["txt"][0]) - o["covered"].astype(np.float32) @ o["txt"][0]
        pairs |= {
            (name, 0, int(drops.argmax())),
            (name, 0, int(a[f"{name}/cos_crop"][:, 0].argmax())),
        }
    rng = np.random.default_rng(56)
    rows = []
    t0 = time.time()
    for name in N.IMAGES:
        todo = sorted(p for p in pairs if p[0] == name)
        if not todo:
            continue
        d = N.load(name)
        o = dict(np.load(N.CACHE / f"56_objects_{name}.npz"))
        pil = Image.open(N.image_path(name)).convert("RGB")
        h, w = d["masks"].shape[1:]
        imgs, index, overlap = [], [], {}
        for _, q, r in todo:
            m = d["masks"][r]
            cands = [
                np.roll(m, (int(rng.integers(h)), int(rng.integers(w))), axis=(0, 1))
                for _ in range(AREA_CANDIDATES)
            ]
            ov = np.array([(c & m).sum() / m.sum() for c in cands])
            keep = np.argsort(ov)[:AREA_DRAWS]
            overlap[(q, r)] = float(ov[keep].mean())
            for k in keep:
                imgs.append(cover(pil, cands[k]))
                index.append((q, r))
        P = unit(pooled(vision, processor, device, imgs))
        for q, r in sorted({(q, r) for _, q, r in todo}):
            base = float(o["base"] @ o["txt"][q])
            drop = base - float(o["covered"][r].astype(np.float32) @ o["txt"][q])
            sel = [i for i, k in enumerate(index) if k == (q, r)]
            null = base - P[sel] @ o["txt"][q]
            rows.append(
                {
                    "name": name,
                    "q": q,
                    "region": r,
                    "area": float(d["masks"][r].mean()),
                    "drop": drop,
                    "null": null.astype(np.float32),
                    "overlap": overlap[(q, r)],
                }
            )
            print(
                f"{name:18} q{q} region {r:3d}  area {d['masks'][r].mean():5.1%}  drop {drop:+.4f}"
                f"  same shape elsewhere {np.median(null):+.4f} [{null.min():+.4f}, {null.max():+.4f}]"
                f"  above {int((drop > null).sum())}/{AREA_DRAWS}  overlap {overlap[(q, r)]:.0%}  {time.time() - t0:.0f}s",
                flush=True,
            )
    np.savez_compressed(
        N.CACHE / "56_area.npz",
        name=np.array([r["name"] for r in rows]),
        q=np.array([r["q"] for r in rows]),
        region=np.array([r["region"] for r in rows]),
        area=np.array([r["area"] for r in rows]),
        drop=np.array([r["drop"] for r in rows]),
        null=np.stack([r["null"] for r in rows]),
        overlap=np.array([r["overlap"] for r in rows]),
    )


if __name__ == "__main__":
    {"objects": objects, "rise": rise, "area": area}[sys.argv[1]]()
