"""Every measurement kept as a map over the whole frame, and how the maps move together.

Nothing is averaged down to one number per frame. For each frame, at its own size:
  maps      22 channels, one value per pixel (light, color, edges and their direction,
            detail at five scales, local contrast, stroke, flat ground ...)
  together  the correlation of every pair of channels across all pixels: at four scales
            (the frame as is, and blurred 4x, 16x, 64x), and inside each cell of a 4x4 grid
The full maps are written to disk beside the statistics.
Standalone for a CUDA machine (runs on CPU too): torch, numpy, PIL.

    python taste_maps_cuda.py <flat_dir> <order.json> <out_dir> [--no-maps]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

DEV = "cuda" if torch.cuda.is_available() else "cpu"
SCALES = (1, 4, 16, 64)
NAMES = [
    "light", "saturation", "brightness", "chroma", "red-green", "yellow-blue", "hue cos", "hue sin", "dark ground", "colored",
    "edge strength", "edge direction cos", "edge direction sin", "detail 1", "detail 2", "detail 3", "detail 4", "detail 5",
    "local contrast", "edge alignment", "thin stroke", "flat ground",
]  # fmt: skip


def box(x: torch.Tensor, k: int) -> torch.Tensor:
    k = max(3, k | 1)
    return F.avg_pool2d(F.pad(x[None, None], (k // 2,) * 4, mode="reflect"), k, 1)[0, 0]


def channels(rgb: torch.Tensor) -> torch.Tensor:
    """(22, H, W): every channel is a full map of the frame."""
    H, W = rgb.shape[1:]
    long = max(H, W)
    r, g, b = rgb
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    mx, mn = rgb.max(0).values, rgb.min(0).values
    d = mx - mn
    hue = torch.zeros_like(mx)
    m = d > 1e-6
    rm, gm = m & (mx == r), m & (mx == g) & (mx != r)
    bm = m & ~rm & ~gm
    hue[rm] = ((g - b)[rm] / d[rm]) % 6
    hue[gm] = (b - r)[gm] / d[gm] + 2
    hue[bm] = (r - g)[bm] / d[bm] + 4
    ang = hue / 6 * 2 * math.pi
    sat = torch.where(mx > 1e-6, d / mx.clamp_min(1e-6), torch.zeros_like(mx))
    chroma = sat * mx
    dark = (lum < 0.08).float()
    colored = ((chroma > 0.25) & (lum >= 0.08)).float()
    gx = F.pad(lum[:, 2:] - lum[:, :-2], (1, 1)) / 2
    gy = F.pad((lum[2:] - lum[:-2]).T, (1, 1)).T / 2
    mag = torch.hypot(gx, gy) * (long / 1000)
    th = torch.atan2(gy, gx)
    detail, cur = [], lum[None, None]
    for _ in range(5):
        down = F.avg_pool2d(cur, 2, ceil_mode=True)
        up = F.interpolate(down, size=cur.shape[-2:], mode="bilinear", align_corners=False)
        detail.append(
            F.interpolate((cur - up).abs(), size=(H, W), mode="bilinear", align_corners=False)[0, 0]
        )
        cur = down
    k = max(3, long // 100)
    contrast = (box(lum * lum, k) - box(lum, k) ** 2).clamp_min(0).sqrt()
    jxx, jyy, jxy = box(gx * gx, k), box(gy * gy, k), box(gx * gy, k)
    align = torch.sqrt((jxx - jyy) ** 2 + 4 * jxy**2) / (jxx + jyy + 1e-9)
    # Thin stroke: colored pixels that a small erosion (0.3% of the long side) would remove.
    e = max(1, round(long * 0.003))
    eroded = -F.max_pool2d(-colored[None, None], 2 * e + 1, 1, e)[0, 0]
    thin = colored - eroded
    flat = (contrast < 0.02).float()
    return torch.stack([lum, sat, mx, chroma, r - g, 0.5 * (r + g) - b, chroma * torch.cos(ang), chroma * torch.sin(ang), dark, colored,
                        mag, mag * torch.cos(2 * th), mag * torch.sin(2 * th), *detail, contrast, align, thin, flat])  # fmt: skip


def together(x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Means, spreads and the correlation of every pair of channels over all positions of x (C, h, w)."""
    v = x.flatten(1).double()
    mu = v.mean(1)
    v = v - mu[:, None]
    sd = v.pow(2).mean(1).sqrt()
    c = (v @ v.T) / v.shape[1] / (sd[:, None] * sd[None, :]).clamp_min(1e-12)
    c[(sd < 1e-7)[:, None] | (sd < 1e-7)[None, :]] = 0
    iu = torch.triu_indices(len(mu), len(mu), 1)
    return mu.float(), sd.float(), c[iu[0], iu[1]].float()


def measure(path: Path) -> tuple[dict[str, np.ndarray], torch.Tensor]:
    with Image.open(path) as im:
        rgb = torch.from_numpy(np.asarray(im.convert("RGB"))).to(DEV).permute(2, 0, 1).float() / 255
    maps = channels(rgb)
    out: dict[str, np.ndarray] = {}
    for s in SCALES:
        x = maps if s == 1 else F.avg_pool2d(maps[None], s, ceil_mode=True)[0]
        mu, sd, c = together(x)
        out[f"together_scale_{s}"] = torch.cat([c, sd]).cpu().numpy()
        if s == 1:
            out["level"] = mu.cpu().numpy()
    H, W = maps.shape[1:]
    cells = []
    for i in range(4):
        for j in range(4):
            mu, sd, c = together(
                maps[:, i * H // 4 : (i + 1) * H // 4, j * W // 4 : (j + 1) * W // 4]
            )
            cells.append(torch.cat([c, mu]))
    out["together_by_region"] = torch.cat(cells).cpu().numpy()
    return out, maps


def main() -> None:
    flat, order, dst = (
        Path(sys.argv[1]),
        json.loads(Path(sys.argv[2]).read_text()),
        Path(sys.argv[3]),
    )
    keep = "--no-maps" not in sys.argv
    (dst / "maps").mkdir(parents=True, exist_ok=True)
    rows, pixels, written = [], 0, 0
    for i, o in enumerate(order, 1):
        stats, maps = measure(flat / o["name"])
        rows.append(stats)
        pixels += maps.shape[1] * maps.shape[2]
        if keep:
            target = dst / "maps" / (Path(o["name"]).stem + ".npy")
            np.save(target, maps.half().cpu().numpy())
            written += target.stat().st_size
        del maps
        if i % 25 == 0 or i == len(order):
            print(
                f"{i}/{len(order)}  {pixels / 1e6:.0f} megapixels read, {written / 1e9:.1f} GB of maps written",
                flush=True,
            )
    fams = list(rows[0])
    np.savez_compressed(
        dst / "together.npz",
        families=np.array(fams),
        channels=np.array(NAMES),
        **{f: np.nan_to_num(np.stack([r[f] for r in rows])) for f in fams},
    )
    print(
        "DONE",
        len(rows),
        "frames,",
        len(NAMES),
        "channels,",
        sum(rows[0][f].size for f in fams),
        "numbers per frame,",
        f"{written / 1e9:.1f} GB of maps",
    )


if __name__ == "__main__":
    main()
