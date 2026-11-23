"""Section 71, figure 1: what "maps moving together" is, on two frames of the test set.

For each frame: the frame, its 22 maps, and the correlation of every pair of maps
across all of its pixels. Runs the same code as the CUDA pass, on these two frames.

    uv run --with matplotlib python scripts/taste_maps_figure.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import taste_maps_cuda as tm
from PIL import Image
from plot_assets import BG, MUTED, TEXT, figure, frame_panels, saturated_magma, verdict

T = Path.home() / ".ytk" / "taste-test"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "71-maps-moving-together"
order = json.loads((T / "order.json").read_text())
bank = np.load(T / "bank.npz")
score = bank["dark_ground"][:, 2]
# Two frames far apart on the owner's own sentence: the most "colors over black", and a middling one.
a = int(np.argmax(score))
b = int(np.argsort(score)[len(score) // 2])
C = len(tm.NAMES)
cmap = saturated_magma()
plt.style.use("dark_background")
fig, top = figure(
    21,
    12.6,
    71,
    "MAPS MOVING TOGETHER  ·  NOTHING AVERAGED AWAY",
    "What is kept when every measurement stays a map of the frame?",
    f"two frames of the test set  ·  {C} maps per frame, one value per pixel at the frame's own size  ·  "
    f"right: the correlation of every pair of maps across all pixels, {C * (C - 1) // 2} pairs, the part that does not care where things are",
)
gs = fig.add_gridspec(
    2,
    3,
    left=0.03,
    right=0.975,
    bottom=0.07,
    top=top - 0.05,
    wspace=0.08,
    hspace=0.16,
    width_ratios=[1, 2.3, 1.25],
)
mats = []
for r, i in enumerate((a, b)):
    path = T / "flat" / order[i]["name"]
    with Image.open(path) as im:
        rgb_np = np.asarray(im.convert("RGB")).copy()
    maps = tm.channels(torch.from_numpy(rgb_np).to(tm.DEV).permute(2, 0, 1).float() / 255)
    _, _, c = tm.together(maps)
    M = np.zeros((C, C))
    iu = np.triu_indices(C, 1)
    M[iu] = c.cpu().numpy()
    M = M + M.T
    mats.append(M)
    ax = fig.add_subplot(gs[r, 0])
    ax.imshow(rgb_np)
    ax.set_axis_off()
    ax.set_title(
        f"the frame, {rgb_np.shape[1]} x {rgb_np.shape[0]}  ·  dark x color = {score[i]:.2f}",
        color=TEXT,
        fontsize=10,
        pad=8,
    )
    sub = gs[r, 1].subgridspec(4, 6, wspace=0.04, hspace=0.22)
    small = (
        torch.nn.functional.adaptive_avg_pool2d(
            maps[None], (180, round(180 * rgb_np.shape[1] / rgb_np.shape[0]))
        )[0]
        .cpu()
        .numpy()
    )
    for k in range(C):
        axm = fig.add_subplot(sub[k // 6, k % 6])
        m = small[k]
        lo, hi = np.percentile(m, [1, 99])
        axm.imshow((m - lo) / max(hi - lo, 1e-6), cmap=cmap, vmin=0, vmax=1)
        axm.set_xticks([])
        axm.set_yticks([])
        axm.set_title(tm.NAMES[k], color=TEXT, fontsize=7.5, pad=2)
        axm._is_colorbar = True
    ax = fig.add_subplot(gs[r, 2])
    ax.imshow((M + 1) / 2, cmap=cmap, vmin=0, vmax=1)
    ax.set_xticks([])
    ax.set_yticks(range(C))
    ax.set_yticklabels(tm.NAMES, color=TEXT, fontsize=7)
    ax.set_title("how its maps move together", color=TEXT, fontsize=10, pad=8)
key = fig.add_axes((0.72, 0.042, 0.18, 0.011))
key.imshow(np.linspace(0, 1, 256)[None, :], cmap=cmap, aspect="auto")
key.set_xticks([])
key.set_yticks([])
key._is_colorbar = True
key.set_title("matrix color: correlation of two maps", color=TEXT, fontsize=9, loc="left", pad=4)
fig.text(0.72, 0.024, "-1, opposite", color=MUTED, fontsize=8.5)
fig.text(0.81, 0.024, "0", color=MUTED, fontsize=8.5, ha="center")
fig.text(0.90, 0.024, "+1, together", color=MUTED, fontsize=8.5, ha="right")
fig.text(
    0.03,
    0.02,
    "map color: low to high within each map (1st to 99th percentile), same ramp as the key",
    color=MUTED,
    fontsize=9,
)
diff = np.abs(mats[0] - mats[1])
i, j = np.unravel_index(np.argmax(diff), diff.shape)
verdict(
    fig,
    f"the pair that differs most between the two frames: {tm.NAMES[i]} with {tm.NAMES[j]}, {mats[0][i, j]:+.2f} against {mats[1][i, j]:+.2f}",
)
frame_panels(fig)
fig.savefig(OUT / "01-what-it-is.png", dpi=250, facecolor=BG)
print("saved", order[a]["name"], order[b]["name"], tm.NAMES[i], tm.NAMES[j])
