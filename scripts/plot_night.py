"""Figures for the patch-grid night (#218, sections 54-58).

uv run --with matplotlib python scripts/plot_night.py ten      # the reference sheet
uv run --with matplotlib python scripts/plot_night.py 54       # section 54's figures
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments" / "patch_grid"))
import night as N
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DPI,
    GOLD,
    PURPLE,
    RED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
)

SERIES = [GOLD, BLUE, CYAN, PURPLE, RED]


def sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=N.ROOT
    ).stdout.strip()


def image(name: str) -> Image.Image:
    return Image.open(N.image_path(name)).convert("RGB")


def show(ax, img: Image.Image, dim: float = 1.0) -> None:
    a = np.asarray(img, dtype=float) / 255.0
    ax.imshow(a * dim, extent=(0, 1, 1, 0), aspect="auto", interpolation="lanczos")
    ax.set_xticks([])
    ax.set_yticks([])


def outline(ax, mask: np.ndarray, color: str, lw: float = 1.6) -> None:
    """The real pixel outline of a region, in image-fraction coordinates."""
    h, w = mask.shape
    ys = (np.arange(h) + 0.5) / h
    xs = (np.arange(w) + 0.5) / w
    ax.contour(xs, ys, mask.astype(float), levels=[0.5], colors=[color], linewidths=lw)


def region_fill(ax, masks: np.ndarray, values: np.ndarray, vmax: float, alpha: float = 0.7) -> None:
    """Paint every region with its value on the shared magma ramp; a pixel in
    several regions takes the largest value, so nested parts stay visible."""
    h, w = masks.shape[1:]
    best = np.zeros((h, w))
    for m, v in zip(masks, values):
        best = np.where(m & (v > best), v, best)
    rgba = saturated_magma()(punch(np.clip(best / max(vmax, 1e-9), 0, 1)))
    rgba[..., 3] = alpha * (best > 0)
    ax.imshow(rgba, extent=(0, 1, 1, 0), aspect="auto", interpolation="nearest")


def grid_map(ax, m: np.ndarray, vmax: float | None = None, alpha: float = 0.66) -> None:
    """A 24 x 24 (or any) per-patch map at its own resolution, on the ramp."""
    m = np.clip(m, 0, None)
    m = m / vmax if vmax else (m - m.min()) / (np.ptp(m) + 1e-12)
    ax.imshow(
        saturated_magma()(punch(np.clip(m, 0, 1))),
        extent=(0, 1, 1, 0),
        aspect="auto",
        alpha=alpha,
        interpolation="nearest",
    )


def mask_colors(n: int) -> np.ndarray:
    return plt.get_cmap("hsv")(np.linspace(0, 1, n, endpoint=False))


def fig_ten(out: Path) -> None:
    """The reference sheet: the ten images, their SAM regions, their queries."""
    qs = N.queries()
    names = list(N.IMAGES)
    data = {n: N.load(n) for n in names}
    counts = [len(data[n]["masks"]) for n in names]
    lost = [int((data[n]["grids"].sum(axis=(1, 2)) == 0).sum()) for n in names]
    fig, top = figure(
        22,
        13.2,
        0,
        "THE NIGHT'S TEN IMAGES",
        "Ten pictures with something to point at, cut into regions by SAM, three questions each",
        f"sam-vit-base, pred_iou 0.80, stability 0.85, area 0.15% to 85% of the frame  |  regions per image {', '.join(map(str, counts))}  |  "
        f"regions too small to own one 16 px patch at half coverage {', '.join(map(str, lost))}  |  under each: small object, frame-filling object, absent object in red  |  {sha()}",
    )
    gs = fig.add_gridspec(
        2, 5, left=0.03, right=0.97, top=top - 0.02, bottom=0.11, wspace=0.06, hspace=0.42
    )
    for k, n in enumerate(names):
        ax = fig.add_subplot(gs[k // 5, k % 5])
        img = image(n)
        show(ax, img, dim=0.75)
        masks = data[n]["masks"]
        cols = mask_colors(len(masks))
        rng = np.random.default_rng(k)
        cols = cols[rng.permutation(len(masks))]
        h, w = masks.shape[1:]
        fill = np.zeros((h, w, 4))
        for m, c in zip(masks, cols):  # large first, so small regions paint on top
            fill[m] = (*c[:3], 0.42)
        ax.imshow(fill, extent=(0, 1, 1, 0), aspect="auto", interpolation="nearest")
        for m, c in zip(masks, cols):
            outline(ax, m, c, lw=0.7)
        panel_title(ax, f"{n}  ({len(masks)} regions)")
        small, big, absent = qs[n]
        ax.text(0.0, -0.035, small, color=TEXT, fontsize=9.5, transform=ax.transAxes, va="top")
        ax.text(0.0, -0.105, big, color=TEXT, fontsize=9.5, transform=ax.transAxes, va="top")
        ax.text(
            0.0,
            -0.175,
            f"{absent}  (absent)",
            color=RED,
            fontsize=9.5,
            transform=ax.transAxes,
            va="top",
        )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print("wrote", out)


def main() -> None:
    what = sys.argv[1] if len(sys.argv) > 1 else "ten"
    if what == "ten":
        d = N.SECTION_ROOT / "54-region-head"
        d.mkdir(exist_ok=True)
        fig_ten(d / "00-the-ten.png")
    else:
        raise SystemExit(f"unknown figure set {what}")


if __name__ == "__main__":
    main()
