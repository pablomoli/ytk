"""Section 64, figure 1: every swept video as a strip of its looks over time.

uv run --with matplotlib python scripts/moments_figure.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from plot_assets import (
    BG,
    GOLD,
    MUTED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    punch,
    ramp_legend,
    saturated_magma,
    style_axes,
    verdict,
)

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "64-moments-and-describer"
mo = np.load(Path.home() / ".ytk" / "sprites" / "moments.npz")
W = 600
vids, stats = list(mo["video"]), mo["video_stats"]
looks, moments = stats[:, 2], stats[:, 3]
order = np.argsort(looks, kind="stable")
share = {
    (v, int(k)): s
    for v, k, s in zip(mo["look_video"], mo["look_id"], mo["look_share"], strict=True)
}
img = np.zeros((len(vids), W))
dur = {}
for v, e in zip(mo["moment_video"], mo["moment_end"], strict=True):
    dur[v] = max(dur.get(v, 0.0), float(e))
row = {vids[i]: r for r, i in enumerate(order)}
for v, k, s, e in zip(
    mo["moment_video"], mo["moment_look"], mo["moment_start"], mo["moment_end"], strict=True
):
    a, b = int(s / dur[v] * W), max(int(e / dur[v] * W), int(s / dur[v] * W) + 1)
    img[row[v], a:b] = share[(v, int(k))]

plt.style.use("dark_background")
one = int((looks == 1).sum())
fig, top = figure(
    17,
    9.2,
    64,
    "MOMENTS  ·  EVERY VIDEO AS A STRIP OF ITS LOOKS",
    "How many different looks does a saved video hold, and when?",
    f"{len(vids)} videos, {int(stats[:, 0].sum()):,} tiles kept, {int(stats[:, 1].sum())} black tiles dropped  ·  a look = tiles of one video within "
    f"cosine distance 0.22 (average link)  ·  {int(looks.sum()):,} looks, {int(moments.sum()):,} moments  ·  median {int(np.median(looks))} looks per video",
)
gs = fig.add_gridspec(
    1, 2, left=0.05, right=0.965, bottom=0.09, top=top - 0.07, wspace=0.13, width_ratios=[2.6, 1]
)
ax = fig.add_subplot(gs[0])
style_axes(ax)
ax.imshow(
    punch(img, 0.55),
    cmap=saturated_magma(),
    vmin=0,
    vmax=1,
    aspect="auto",
    interpolation="nearest",
    extent=(0, 1, len(vids), 0),
)
ax.set_xlabel("position in the video (start to end)")
ax.set_ylabel("videos, fewest looks at the top")
ax.set_yticks([])
panel_title(
    ax,
    "Each row is one video. Bright = the look that fills most of it, dark = a look that appears briefly",
    width=96,
)
ax = fig.add_subplot(gs[1])
style_axes(ax)
ax.plot(
    np.sort(looks),
    np.arange(len(looks)),
    color=GOLD,
    lw=2.2,
    label="one step per video, same order as the strips",
)
ax.set_xscale("log")
ax.invert_yaxis()
ax.set_xlabel("distinct looks in the video (log)")
ax.set_yticks([])
ax.axvline(
    np.median(looks), color=MUTED, lw=1, ls="--", label=f"median, {int(np.median(looks))} looks"
)
ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper right")
ramp_legend(
    ax,
    saturated_magma(),
    "strip color: share of the video a look fills",
    "a brief look",
    "the whole video",
    room=0,
    at=(0.05, 0.07),
)
panel_title(ax, "The same rows, counted", width=34)
verdict(
    fig,
    f"{one} videos hold a single look; the median holds {int(np.median(looks))}; the busiest {int(looks.max())}",
)
frame_panels(fig)
fig.savefig(OUT / "01-moments.png", dpi=300, facecolor=BG)
print("saved", one, int(np.median(looks)), int(looks.max()), np.percentile(looks, [10, 25, 75, 90]))
