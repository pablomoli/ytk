"""Section 72, part 1: does a family follow the look, or the file?

Each test frame is altered three ways that barely change what a person sees (saved again
as JPEG at quality 40, resampled to half size, cropped to its central 90%). For every family:
  finds itself      the altered frame's nearest original is its own original
  keeps neighbors   the altered frame's 10 nearest originals from other items are the ones
                    its original had
A reading of the look should do both. A reading of the file does neither once the file changes.

    uv run --with matplotlib python scripts/taste_invariance.py
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
    PURPLE,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
    style_axes,
    verdict,
)

T = Path.home() / ".ytk" / "taste-test"
S = T / "s72"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "72-look-or-file"
ALTS = [
    ("jpeg", "saved again, JPEG quality 40"),
    ("half", "half the size"),
    ("crop", "central 90%"),
]
K = 10
order = json.loads((T / "order.json").read_text())
item = np.array([o["item"] for o in order])
n = len(order)
same = item[:, None] == item[None, :]
WHERE = {"layout", "thumbnail", "balance", "symmetry", "spread", "regions", "stroke_width"}


def families(bank, sig, tg) -> dict[str, np.ndarray]:
    f = {str(k): bank[str(k)] for k in bank["families"]}
    f["complexity"] = f["complexity"][:, :3]
    f |= {"image model, pooled": sig["pooled"]}
    f |= {f"image model, patch stats, depth {d}": sig[f"stats_{d}"] for d in (9, 18, 27)}
    f |= {f"image model, patch Gram, depth {d}": sig[f"gram_{d}"] for d in (9, 18, 27)}
    f |= {
        "maps together, whole frame": tg["together_scale_1"][:, :231],
        "maps together, blurred 16x": tg["together_scale_16"][:, :231],
        "maps together, by region": tg["together_by_region"],
        "maps together, lit part only": tg["together_lit"],
        "maps together, busy part only": tg["together_busy"],
    }
    return f


def group(k: str) -> str:
    if k.startswith("image model"):
        return "image model"
    if k.startswith("maps together"):
        return "maps moving together"
    return "where things are" if k in WHERE else "color, light, texture"


orig = families(
    np.load(T / "bank.npz"), np.load(T / "siglip.npz"), np.load(S / "orig" / "together.npz")
)
alt = {
    a: families(
        np.load(S / f"bank_{a}.npz"),
        np.load(S / f"siglip_{a}.npz"),
        np.load(S / a / "together.npz"),
    )
    for a, _ in ALTS
}
names = list(orig)
res = {k: {"group": group(k)} for k in names}
for k in names:
    x = orig[k].astype(np.float64)
    mu, sd = np.nanmean(x, 0), np.nanstd(x, 0) + 1e-9

    def unit(v, mu=mu, sd=sd):
        z = np.nan_to_num(
            (v.astype(np.float64) - mu) / sd
        )  # a missing value sits at the family's mean
        return z / (np.linalg.norm(z, axis=1, keepdims=True) + 1e-9)

    xo = unit(x)
    so = xo @ xo.T
    np.fill_diagonal(so, -9)
    res[k]["holds_together"] = float(
        same[np.arange(n)[:, None], np.argsort(-so, axis=1)[:, :5]].mean()
    )
    so_x = so.copy()
    so_x[same] = -9
    base = np.argsort(-so_x, axis=1)[:, :K]
    for a, _ in ALTS:
        s = unit(alt[a][k]) @ xo.T
        res[k][f"finds_itself_{a}"] = float((s.argmax(1) == np.arange(n)).mean())
        s[same] = -9
        got = np.argsort(-s, axis=1)[:, :K]
        res[k][f"keeps_neighbors_{a}"] = float(
            np.mean([len(set(p) & set(q)) for p, q in zip(base, got, strict=True)]) / K
        )
    res[k]["finds_itself"] = float(np.mean([res[k][f"finds_itself_{a}"] for a, _ in ALTS]))
    res[k]["keeps_neighbors"] = float(np.mean([res[k][f"keeps_neighbors_{a}"] for a, _ in ALTS]))
(OUT / "invariance.json").write_text(json.dumps({"frames": n, "families": res}, indent=1))
rank = sorted(names, key=lambda k: -res[k]["keeps_neighbors"])
for k in rank:
    r = res[k]
    print(
        f"{k:36s} holds {r['holds_together']:.2f} | finds itself {r['finds_itself']:.2f} | keeps neighbors {r['keeps_neighbors']:.2f}  "
        + " ".join(f"{a}:{r[f'keeps_neighbors_{a}']:.2f}" for a, _ in ALTS)
    )

plt.style.use("dark_background")
cmap = saturated_magma()
col = {
    "color, light, texture": GOLD,
    "where things are": CYAN,
    "image model": PURPLE,
    "maps moving together": TEXT,
}
best, worst = rank[0], rank[-1]
fig, top = figure(
    21,
    10.4,
    72,
    "THE LOOK OR THE FILE  ·  THE SAME FRAMES, ALTERED THREE WAYS",
    "When the file changes and the picture does not, which readings stay put?",
    f"{n} frames, each saved again at JPEG quality 40, resampled to half size, and cropped to its central 90%  ·  finds itself = the altered frame's nearest original is its own  ·  "
    f"keeps neighbors = its {K} nearest originals from other items are the ones its original had",
)
gs = fig.add_gridspec(
    1, 2, left=0.17, right=0.975, bottom=0.1, top=top - 0.07, wspace=0.26, width_ratios=[1, 1.25]
)
ax = fig.add_subplot(gs[0])
style_axes(ax)
cols = [f"{m}_{a}" for m in ("finds_itself", "keeps_neighbors") for a, _ in ALTS]
M = np.array([[res[k][c] for c in cols] for k in rank])
ax.imshow(punch(M, 0.8), cmap=cmap, vmin=0, vmax=1, aspect="auto")
for i in range(M.shape[0]):
    for j in range(M.shape[1]):
        ax.text(
            j,
            i,
            f"{M[i, j]:.2f}".lstrip("0") if M[i, j] < 1 else "1",
            ha="center",
            va="center",
            fontsize=7.5,
            color="#000000" if M[i, j] > 0.6 else TEXT,
        )
ax.set_yticks(range(len(rank)))
ax.set_yticklabels([k.replace("_", " ") for k in rank], color=TEXT, fontsize=8.5)
ax.set_xticks(range(6))
ax.set_xticklabels(
    [lab.replace(", ", ",\n") for _ in range(2) for _, lab in ALTS], color=TEXT, fontsize=8
)
ax.axvline(2.5, color=BG, lw=5)
ax.text(1, -1.1, "finds itself", color=TEXT, fontsize=10, ha="center")
ax.text(4, -1.1, "keeps its neighbors", color=TEXT, fontsize=10, ha="center")
ax.set_title(
    "Every family under every alteration (color and number: share of frames, 0 to 1)",
    color=TEXT,
    fontsize=10.5,
    pad=34,
)
ax = fig.add_subplot(gs[1])
style_axes(ax)
ax.plot(
    [0, 1], [0, 1], color=DIM, lw=5, label="keeps neighbors exactly as well as it holds together"
)
for g, c in col.items():
    ks = [k for k in names if res[k]["group"] == g]
    ax.scatter(
        [res[k]["holds_together"] for k in ks],
        [res[k]["keeps_neighbors"] for k in ks],
        s=130,
        color=c,
        label=g,
        zorder=3,
    )
for k in names:
    ax.annotate(
        k.replace("image model, ", "").replace("maps together, ", "").replace("_", " "),
        (res[k]["holds_together"], res[k]["keeps_neighbors"]),
        xytext=(7, 3),
        textcoords="offset points",
        color=TEXT,
        fontsize=7.5,
    )
ax.set_xlim(0, 0.95)
ax.set_ylim(0, 1.02)
ax.set_xlabel(
    "holds together: a frame's nearest frames come from its own item (sections 70 and 71)"
)
ax.set_ylabel("keeps its neighbors when the file is altered (mean of the three)")
ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="upper left")
panel_title(
    ax,
    "Right and low is the mark of a file reading: tight within an item, lost when the file changes",
    width=74,
)
verdict(
    fig,
    f"keeps its neighbors best: {best.replace('_', ' ')} ({res[best]['keeps_neighbors']:.0%}); worst: {worst.replace('_', ' ')} ({res[worst]['keeps_neighbors']:.0%})",
)
frame_panels(fig)
fig.savefig(OUT / "01-look-or-file.png", dpi=300, facecolor=BG)
print("saved")
_ = MUTED
