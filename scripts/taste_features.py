"""Pixel and composition readings for the taste test frames, and the figure of the set itself.

No model. Each frame is read at 768 px on its long side.
  global   light, contrast, saturation, colorfulness, edges, dark and bright share, hue and light histograms
  grid     the same four numbers per cell of a 4x4 grid: where things are
  comp     the colored region: coverage, how spread it is at three grid sizes, how many pieces,
           how much of it is thin stroke, how aligned its edges are, where its center sits

    uv run --with matplotlib python scripts/taste_features.py
"""

import json
import sys
from pathlib import Path

import numpy as np
from matplotlib.colors import rgb_to_hsv
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from plot_assets import (
    BG,
    CYAN,
    GOLD,
    MUTED,
    PURPLE,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

T = Path.home() / ".ytk" / "taste-test"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "69-taste-test-set"
COMP = [
    "coverage",
    "spread_2",
    "spread_4",
    "spread_8",
    "pieces",
    "largest_piece",
    "thin_stroke",
    "edge_alignment",
    "center_x",
    "center_y",
    "dark",
    "color",
]


def read(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((768, 768))
        return np.asarray(im, np.float32) / 255


def spread(mask: np.ndarray, n: int) -> float:
    """Entropy of where the colored pixels fall on an n x n grid, 0 = one cell, 1 = even."""
    h, w = mask.shape
    cells = np.array(
        [
            mask[i * h // n : (i + 1) * h // n, j * w // n : (j + 1) * w // n].mean()
            for i in range(n)
            for j in range(n)
        ]
    )
    if cells.sum() <= 0:
        return 0.0
    q = cells / cells.sum()
    return float(-(q[q > 0] * np.log(q[q > 0])).sum() / np.log(n * n))


def features(a: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    hsv = rgb_to_hsv(a)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    gy, gx = np.gradient(lum)
    edge = np.hypot(gx, gy)
    rg, yb = a[..., 0] - a[..., 1], 0.5 * (a[..., 0] + a[..., 1]) - a[..., 2]
    dark = lum < 0.08
    glob = np.concatenate(
        [
            [
                lum.mean(),
                lum.std(),
                sat.mean(),
                np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean()),
                edge.mean(),
                dark.mean(),
                (lum > 0.92).mean(),
            ],
            np.histogram(hue, bins=12, range=(0, 1), weights=sat * val)[0] / lum.size * 4,
            np.histogram(lum, bins=8, range=(0, 1))[0] / lum.size,
        ]
    )
    colored = (sat * val > 0.25) & ~dark
    h, w = lum.shape
    grid = np.array(
        [
            [
                f[i * h // 4 : (i + 1) * h // 4, j * w // 4 : (j + 1) * w // 4].mean()
                for f in (lum, sat, edge * 8, colored.astype(np.float32))
            ]
            for i in range(4)
            for j in range(4)
        ]
    ).ravel()
    labels, n = ndimage.label(ndimage.binary_opening(colored, iterations=1))
    sizes = np.bincount(labels.ravel())[1:] if n else np.array([0])
    eroded = ndimage.binary_erosion(colored, iterations=2)
    # Edge alignment: how much nearby edges agree in direction (structure tensor coherence), on strong edges.
    jxx, jyy, jxy = (ndimage.uniform_filter(x, 9) for x in (gx * gx, gy * gy, gx * gy))
    coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy**2) / (jxx + jyy + 1e-8)
    strong = edge > np.percentile(edge, 90)
    ys, xs = np.nonzero(colored)
    comp = np.array(
        [
            colored.mean(),
            spread(colored, 2),
            spread(colored, 4),
            spread(colored, 8),
            np.log1p((sizes > colored.size * 0.0005).sum()),
            sizes.max() / max(colored.sum(), 1),
            1 - eroded.sum() / max(colored.sum(), 1),
            float(coh[strong].mean()) if strong.any() else 0.0,
            xs.mean() / w if len(xs) else 0.5,
            ys.mean() / h if len(ys) else 0.5,
            dark.mean(),
            float((sat * val)[~dark].mean()) if (~dark).any() else 0.0,
        ]
    )
    return glob.astype(np.float32), grid.astype(np.float32), comp.astype(np.float32)


order = json.loads((T / "order.json").read_text())
out = [features(read(T / "flat" / o["name"])) for o in order]
np.savez(
    T / "features.npz",
    **{k: np.stack([x[i] for x in out]) for i, k in enumerate(("global", "grid", "comp"))},
    comp_names=np.array(COMP),
)
print("features for", len(order), "frames")

# Figure: the set itself.
items = json.loads((T / "frames.json").read_text())
kinds = [("youtube", GOLD), ("reel", CYAN), ("carousel", PURPLE), ("tiktok", MUTED)]
plt.style.use("dark_background")
vids = {k: i for k, i in items.items() if "seconds" in i}
shots = {
    kind: np.concatenate(
        [np.diff([0, *i["cuts"], i["seconds"]]) for i in vids.values() if i["kind"] == kind]
    )
    for kind in ("youtube", "reel", "tiktok")
}
fig, top = figure(
    19,
    10,
    69,
    "THE TASTE TEST SET  ·  50 SAVED ITEMS AT NATIVE RESOLUTION",
    "What is in the test set, and how is each item cut?",
    f"10 YouTube videos, 20 reels, 10 carousels, 10 TikToks, drawn at random from the owner's saves  ·  {len(order)} frames kept: one from the middle of each of the twelve longest shots, "
    f"every slide of a carousel  ·  median shot: YouTube {np.median(shots['youtube']):.1f} s, reels {np.median(shots['reel']):.1f} s, TikToks {np.median(shots['tiktok']):.1f} s",
)
gs = fig.add_gridspec(
    1, 2, left=0.045, right=0.975, bottom=0.08, top=top - 0.06, wspace=0.12, width_ratios=[2.2, 1]
)
ax = fig.add_subplot(gs[0])
style_axes(ax)
y = 0
ticks = []
for kind, col in kinds:
    for it in items.values():
        if it["kind"] != kind:
            continue
        if "seconds" in it:
            dur = max(it["seconds"], 1e-6)
            ax.plot([0, 1], [y, y], color="#1c1c22", lw=5, solid_capstyle="butt")
            ax.vlines(np.array(it["cuts"]) / dur, y - 0.38, y + 0.38, color=col, lw=0.7, alpha=0.9)
            ax.scatter(
                [f["t"] / dur for f in it["frames"]],
                [y] * len(it["frames"]),
                s=16,
                color=TEXT,
                zorder=4,
                linewidths=0,
            )
        else:
            n = len(it["frames"])
            ax.scatter(
                (np.arange(n) + 0.5) / max(n, 1), [y] * n, s=46, marker="s", color=col, linewidths=0
            )
        y += 1
    ticks.append((y - sum(1 for i in items.values() if i["kind"] == kind) / 2 - 0.5, kind))
    y += 1.2
ax.set_ylim(y, -1)
ax.set_xlim(-0.01, 1.01)
ax.set_yticks([t for t, _ in ticks])
ax.set_yticklabels([k for _, k in ticks], color=TEXT, fontsize=10)
ax.set_xlabel("position in the item (start to end; a carousel's slides in order)")
ax.plot([], [], color=GOLD, lw=1.2, label="a cut (colored by kind)")
ax.scatter([], [], s=16, color=TEXT, label="a frame kept at native resolution")
ax.scatter([], [], s=46, marker="s", color=PURPLE, label="a carousel slide")
leg = ax.legend(
    frameon=False,
    fontsize=9,
    labelcolor=TEXT,
    loc="lower center",
    ncol=3,
    bbox_to_anchor=(0.5, 1.0),
    title="Each row is one item",
    title_fontsize=10.5,
)
leg.get_title().set_color(TEXT)
ax = fig.add_subplot(gs[1])
style_axes(ax)
bins = np.geomspace(0.2, 2000, 40)
for kind, col in (("youtube", GOLD), ("reel", CYAN), ("tiktok", MUTED)):
    ax.hist(
        shots[kind],
        bins=bins,
        histtype="step",
        lw=2,
        color=col,
        label=f"{kind}: {len(shots[kind])} shots, median {np.median(shots[kind]):.1f} s",
    )
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("how long a shot holds, seconds (log)")
ax.set_ylabel("shots (log)")
ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper right")
panel_title(ax, "Shot lengths by kind", width=34)
nocut = sum(1 for i in vids.values() if len(i["cuts"]) == 0)
verdict(
    fig,
    f"{nocut} of {len(vids)} videos never cut; the most-cut one has {max(len(i['cuts']) for i in vids.values())} cuts",
)
frame_panels(fig)
fig.savefig(OUT / "01-the-set.png", dpi=300, facecolor=BG)
json.dump(
    {
        "frames": len(order),
        "videos": len(vids),
        "videos_without_a_cut": nocut,
        "median_shot_s": {k: float(np.median(v)) for k, v in shots.items()},
        "cuts_per_item": {
            k: sorted(len(i["cuts"]) for i in vids.values() if i["kind"] == k) for k in shots
        },
    },
    open(OUT / "results.json", "w"),
    indent=1,
)
print("saved", nocut, {k: round(float(np.median(v)), 1) for k, v in shots.items()})
