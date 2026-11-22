"""Section 63: YouTube saves in the subject space and three look spaces.

Cover (one thumbnail), shown (SigLIP-2 averaged over every sprite tile) and
measured (pixel statistics of the same tiles). Read-only on Chroma; reads
~/.ytk/sprites/looks.npz and ~/.ytk/sprites-emb/<id>.npy.

    uv run --with matplotlib python scripts/three_spaces.py
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from plot_assets import (
    BG,
    CYAN,
    DIM,
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

from ytk import store

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "63-subject-vs-footage"
SPRITES, EMB = Path.home() / ".ytk" / "sprites", Path.home() / ".ytk" / "sprites-emb"
K, SEED, NULLS = 15, 7, 200
rng = np.random.default_rng(SEED)

looks = np.load(SPRITES / "looks.npz")
ids = [i for i in looks["ids"] if (EMB / f"{i}.npy").exists()]
g = store._videos_collection().get(ids=ids, include=["embeddings", "metadatas"])
subj = {i: np.asarray(e, float) for i, e in zip(g["ids"], g["embeddings"], strict=True)}
upl = {i: m.get("uploader", "") for i, m in zip(g["ids"], g["metadatas"], strict=True)}
c = store._visual_collection().get(ids=[f"yt:{i}" for i in ids], include=["embeddings"])
cover = {i[3:]: np.asarray(e, float) for i, e in zip(c["ids"], c["embeddings"], strict=True)}
ids = [i for i in ids if i in subj and i in cover]
row = {i: k for k, i in enumerate(looks["ids"])}
n = len(ids)
up = np.array([upl[i] for i in ids])


def unit(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True)


tile_sets = [np.load(EMB / f"{i}.npy").astype(np.float32) for i in ids]
# How alike a video's own tiles are: 1 means one look held throughout.
steady = np.array([float(np.linalg.norm(t.mean(0))) for t in tile_sets])
r = [row[i] for i in ids]
# Measured look: per-video means and spreads plus the two histograms, each column standardized.
meas = np.hstack(
    [
        looks["mean"][r],
        looks["std"][r],
        looks["hue"][r] * 4,
        looks["lum"][r],
        looks["change"][r][:, :1],
    ]
)
meas = (meas - meas.mean(0)) / (meas.std(0) + 1e-9)
spaces = {
    "subject": unit(np.stack([subj[i] for i in ids])),
    "cover": unit(np.stack([cover[i] for i in ids])),
    "shown": unit(np.stack([t.mean(0) for t in tile_sets])),
    "measured": unit(meas),
}


def knn(x, drop_creator=False):
    s = x @ x.T
    np.fill_diagonal(s, -9)
    if drop_creator:
        s[up[:, None] == up[None, :]] = -9
    return np.argsort(-s, axis=1)[:, :K]


def overlap(a, b):
    return np.array([len(set(x) & set(y)) for x, y in zip(a, b, strict=True)]) / K


nn = {k: knn(v) for k, v in spaces.items()}
nn_x = {k: knn(v, True) for k, v in spaces.items()}
pairs = [
    ("subject", "cover"),
    ("subject", "shown"),
    ("subject", "measured"),
    ("cover", "shown"),
    ("shown", "measured"),
]
res = {}
for a, b in pairs:
    obs = overlap(nn[a], nn[b])
    null = []
    for _ in range(NULLS):
        p = rng.permutation(n)
        inv = np.empty(n, int)
        inv[p] = np.arange(n)
        null.append(overlap(nn[a], inv[nn[b][p]]).mean())
    res[f"{a}|{b}"] = {
        "observed": float(obs.mean()),
        "no_same_creator": float(overlap(nn_x[a], nn_x[b]).mean()),
        "null": [float(x) for x in null],
        "zero_share": float((obs == 0).mean()),
    }
    print(
        f"{a:8s} vs {b:8s} {obs.mean():.3f}  creators dropped {res[f'{a}|{b}']['no_same_creator']:.3f}  null {np.mean(null):.3f}"
    )
same_creator = {k: float((up[v] == up[:, None]).mean()) for k, v in nn.items()}
print(
    "same-creator share of neighbors", same_creator, "steadiness median", float(np.median(steady))
)

import umap

lay = {
    k: umap.UMAP(n_neighbors=K, min_dist=0.25, metric="cosine", random_state=SEED).fit_transform(v)
    for k, v in spaces.items()
}
# One carrier for every map: left-to-right rank in the subject layout.
carrier = np.argsort(np.argsort(lay["subject"][:, 0])) / (n - 1)

json.dump(
    {
        "n": n,
        "k": K,
        "pairs": res,
        "same_creator_neighbor_share": same_creator,
        "steadiness": steady.tolist(),
        "carrier": carrier.tolist(),
        "layouts": {k: v.tolist() for k, v in lay.items()},
    },
    open(OUT / "results.json", "w"),
)
np.savez(
    Path.home() / ".ytk" / "sprites" / "spaces.npz",
    ids=np.array(ids),
    **spaces,
    **{f"nn_{k}": v for k, v in nn.items()},
)

plt.style.use("dark_background")
sm, ss = res["subject|measured"], res["subject|shown"]
fig, top = figure(
    22,
    7.4,
    63,
    "SUBJECT AGAINST FOOTAGE  ·  ONE CORPUS, FOUR SPACES",
    "With the look taken from the footage, does it follow the subject?",
    f"{n} YouTube saves  ·  shown = SigLIP-2 averaged over every sprite tile, measured = pixel statistics of the same tiles  ·  "
    f"every map wears one color: left-to-right position in the subject map  ·  shared {K}-neighbors with subject: "
    f"cover {res['subject|cover']['observed']:.3f}, shown {ss['observed']:.3f}, measured {sm['observed']:.3f}, chance {K / n:.3f}",
)
gs = fig.add_gridspec(1, 4, left=0.035, right=0.745, bottom=0.12, top=top - 0.1, wspace=0.12)
bars = fig.add_gridspec(1, 1, left=0.835, right=0.975, bottom=0.12, top=top - 0.1)
cmap = saturated_magma()
names = {
    "subject": "Subject: what the note says it is about",
    "cover": "Cover: the one thumbnail",
    "shown": "Shown: what is in the footage",
    "measured": "Measured: color, light and texture of the footage",
}
for j, k in enumerate(names):
    ax = fig.add_subplot(gs[j])
    style_axes(ax)
    ax.scatter(
        lay[k][:, 0],
        lay[k][:, 1],
        c=punch(carrier),
        cmap=cmap,
        vmin=0,
        vmax=1,
        s=34,
        linewidths=0,
        alpha=0.92,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    ax.margins(0.04)
    ramp_legend(ax, cmap, "position in the subject map", "left edge", "right edge")
    panel_title(ax, names[k], width=30)
ax = fig.add_subplot(bars[0])
style_axes(ax)
for y, (a, b) in enumerate(pairs[::-1]):
    q = res[f"{a}|{b}"]
    lo, hi = np.percentile(q["null"], [0.5, 99.5])
    ax.barh(y, hi - lo, left=lo, height=0.5, color=DIM)
    ax.plot([np.mean(q["null"]), q["observed"]], [y, y], color=MUTED, lw=0.8)
    ax.scatter([q["no_same_creator"]], [y], s=70, color=CYAN, zorder=3)
    ax.scatter([q["observed"]], [y], s=110, color=GOLD, zorder=4)
ax.set_yticks(range(len(pairs)))
ax.set_yticklabels([f"{a} · {b}" for a, b in pairs[::-1]], color=TEXT, fontsize=9.5)
ax.set_xlim(0, None)
ax.set_ylim(-1.7, len(pairs) - 0.4)
ax.set_xlabel("share of 15 nearest neighbors the two spaces agree on")
ax.scatter([], [], s=110, color=GOLD, label="your saves")
ax.scatter([], [], s=70, color=CYAN, label="same-creator neighbors dropped")
ax.barh([0], [0], color=DIM, label="pairing shuffled")
ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="lower center")
panel_title(ax, "How much each pair of spaces agrees", width=34)
verdict(
    fig,
    f"subject shares {ss['observed'] * 100:.0f}% of neighbors with what is shown and {sm['observed'] * 100:.0f}% with the measured look",
)
frame_panels(fig)
fig.savefig(OUT / "01-four-spaces.png", dpi=300, facecolor=BG)
print("saved", OUT / "01-four-spaces.png")
