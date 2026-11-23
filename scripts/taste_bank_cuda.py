"""A wide bank of image measurements for the taste test frames, on the whole image at its own size.

Every measure is taken over the full frame as served and is expressed relative to the frame
(cycles per image, fractions of the long side), so a 4K frame and a 720p frame are read on the
same terms. Families are kept apart so a later step can ask which carry what.
Standalone for a CUDA machine: torch, numpy, scipy, PIL. Run by taste_pass_cuda.py.
"""

from __future__ import annotations

import io
import math
from itertools import pairwise

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from scipy import ndimage

DEV = "cuda" if torch.cuda.is_available() else "cpu"


def hsv(rgb: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    r, g, b = rgb
    mx, mn = rgb.max(0).values, rgb.min(0).values
    d = mx - mn
    h = torch.zeros_like(mx)
    m = d > 1e-6
    rm, gm = m & (mx == r), m & (mx == g) & (mx != r)
    bm = m & ~rm & ~gm
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = (b - r)[gm] / d[gm] + 2
    h[bm] = (r - g)[bm] / d[bm] + 4
    return h / 6, torch.where(mx > 1e-6, d / mx.clamp_min(1e-6), torch.zeros_like(mx)), mx


def grid(x: torch.Tensor, n: int) -> torch.Tensor:
    return F.adaptive_avg_pool2d(x[None, None].float(), n)[0, 0].flatten()


def blur(x: torch.Tensor, k: int) -> torch.Tensor:
    # A box average is the same taken along rows then columns: 2k taps per pixel, not k squared.
    k = max(3, k | 1)
    h = k // 2
    x = F.avg_pool2d(F.pad(x[None, None], (h, h, 0, 0), mode="reflect"), (1, k), 1)
    return F.avg_pool2d(F.pad(x, (0, 0, h, h), mode="reflect"), (k, 1), 1)[0, 0]


def entropy(p: torch.Tensor) -> torch.Tensor:
    p = p / p.sum().clamp_min(1e-12)
    return -(p[p > 0] * p[p > 0].log()).sum() / math.log(max(p.numel(), 2))


def moments(w: torch.Tensor) -> list[torch.Tensor]:
    """Where a map's mass sits and how far it spreads, in fractions of the frame."""
    h, wd = w.shape
    tot = w.sum().clamp_min(1e-9)
    ys = torch.linspace(0, 1, h, device=w.device)[:, None]
    xs = torch.linspace(0, 1, wd, device=w.device)[None, :]
    cx, cy = (w * xs).sum() / tot, (w * ys).sum() / tot
    sx, sy = ((w * (xs - cx) ** 2).sum() / tot).sqrt(), ((w * (ys - cy) ** 2).sum() / tot).sqrt()
    return [
        cx,
        cy,
        sx,
        sy,
        w[:, : wd // 2].sum() / tot,
        w[: h // 2].sum() / tot,
        w[h // 3 : 2 * h // 3, wd // 3 : 2 * wd // 3].sum() / tot,
    ]


def jpeg_bits(im: Image.Image) -> float:
    """Bits per pixel of the frame saved as JPEG at quality 75: a plain measure of how busy it is."""
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=75)
    return buf.tell() * 8 / (im.width * im.height)


def measure(rgb: torch.Tensor, jpeg_bpp: float) -> dict[str, np.ndarray]:
    """rgb is the decoded frame, (3, H, W) in 0..1 on DEV."""
    H, W = rgb.shape[1:]
    long = max(H, W)
    lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    hue, sat, val = hsv(rgb)
    chroma = sat * val
    dark = lum < 0.08
    colored = (chroma > 0.25) & ~dark
    gx = F.pad(lum[:, 2:] - lum[:, :-2], (1, 1)) / 2
    gy = F.pad((lum[2:] - lum[:-2]).T, (1, 1)).T / 2
    # Gradients per pixel shrink as resolution grows; scale them to "per thousandth of the long side".
    mag = torch.hypot(gx, gy) * (long / 1000)
    out: dict[str, list] = {}
    q = torch.quantile(
        lum.flatten()[:: max(1, lum.numel() // 500_000)],
        torch.tensor([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99], device=DEV),
    )
    sd = lum.std().clamp_min(1e-6)
    out["tone"] = [
        lum.mean(),
        sd,
        ((lum - lum.mean()) ** 3).mean() / sd**3,
        *q,
        dark.float().mean(),
        (lum > 0.92).float().mean(),
        q[-1] - q[0],
    ]
    out["light_histogram"] = list(torch.histc(lum, 16, 0, 1) / lum.numel())
    rg, yb = rgb[0] - rgb[1], 0.5 * (rgb[0] + rgb[1]) - rgb[2]
    out["color"] = [
        sat.mean(),
        sat.std(),
        val.mean(),
        torch.hypot(rg.std(), yb.std()) + 0.3 * torch.hypot(rg.mean(), yb.mean()),
        chroma.mean(),
        chroma.std(),
        colored.float().mean(),
        rg.mean(),
        yb.mean(),
    ]
    hh = (
        torch.zeros(18, device=DEV).index_add_(
            0, (hue.flatten() * 18).long().clamp(0, 17), chroma.flatten()
        )
        / lum.numel()
    )
    ang = hue * 2 * math.pi
    tot = chroma.sum().clamp_min(1e-9)
    harm = [
        torch.hypot((chroma * torch.cos(k * ang)).sum(), (chroma * torch.sin(k * ang)).sum()) / tot
        for k in (1, 2, 3)
    ]
    out["hue"] = [
        *(hh * 6),
        (chroma * torch.cos(ang)).sum() / tot,
        (chroma * torch.sin(ang)).sum() / tot,
        *harm,
    ]
    hs = (
        torch.zeros(24, device=DEV).index_add_(
            0,
            ((hue.flatten() * 6).long().clamp(0, 5) * 4 + (sat.flatten() * 4).long().clamp(0, 3)),
            val.flatten(),
        )
        / lum.numel()
    )
    out["hue_by_saturation"] = list(hs)
    # Palette: five colors by k-means on a sample of pixels, largest first.
    px = rgb.flatten(1).T[
        torch.randperm(lum.numel(), device=DEV, generator=torch.Generator(DEV).manual_seed(0))[
            :20000
        ]
    ]
    cen = px[torch.linspace(0, len(px) - 1, 5, device=DEV).long()].clone()
    for _ in range(12):
        lab = torch.cdist(px, cen).argmin(1)
        for k in range(5):
            if (lab == k).any():
                cen[k] = px[lab == k].mean(0)
    share = torch.bincount(lab, minlength=5).float() / len(px)
    o = share.argsort(descending=True)
    pd = torch.cdist(cen, cen)
    out["palette"] = [
        *torch.cat([cen[o], share[o, None]], 1).flatten(),
        pd[pd > 0].min() if (pd > 0).any() else pd.sum(),
        pd.mean(),
    ]
    rest = chroma[~dark]
    out["dark_ground"] = [
        dark.float().mean(),
        rest.mean() if rest.numel() else lum.sum() * 0,
        dark.float().mean() * (rest.mean() if rest.numel() else 0),
        lum[~dark].mean() if rest.numel() else lum.sum() * 0,
        (colored & ~dark).float().mean() / (~dark).float().mean().clamp_min(1e-6),
    ]
    # Frequency content of the whole frame, in cycles per image.
    win = torch.hann_window(H, device=DEV)[:, None] * torch.hann_window(W, device=DEV)[None, :]
    P = torch.fft.fftshift(torch.fft.fft2((lum - lum.mean()) * win)).abs() ** 2
    fy = torch.arange(H, device=DEV)[:, None] - H // 2
    fx = torch.arange(W, device=DEV)[None, :] - W // 2
    rad = torch.hypot(fx.float(), fy.float() * (W / H))
    edges_r = torch.logspace(0, math.log10(360), 13, device=DEV)
    band = torch.stack([P[(rad >= a) & (rad < b)].sum() for a, b in pairwise(edges_r)])
    lb = (band / band.sum().clamp_min(1e-12)).clamp_min(1e-12).log()
    xr = torch.arange(12, device=DEV).float()
    slope = ((xr - xr.mean()) * (lb - lb.mean())).sum() / ((xr - xr.mean()) ** 2).sum()
    out["frequency"] = [*lb, slope]
    th = torch.atan2(fy.float() * (W / H), fx.float()) % math.pi
    mid = (rad >= 8) & (rad < 120)
    ob = torch.stack(
        [P[mid & (th >= k * math.pi / 8) & (th < (k + 1) * math.pi / 8)].sum() for k in range(8)]
    )
    ob = ob / ob.sum().clamp_min(1e-12)
    out["frequency_direction"] = [*ob, ob.max() - ob.min(), entropy(ob)]
    # Detail at each scale: a pyramid from fine to coarse, energy and how concentrated it is.
    pyr, cur = [], lum[None, None]
    for _ in range(6):
        if min(cur.shape[-2:]) < 8:
            pyr += [lum.sum() * 0, lum.sum() * 0]
            continue
        down = F.avg_pool2d(cur, 2)
        lap = cur[..., : down.shape[-2] * 2, : down.shape[-1] * 2] - F.interpolate(
            down, scale_factor=2, mode="nearest"
        )
        v = lap.var().clamp_min(1e-12)
        pyr += [v.sqrt(), (lap**4).mean() / v**2]
        cur = down
    out["detail_by_scale"] = pyr
    oa = torch.atan2(gy, gx) % math.pi
    oh = torch.zeros(8, device=DEV).index_add_(
        0, (oa.flatten() / math.pi * 8).long().clamp(0, 7), mag.flatten()
    )
    oh = oh / oh.sum().clamp_min(1e-12)
    coh = []
    for frac in (0.01, 0.04):
        k = max(3, int(long * frac))
        jxx, jyy, jxy = blur(gx * gx, k), blur(gy * gy, k), blur(gx * gy, k)
        c = torch.sqrt((jxx - jyy) ** 2 + 4 * jxy**2) / (jxx + jyy + 1e-9)
        coh.append((c * mag).sum() / mag.sum().clamp_min(1e-9))
    out["edges"] = [
        mag.mean(),
        mag.std(),
        *[(mag > t).float().mean() for t in (0.05, 0.15, 0.4)],
        *oh,
        entropy(oh),
        *coh,
    ]
    edge_map = (mag > 0.15).float()
    out["layout"] = [*grid(lum, 4), *grid(sat, 4), *grid(edge_map, 4), *grid(colored, 4)]
    out["thumbnail"] = list(grid(lum, 8))
    out["balance"] = [m for w in (lum, chroma, mag, colored.float()) for m in moments(w)]
    sym = []
    for m in (lum, edge_map):
        t = F.adaptive_avg_pool2d(m[None, None], 64)[0, 0]
        t = (t - t.mean()) / t.std().clamp_min(1e-6)
        sym += [(t * t.flip(1)).mean(), (t * t.flip(0)).mean(), (t * t.flip(0).flip(1)).mean()]
    out["symmetry"] = sym
    out["spread"] = [
        entropy(grid(m, n).clamp_min(0)) for m in (colored, edge_map) for n in (2, 4, 8, 16)
    ]
    # Regions and stroke widths on a mask reduced to 1024 on the long side, sizes kept relative to the frame.
    s = 1024 / long
    small = (
        F.interpolate(
            colored[None, None].float(),
            size=(max(8, round(H * s)), max(8, round(W * s))),
            mode="area",
        )[0, 0]
        .cpu()
        .numpy()
        > 0.5
    )
    lab, n = ndimage.label(small)
    sizes = np.bincount(lab.ravel())[1:] if n else np.array([0])
    area = max(small.sum(), 1)
    widths = [1 - ndimage.binary_erosion(small, iterations=r).sum() / area for r in (1, 3, 6, 12)]
    flat_std = blur((lum - blur(lum, max(3, long // 32))) ** 2, max(3, long // 32)).sqrt()
    out["regions"] = [
        math.log1p((sizes > small.size * 0.0005).sum()),
        sizes.max() / area,
        (sizes > small.size * 0.01).sum(),
        small.mean(),
        (flat_std < 0.02).float().mean(),
    ]
    out["stroke_width"] = widths
    out["complexity"] = [
        entropy(torch.histc(lum, 64, 0, 1)),
        jpeg_bpp,
        entropy(torch.histc(mag.clamp(0, 1), 32, 0, 1)),
        math.log(H * W),
        W / H,
    ]
    return {k: np.array([float(x) for x in v], np.float32) for k, v in out.items()}
