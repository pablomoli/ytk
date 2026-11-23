"""Section 72, part 3: what a direction in the co-movement space looks like.

Directions that depend on few pairs of maps (sparse PCA) are found in the 231-pair space.
For each, real frames from its low end, its middle and its high end are shown beside the
pairs that drive it. No direction is named; the frames say what it is.

    uv run --with matplotlib python scripts/taste_directions.py [family key in together.npz]
"""

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA, SparsePCA

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import taste_maps_cuda as tm
from PIL import Image
from plot_assets import BG, CYAN, GOLD, MUTED, TEXT, figure, frame_panels, verdict

T = Path.home() / ".ytk" / "taste-test"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "72-look-or-file"
KEY = sys.argv[1] if len(sys.argv) > 1 else "together_scale_1"
SRC = (
    T / "s72" / "orig" / "together.npz"
    if (T / "s72" / "orig" / "together.npz").exists()
    else T / "together.npz"
)
N_DIR, PER_END = 5, 4
PROBES = {
    "type card": "youtube-04_05.jpg",
    "wireframe": "reel-29_01.jpg",
    "render": "carousel-38_00.jpg",
}
order = json.loads((T / "order.json").read_text())
item = np.array([o["item"] for o in order])
x = np.load(SRC)[KEY][:, :231].astype(np.float64)
C = len(tm.NAMES)
iu = np.triu_indices(C, 1)
pair = [f"{tm.NAMES[a]} with {tm.NAMES[b]}" for a, b in zip(*iu, strict=True)]
CHROMA = {"saturation", "chroma", "red-green", "yellow-blue", "hue cos", "hue sin", "colored"}
PHOTO = {"light", "brightness", "dark ground"}
kind = lambda n: "c" if n in CHROMA else ("p" if n in PHOTO else "s")
pair_kind = [
    "".join(sorted(kind(tm.NAMES[a]) + kind(tm.NAMES[b]))) for a, b in zip(*iu, strict=True)
]
BLOCKS = {
    "all": (None, "03-directions.png", "all 231 pairs"),
    "light-structure": (
        {"ps"},
        "04-directions-light-with-structure.png",
        "light with structure pairs only",
    ),
    "structure": (
        {"ss", "cs"},
        "05-directions-structure.png",
        "structure with structure, and color with structure",
    ),
}
BLOCK = sys.argv[2] if len(sys.argv) > 2 else "all"
in_block = np.array([BLOCKS[BLOCK][0] is None or k in BLOCKS[BLOCK][0] for k in pair_kind])
keep = (np.nanstd(x, 0) > 1e-6) & in_block
mu = np.nanmean(x, 0)
z = np.nan_to_num(x - mu)[
    :, keep
]  # correlations are already on one scale; a missing pair sits at its mean
pca = PCA(n_components=10).fit(z)
sp = SparsePCA(n_components=N_DIR, alpha=2.0, random_state=0, max_iter=400).fit(z)
comp = sp.components_
proj = z @ comp.T
names_kept = [p for p, k in zip(pair, keep, strict=True) if k]
res = {
    "family": KEY,
    "frames": len(x),
    "pairs_used": int(keep.sum()),
    "pca_variance_first_5": [float(v) for v in pca.explained_variance_ratio_[:5]],
    "directions": [],
}


def spread_pick(idx: np.ndarray, k: int) -> list[int]:
    """The first k frames of idx that come from different items."""
    out, seen = [], set()
    for i in idx:
        if item[i] not in seen:
            out.append(int(i))
            seen.add(item[i])
        if len(out) == k:
            break
    return out


