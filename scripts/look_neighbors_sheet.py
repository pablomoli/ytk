"""Eye check for section 63: a seed video, its nearest by measured look, its nearest by what is shown.

Reads ~/.ytk/sprites/spaces.npz (written by three_spaces.py). The sheet shows
saved videos' frames and titles; it is kept in the section folder on the owner's word.

    uv run --with matplotlib python scripts/look_neighbors_sheet.py "usman" "svd visualized" ...
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
from plot_assets import BG, CYAN, GOLD, MUTED, TEXT

from ytk import store

SPRITES = Path.home() / ".ytk" / "sprites"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "63-subject-vs-footage"
TILES, NEAR = 10, 3

sp = np.load(SPRITES / "spaces.npz")
ids = list(sp["ids"])
g = store._videos_collection().get(ids=ids, include=["metadatas"])
title = {i: m.get("title", "") for i, m in zip(g["ids"], g["metadatas"], strict=True)}


def strip(vid: str) -> np.ndarray:
    grid = json.loads((SPRITES / vid / "grid.json").read_text())
    per = grid["rows"] * grid["cols"]
    picks = np.linspace(0, grid["tiles"] - 1, TILES).round().astype(int)
    out = []
    for i in picks:
        frag, k = divmod(int(i), per)
        r, c = divmod(k, grid["cols"])
        with Image.open(SPRITES / vid / f"{frag:03d}.jpg") as im:
            w, h = im.width // grid["cols"], im.height // grid["rows"]
            out.append(
                np.asarray(
                    im.convert("RGB")
                    .crop((c * w, r * h, (c + 1) * w, (r + 1) * h))
                    .resize((320, 180))
                )
            )
    return np.concatenate(out, axis=1)


seeds = []
for q in sys.argv[1:]:
    hit = [k for k, i in enumerate(ids) if q.lower() in title[i].lower()]
    if hit:
        seeds.append(hit[0])
rows = []
for s in seeds:
    rows.append((s, "seed", GOLD))
    rows += [(int(j), "nearest by measured look", CYAN) for j in sp["nn_measured"][s][:NEAR]]
    rows += [(int(j), "nearest by what is shown", MUTED) for j in sp["nn_shown"][s][:NEAR]]
fig, axes = plt.subplots(len(rows), 1, figsize=(16, 1.12 * len(rows)), facecolor=BG)
for ax, (k, kind, color) in zip(axes, rows, strict=True):
    ax.imshow(strip(ids[k]))
    ax.set_axis_off()
    ax.set_title(
        f"{kind}  ·  {title[ids[k]][:110]}",
        color=color if kind == "seed" else TEXT,
        fontsize=8.5,
        loc="left",
        pad=2,
    )
    ax.plot([0, 0], [0, 180], color=color, lw=6, solid_capstyle="butt")
from matplotlib.lines import Line2D

keys = [
    ("seed video", GOLD),
    (f"its {NEAR} nearest by measured look (pixel statistics)", CYAN),
    (f"its {NEAR} nearest by what is shown (image model)", MUTED),
]
fig.legend(
    handles=[Line2D([0], [0], color=c, lw=7, label=t) for t, c in keys],
    loc="upper left",
    bbox_to_anchor=(0.01, 0.999),
    ncol=3,
    frameon=False,
    labelcolor=TEXT,
    fontsize=10,
)
fig.subplots_adjust(left=0.01, right=0.99, top=0.972, bottom=0.005, hspace=0.42)
OUT.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT / "02-look-neighbors.png", dpi=200, facecolor=BG)
print("saved", OUT / "02-look-neighbors.png", [title[ids[s]][:50] for s in seeds])
