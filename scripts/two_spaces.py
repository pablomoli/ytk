"""Section 62: the same saves in the subject space and the cover space.

Read-only on Chroma. uv run --with matplotlib python scripts/two_spaces.py
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
    DIM,
    GOLD,
    MUTED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
    style_axes,
    verdict,
)

from ytk import store

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "62-subject-vs-cover"
K, SEED, NULLS = 15, 7, 200
rng = np.random.default_rng(SEED)

v = store._visual_collection().get(include=["embeddings", "metadatas"])
vids = store._videos_collection()
mems = store._memories_collection()
rows = []
for iid, emb, md in zip(v["ids"], v["embeddings"], v["metadatas"]):
    kind = iid.split(":")[0]
    if kind == "yt":
        tid, col = iid[3:], vids
    else:
        np_ = md.get("note_path", "")
        if "second-brain/" not in np_:
            continue
        tid = "note_" + np_.split("second-brain/")[1].removesuffix(".md").replace("/", "_")
        col = mems
    rows.append((iid, kind, md.get("title", ""), np.asarray(emb, float), tid, col))


def fetch(col, ids):
    out = {}
    for i in range(0, len(ids), 200):
        g = col.get(ids=ids[i : i + 200], include=["embeddings"])
        out.update({k: np.asarray(e, float) for k, e in zip(g["ids"], g["embeddings"])})
    return out


tv = fetch(vids, [r[4] for r in rows if r[5] is vids]) | fetch(
    mems, [r[4] for r in rows if r[5] is mems]
)
rows = [r for r in rows if r[4] in tv]
ids = [r[0] for r in rows]
kind = np.array([r[1] for r in rows])
titles = [r[2] for r in rows]
L = np.stack([r[3] for r in rows])
M = np.stack([tv[r[4]] for r in rows])
L /= np.linalg.norm(L, axis=1, keepdims=True)
M /= np.linalg.norm(M, axis=1, keepdims=True)
n = len(rows)
print("paired", n, "of", len(v["ids"]), {k: int((kind == k).sum()) for k in set(kind)})


def knn(X):
    s = X @ X.T
    np.fill_diagonal(s, -9)
    return np.argsort(-s, axis=1)[:, :K]


nm, nl = knn(M), knn(L)


def overlap(a, b):
    return np.array([len(set(x) & set(y)) for x, y in zip(a, b)]) / K


obs = overlap(nm, nl)


# Null: re-pair looks with meanings inside each source, so thumbnail-vs-reel style cannot fake agreement.
def shuffled_within():
    p = np.arange(n)
    for k in set(kind):
        idx = np.where(kind == k)[0]
        p[idx] = rng.permutation(idx)
    return p


def null_mean(p):
    inv = np.empty(n, int)
    inv[p] = np.arange(n)
    return overlap(nm, inv[nl[p]]).mean()  # item i wears item p[i]'s look


null_w = np.array([null_mean(shuffled_within()) for _ in range(NULLS)])
null_a = np.array([null_mean(rng.permutation(n)) for _ in range(NULLS)])
same_src = (kind[nl] == kind[:, None]).mean()
same_src_m = (kind[nm] == kind[:, None]).mean()
chance_src = sum(((kind == k).mean()) ** 2 for k in set(kind))


# within-source observed: neighbors restricted to the item's own source
def knn_within(X):
    s = X @ X.T
    np.fill_diagonal(s, -9)
    s[kind[:, None] != kind[None, :]] = -9
    return np.argsort(-s, axis=1)[:, :K]


obs_w = overlap(knn_within(M), knn_within(L))
print(
    f"overlap mean {obs.mean():.3f}  null within-source {null_w.mean():.3f}±{null_w.std():.3f}  null any {null_a.mean():.3f}"
)
print(
    f"within-source-only overlap {obs_w.mean():.3f}; chance for it ~",
    {k: round(K / max((kind == k).sum() - 1, 1), 3) for k in set(kind)},
)
print(
    f"look neighbors same source {same_src:.2f}, meaning neighbors same source {same_src_m:.2f}, chance {chance_src:.2f}"
)

import umap

em = umap.UMAP(n_neighbors=K, min_dist=0.25, metric="cosine", random_state=SEED).fit_transform(M)
el = umap.UMAP(n_neighbors=K, min_dist=0.25, metric="cosine", random_state=SEED).fit_transform(L)

# Creator check on YouTube: is the agreement one channel reusing a thumbnail template?
yi = np.where(kind == "yt")[0]
g = vids.get(ids=[ids[i][3:] for i in yi], include=["metadatas"])
upl = dict(zip(g["ids"], [m.get("uploader", "") for m in g["metadatas"]]))
up = np.array([upl.get(ids[i][3:], "") for i in yi])


def yt_overlap(drop_same_creator):
    out = []
    for X in (M[yi], L[yi]):
        s = X @ X.T
        np.fill_diagonal(s, -9)
        if drop_same_creator:
            s[up[:, None] == up[None, :]] = -9
        out.append(np.argsort(-s, axis=1)[:, :K])
    return float(overlap(*out).mean())


yt_all, yt_cross = yt_overlap(False), yt_overlap(True)
print(
    f"youtube overlap {yt_all:.3f}, same-creator neighbors dropped {yt_cross:.3f}, chance {K / len(yi):.3f}"
)

# Sidecar holds numbers only: no ids, titles or URLs leave the store.
json.dump(
    {
        "n": n,
        "k": K,
        "by_source": {k: int((kind == k).sum()) for k in sorted(set(kind))},
        "overlap_mean": float(obs.mean()),
        "overlap_zero_share": float((obs == 0).mean()),
        "null_within_source": null_w.tolist(),
        "null_any": null_a.tolist(),
        "look_neighbors_same_source": float(same_src),
        "subject_neighbors_same_source": float(same_src_m),
        "same_source_chance": float(chance_src),
        "youtube_overlap": yt_all,
        "youtube_overlap_no_same_creator": yt_cross,
        "youtube_chance": K / len(yi),
        "overlap": obs.tolist(),
        "subject_xy": em.tolist(),
        "cover_xy": el.tolist(),
    },
    open(OUT / "results.json", "w"),
)
print("zero overlap share", float((obs == 0).mean()))

plt.style.use("dark_background")
fig, top_y = figure(
    17,
    7.6,
    62,
    "SUBJECT AGAINST COVER  ·  TWO SPACES, ONE CORPUS",
    "Do saves that are alike in subject also have alike covers?",
    f"{n} saves with both a note vector (Qwen3) and a cover vector (SigLIP-2)  ·  brightness = share of an item's {K} nearest "
    f"subject neighbors that are also among its {K} nearest look neighbors  ·  mean {obs.mean():.3f}, "
    f"shuffled within source {null_w.mean():.3f}  ·  the look here is one cover image per save, not the video",
)
gs = fig.add_gridspec(
    1,
    3,
    left=0.05,
    right=0.965,
    bottom=0.11,
    top=top_y - 0.09,
    wspace=0.16,
    width_ratios=[1, 1, 0.72],
)
cmap = saturated_magma()
c = punch(obs / max(obs.max(), 1e-9))
order = np.argsort(obs)
for j, (E, name) in enumerate(
    [
        (em, "The subject space: neighbors here are about the same thing"),
        (el, "The cover space: neighbors here have similar covers"),
    ]
):
    ax = fig.add_subplot(gs[j])
    style_axes(ax)
    ax.scatter(
        E[order, 0],
        E[order, 1],
        c=c[order],
        cmap=cmap,
        vmin=0,
        vmax=1,
        s=26 + 90 * c[order],
        linewidths=0,
        alpha=0.92,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    ax.margins(0.03)
    panel_title(ax, name)
ax = fig.add_subplot(gs[2])
style_axes(ax)
bins = np.linspace(0, max(obs.max(), 0.4) + 1 / K, round(max(obs.max(), 0.4) * K) + 2) - 0.5 / K
perm = shuffled_within()
inv = np.empty(n, int)
inv[perm] = np.arange(n)
one_null = overlap(nm, inv[nl[perm]])
ax.hist(one_null, bins=bins, color=DIM, label="covers re-dealt within each source (one shuffle)")
ax.hist(obs, bins=bins, color=GOLD, histtype="step", linewidth=2.2, label="your saves")
ax.axvline(obs.mean(), color=GOLD, lw=1.2, ls="--")
ax.axvline(null_w.mean(), color=MUTED, lw=1.2, ls="--")
ax.set_yscale("log")
ax.set_xlabel("share of subject neighbors that are also cover neighbors")
ax.set_ylabel("saves (log)")
ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="upper right")
panel_title(ax, "Against chance: the same saves with their covers shuffled", width=40)
verdict(
    fig,
    f"subject and cover share {obs.mean() / max(null_w.mean(), 1e-9):.1f}x more neighbors than chance; {100 * (obs == 0).mean():.0f}% of saves share none",
)
frame_panels(fig)
fig.savefig(OUT / "01-two-spaces.png", dpi=300, facecolor=BG)
print("saved", OUT / "01-two-spaces.png")