plt.style.use("dark_background")
fig, top = figure(
    22,
    3.3 * N_DIR + 2.6,
    72,
    "THE LOOK OR THE FILE  ·  DIRECTIONS IN THE CO-MOVEMENT SPACE",
    "What changes in the picture as a frame moves along one direction?",
    f"{len(x)} frames, {int(keep.sum())} pair correlations, {BLOCKS[BLOCK][2]}  ·  {N_DIR} directions that each lean on few pairs  ·  "
    f"each row: four frames from the low end, four from the middle, four from the high end, each from a different item  ·  no direction is named",
)
gs = fig.add_gridspec(
    N_DIR,
    13,
    left=0.012,
    right=0.99,
    bottom=0.03,
    top=top - 0.035,
    wspace=0.04,
    hspace=0.3,
    width_ratios=[1] * 12 + [3.3],
)
for d in range(N_DIR):
    a = proj[:, d]
    o = np.argsort(a)
    mid = np.argsort(np.abs(a - np.median(a)))
    picks = (
        spread_pick(o, PER_END) + spread_pick(mid, PER_END) + spread_pick(o[::-1], PER_END)[::-1]
    )
    for c, i in enumerate(picks):
        ax = fig.add_subplot(gs[d, c])
        im = Image.open(T / "flat" / order[i]["name"])
        im.thumbnail((420, 420))
        ax.imshow(im)
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(CYAN if c < 4 else (MUTED if c < 8 else GOLD))
            s.set_linewidth(2)
        ax._is_colorbar = True
        if c in (0, 4, 8):
            ax.set_title(
                ("low end" if c == 0 else "middle" if c == 4 else "high end") + f"   ({a[i]:+.1f})",
                color=CYAN if c == 0 else (MUTED if c == 4 else GOLD),
                fontsize=9.5,
                loc="left",
                pad=4,
            )
    w = comp[d]
    top_pairs = np.argsort(-np.abs(w))[:6]
    ax = fig.add_subplot(gs[d, 12])
    ax.set_axis_off()
    ax._is_colorbar = True
    lines = [
        f"direction {d + 1}: leans on {int((np.abs(w) > 1e-9).sum())} of {len(w)} pairs",
        "toward the high end:",
    ]
    lines += [
        f"   {'more' if w[j] > 0 else 'less'} {names_kept[j]} moving together" for j in top_pairs
    ]
    ax.text(
        0,
        0.98,
        "\n".join(lines),
        color=TEXT,
        fontsize=8.6,
        va="top",
        transform=ax.transAxes,
        linespacing=1.5,
    )
    res["directions"].append(
        {
            "pairs_used": int((np.abs(w) > 1e-9).sum()),
            "top_pairs": [{"pair": names_kept[j], "weight": float(w[j])} for j in top_pairs],
            "low": [order[i]["name"] for i in picks[:4]],
            "high": [order[i]["name"] for i in picks[8:]],
            # The raw correlation of the heaviest pair at each end, and where three known frames fall.
            "top_pair_raw_low_end": float(np.nanmean(x[o[:20]][:, keep][:, top_pairs[0]])),
            "top_pair_raw_high_end": float(np.nanmean(x[o[-20:]][:, keep][:, top_pairs[0]])),
            "probes_percentile": {
                k: float((a < a[[n["name"] for n in order].index(v)]).mean())
                for k, v in PROBES.items()
            },
        }
    )
from matplotlib.lines import Line2D

fig.legend(
    handles=[
        Line2D([0], [0], color=c, lw=5, label=t)
        for t, c in (
            ("frames at the low end of a direction", CYAN),
            ("frames in the middle", MUTED),
            ("frames at the high end", GOLD),
        )
    ],
    loc="lower left",
    bbox_to_anchor=(0.012, 0.002),
    ncol=3,
    frameon=False,
    labelcolor=TEXT,
    fontsize=10,
)
verdict(
    fig,
    f"the first five ordinary directions hold {sum(pca.explained_variance_ratio_[:5]):.0%} of the variation; the five sparse ones lean on {', '.join(str(r['pairs_used']) for r in res['directions'])} pairs",
)
frame_panels(fig)
fig.savefig(OUT / BLOCKS[BLOCK][1], dpi=200, facecolor=BG)
(OUT / f"directions-{BLOCK}.json").write_text(json.dumps(res, indent=1))
print(
    "saved",
    [r["pairs_used"] for r in res["directions"]],
    [round(v, 2) for v in res["pca_variance_first_5"]],
)
for r in res["directions"]:
    print(
        " ",
        [(p["pair"], round(p["weight"], 2)) for p in r["top_pairs"][:3]],
        "| raw low",
        round(r["top_pair_raw_low_end"], 2),
        "high",
        round(r["top_pair_raw_high_end"], 2),
        "|",
        {k: round(v, 2) for k, v in r["probes_percentile"].items()},
    )
