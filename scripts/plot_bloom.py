"""Validation checkpoint for bloom (feature C, epic #107).

Not a before/after. The question this answers is whether the numpy pipeline in
labs/bloom_tuning.py — the thing the shipped constants were chosen with — is
actually a faithful model of the shader. If it is, tuning in the notebook is
trustworthy. If it is not, every constant chosen there is suspect.

So: take the un-bloomed scene captured from the running map (`?bloom=off`),
run the notebook's arithmetic over it with the shipped constants, and compare
against what the GPU produced from that same scene.

The numpy side deliberately mirrors the shader's *approximations* — the fixed
9-tap kernel, the same tap spacing, the same downsample — rather than an ideal
Gaussian. Comparing against a better blur would measure the wrong thing.

Usage: uv run --with matplotlib --with numpy --with pillow python scripts/plot_bloom.py
Figures land in docs/assets/05-bloom/.
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import BG as FIG_BG
from plot_assets import (
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    RED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "05-bloom"
RAW = OUTDIR / "scene-raw.png"
BLOOMED = OUTDIR / "scene-bloomed.png"

# Exactly what mapRenderer.ts ships.
THRESHOLD, KNEE = 0.26, 0.14
SIGMA, PASSES, DOWNSAMPLE, INTENSITY = 9.5, 2, 2, 1.45

# The shader's kernel, verbatim.
TAPS = np.array(
    [0.0162, 0.0540, 0.1216, 0.1946, 0.2270, 0.1946, 0.1216, 0.0540, 0.0162], dtype=np.float32
)


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=FIG_BG)
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def legend(ax, **kw):
    return ax.legend(fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT, **kw)


def load(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def box_down(img, factor):
    h = (img.shape[0] // factor) * factor
    w = (img.shape[1] // factor) * factor
    return img[:h, :w].reshape(h // factor, factor, w // factor, factor, 3).mean((1, 3))


def upsample_to(img, shape):
    """Bilinear, because the bloom textures are LINEAR-filtered on the GPU."""
    yi = np.linspace(0, img.shape[0] - 1, shape[0])
    xi = np.linspace(0, img.shape[1] - 1, shape[1])
    y0 = np.floor(yi).astype(int)
    y1 = np.minimum(y0 + 1, img.shape[0] - 1)
    x0 = np.floor(xi).astype(int)
    x1 = np.minimum(x0 + 1, img.shape[1] - 1)
    wy = (yi - y0)[:, None, None]
    wx = (xi - x0)[None, :, None]
    top = img[y0][:, x0] * (1 - wx) + img[y0][:, x1] * wx
    bot = img[y1][:, x0] * (1 - wx) + img[y1][:, x1] * wx
    return top * (1 - wy) + bot * wy


def tap_blur(img, step_px, axis):
    """The shader's nine taps at a fixed spacing, sampled with clamping."""
    out = np.zeros_like(img)
    n = img.shape[axis]
    for i, w in enumerate(TAPS):
        shift = round((i - 4) * step_px)
        idx = np.clip(np.arange(n) + shift, 0, n - 1)
        out += w * (img[idx] if axis == 0 else img[:, idx])
    return out


def predict(scene: np.ndarray) -> np.ndarray:
    y = scene @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    t = np.clip((y - (THRESHOLD - KNEE)) / (2 * KNEE), 0, 1)
    bright = scene * (t * t * (3 - 2 * t))[..., None]
    small = box_down(bright, DOWNSAMPLE)
    spread = SIGMA / DOWNSAMPLE / 3
    for _ in range(PASSES):
        small = tap_blur(small, spread, axis=1)
        small = tap_blur(small, spread, axis=0)
    return np.clip(scene + INTENSITY * upsample_to(small, scene.shape[:2]), 0, 1)


def main():
    if not RAW.exists() or not BLOOMED.exists():
        raise SystemExit(f"missing captures — run scripts/shoot_bloom_pair.py first ({RAW.parent})")
    scene = load(RAW)
    gpu = load(BLOOMED)
    model = predict(scene)

    err = np.abs(model - gpu).mean(axis=2)
    added_gpu = np.clip(gpu - scene, 0, 1).mean() * 100
    added_model = np.clip(model - scene, 0, 1).mean() * 100

    fig, top = figure(
        16.0,
        7.4,
        1,
        "does the notebook model the shader?",
        "The numpy pipeline the constants were chosen with, against the GPU",
        f"threshold {THRESHOLD} · knee {KNEE} · σ {SIGMA} · {PASSES} passes · "
        f"÷{DOWNSAMPLE} · intensity {INTENSITY}  ·  mean |error| {err.mean() * 100:.2f}%",
    )
    gs = fig.add_gridspec(
        1, 4, left=0.015, right=1 - MARGIN - 0.005, top=top, bottom=0.11, wspace=0.045
    )

    for k, (img, title) in enumerate(
        (
            (scene, "scene, bloom off (?bloom=off)"),
            (model, "numpy prediction"),
            (gpu, "what the GPU drew"),
        )
    ):
        ax = fig.add_subplot(gs[k])
        style_axes(ax)
        ax.set_facecolor("#000000")
        panel_title(ax, title)
        ax.imshow(np.clip(img, 0, 1))
        ax.set_xticks([])
        ax.set_yticks([])

    ax = fig.add_subplot(gs[3])
    style_axes(ax)
    panel_title(ax, "|prediction − GPU|, per pixel")
    im = ax.imshow(err, cmap="magma", vmin=0, vmax=max(err.max(), 1e-6))
    ax.set_xticks([])
    ax.set_yticks([])
    cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
    cb.ax.tick_params(colors=MUTED, labelsize=TICK_SIZE)
    cb.set_label("absolute error", color=MUTED, fontsize=TICK_SIZE)

    fig.text(
        MARGIN,
        0.045,
        f"light added over the scene — GPU {added_gpu:.2f}%, prediction {added_model:.2f}%   ·   "
        f"p99 error {np.percentile(err, 99) * 100:.2f}%, max {err.max() * 100:.2f}%",
        color=MUTED,
        fontsize=TICK_SIZE,
        va="baseline",
    )
    save(fig, "01-model-vs-gpu.png")

    fig, top = figure(
        12.0,
        6.0,
        2,
        "where the model and the GPU disagree",
        "Error against scene brightness",
        "if the notebook is faithful the error should be small everywhere and "
        "unstructured — error that tracks brightness means the bright-pass differs",
    )
    gs = fig.add_gridspec(1, 1, left=0.085, right=1 - MARGIN - 0.02, top=top, bottom=0.14)
    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "per-pixel error vs luminance")
    y = (scene @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)).ravel()
    e = err.ravel()
    sel = np.random.default_rng(7).choice(len(y), size=min(40000, len(y)), replace=False)
    ax.scatter(y[sel], e[sel] * 100, s=1.2, color=GOLD, alpha=0.35, linewidths=0)
    ax.axvline(THRESHOLD, color=RED, ls="--", lw=1.5, label=f"bright-pass threshold ({THRESHOLD})")
    ax.set_xlabel("scene luminance")
    ax.set_ylabel("absolute error / %")
    legend(ax, loc="upper right")
    save(fig, "02-error-structure.png")

    print()
    print(f"  mean |error|     {err.mean() * 100:.3f}%")
    print(f"  p99 |error|      {np.percentile(err, 99) * 100:.3f}%")
    print(f"  max |error|      {err.max() * 100:.3f}%")
    print(f"  light added      GPU {added_gpu:.3f}%  model {added_model:.3f}%")


if __name__ == "__main__":
    main()
