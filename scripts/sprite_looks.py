"""Measured look numbers for every sprite tile: no model, pixels only.

Per tile: brightness, contrast, saturation, colorfulness, edge density, dark
and bright share, a 12-bin hue histogram weighted by saturation, an 8-bin
brightness histogram. Per video: the mean and spread of each across its
tiles, plus how much consecutive tiles differ. Writes ~/.ytk/sprites/looks.npz.

    uv run python scripts/sprite_looks.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

SPRITES = Path.home() / ".ytk" / "sprites"
SCALARS = ["brightness", "contrast", "saturation", "colorfulness", "edges", "dark", "bright"]
HUE_BINS, LUM_BINS = 12, 8


def tile_features(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    # Hasler and Suesstrunk colorfulness on opponent channels.
    rg, yb = r - g, 0.5 * (r + g) - b
    colorful = np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean())
    edges = np.abs(np.diff(lum, axis=0)).mean() + np.abs(np.diff(lum, axis=1)).mean()
    d = mx - mn
    hue = np.zeros_like(mx)
    m = d > 1e-6
    rm, gm = m & (mx == r), m & (mx == g) & (mx != r)
    bm = m & ~rm & ~gm
    hue[rm] = ((g - b)[rm] / d[rm]) % 6
    hue[gm] = (b - r)[gm] / d[gm] + 2
    hue[bm] = (r - g)[bm] / d[bm] + 4
    w = sat * mx
    hh = np.histogram(hue / 6, bins=HUE_BINS, range=(0, 1), weights=w)[0] / rgb[..., 0].size
    lh = np.histogram(lum, bins=LUM_BINS, range=(0, 1))[0] / lum.size
    scal = [
        lum.mean(),
        lum.std(),
        sat.mean(),
        colorful,
        edges,
        (lum < 0.08).mean(),
        (lum > 0.92).mean(),
    ]
    return np.array(scal), hh, lh


def video(d: Path) -> dict[str, np.ndarray] | None:
    grid = json.loads((d / "grid.json").read_text())
    per, feats, small = grid["rows"] * grid["cols"], [], []
    for sheet in sorted(d.glob("[0-9]*.jpg")):
        with Image.open(sheet) as im:
            arr = np.asarray(im.convert("RGB"), dtype=np.float32) / 255
        h, w = arr.shape[0] // grid["rows"], arr.shape[1] // grid["cols"]
        for k in range(per):
            if len(feats) >= grid["tiles"]:
                break
            r, c = divmod(k, grid["cols"])
            t = arr[r * h : (r + 1) * h, c * w : (c + 1) * w]
            feats.append(tile_features(t))
            small.append(t[:: max(h // 9, 1), :: max(w // 16, 1)][:9, :16])
    if len(feats) < 2:
        return None
    s = np.stack([f[0] for f in feats])
    change = np.abs(np.diff(np.stack(small), axis=0)).mean(axis=(1, 2, 3))
    return {
        "mean": s.mean(0),
        "std": s.std(0),
        "hue": np.mean([f[1] for f in feats], axis=0),
        "lum": np.mean([f[2] for f in feats], axis=0),
        "change": np.array([change.mean(), float(grid["interval"]), float(len(feats))]),
    }


def main() -> None:
    dirs = sorted(d for d in SPRITES.iterdir() if (d / "grid.json").exists())
    out: dict[str, list] = {k: [] for k in ("mean", "std", "hue", "lum", "change")}
    ids, t0 = [], time.monotonic()
    for n, d in enumerate(dirs, 1):
        v = video(d)
        if v is None:
            continue
        ids.append(d.name)
        for k in out:
            out[k].append(v[k])
        if n % 50 == 0:
            print(f"[{n}/{len(dirs)}] {time.monotonic() - t0:.0f} s", flush=True)
    np.savez(
        SPRITES / "looks.npz",
        ids=np.array(ids),
        scalars=np.array(SCALARS),
        **{k: np.stack(v) for k, v in out.items()},
    )
    print(f"DONE {len(ids)} videos in {time.monotonic() - t0:.0f} s")


if __name__ == "__main__":
    main()
