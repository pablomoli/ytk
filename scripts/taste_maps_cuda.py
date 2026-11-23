"""Every measurement kept as a map over the whole frame, and how the maps move together.

Nothing is averaged down to one number per frame. For each frame, at its own size:
  maps      22 channels, one value per pixel (light, color, edges and their direction,
            detail at five scales, local contrast, stroke, flat ground ...)
  together  the correlation of every pair of channels across all pixels: at four scales
            (the frame as is, and blurred 4x, 16x, 64x), and inside each cell of a 4x4 grid
The maps are never written: a frame's 22 maps are 22 times its pixels, and the frame
and this file reproduce them exactly. Only the statistics are returned.
Standalone for a CUDA machine (runs on CPU too): torch, numpy, PIL. Run by taste_pass_cuda.py.
"""

from __future__ import annotations

import math

import numpy as np
import torch
import torch.nn.functional as F

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


def measure(rgb: torch.Tensor) -> dict[str, np.ndarray]:
    """rgb is the decoded frame, (3, H, W) in 0..1 on DEV. The maps live only for this call."""
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
    # The same correlations inside a part of the frame only. On a frame that is mostly black,
    # every map marks the same small lit region, so whole-frame correlations all rise together;
    # these ask how the maps relate within that region. Too few pixels gives no answer (NaN).
    lit = maps[NAMES.index("dark ground")] < 0.5
    busy = maps[NAMES.index("flat ground")] < 0.5
    iu = torch.triu_indices(len(NAMES), len(NAMES), 1)
    for name, mask in (("lit", lit), ("busy", busy)):
        share = mask.float().mean()
        if share < 0.005:
            out[f"together_{name}"] = np.full(iu.shape[1], np.nan, np.float32)
        else:
            # Masked moments in place: the selected pixels are never copied out, which a 4K frame cannot afford.
            m = mask.float()
            cnt = m.sum()
            mu = (maps * m).flatten(1).sum(1) / cnt
            v = ((maps - mu[:, None, None]) * m).flatten(1)
            cov = (v @ v.T) / cnt
            sd = cov.diagonal().clamp_min(0).sqrt()
            c = cov / (sd[:, None] * sd[None, :]).clamp_min(1e-12)
            pair_ok = (sd > 1e-6)[:, None] & (sd > 1e-6)[None, :]
            c = torch.where(pair_ok, c, torch.full_like(c, float("nan")))
            out[f"together_{name}"] = c[iu[0], iu[1]].cpu().numpy()
            del v, cov
        out[f"support_{name}"] = np.array([float(share)], np.float32)
    return out
