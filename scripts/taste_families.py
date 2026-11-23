"""Section 70: which families of measurement say something, and which say something new.

For each family of readings on the 417 test frames:
  holds together   share of a frame's 5 nearest frames that come from the same item
  follows subject  share of its 10 nearest frames from other items that pooled SigLIP also picks
and how much every pair of families agrees. A family of random numbers is the reference.

    uv run --with matplotlib python scripts/taste_families.py
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage

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
    ramp_legend,
    saturated_magma,
    style_axes,
    verdict,
)

T = Path.home() / ".ytk" / "taste-test"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "70-measurement-families"
K_IN, K_OUT = 5, 10
order = json.loads((T / "order.json").read_text())
item = np.array([o["item"] for o in order])
n = len(order)
bank, sig = np.load(T / "bank.npz"), np.load(T / "siglip.npz")
WHERE = {"layout", "thumbnail", "balance", "symmetry", "spread", "regions", "stroke_width"}
fam = {
    str(f): (bank[str(f)], "where things are" if str(f) in WHERE else "color, light, texture")
    for f in bank["families"]
}
# Frame size and aspect ratio identify the platform, not the look: kept in the file, left out here.
fam["complexity"] = (fam["complexity"][0][:, :3], fam["complexity"][1])
fam |= {"image model, pooled": (sig["pooled"], "image model")}
fam |= {
    f"image model, patch stats, depth {d}": (sig[f"stats_{d}"], "image model") for d in (9, 18, 27)
}
fam |= {
    f"image model, patch Gram, depth {d}": (sig[f"gram_{d}"], "image model") for d in (9, 18, 27)
}
rng = np.random.default_rng(0)
fam["random numbers"] = (rng.normal(size=(n, 32)), "reference")
names = list(fam)


def sims(x: np.ndarray) -> np.ndarray:
    x = (x - x.mean(0)) / (x.std(0) + 1e-9)
    x = x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)
    s = x @ x.T
    np.fill_diagonal(s, -9)
    return s


same = item[:, None] == item[None, :]
nn_in, nn_out = {}, {}
for k, (x, _) in fam.items():
    s = sims(x.astype(np.float64))
    nn_in[k] = np.argsort(-s, axis=1)[:, :K_IN]
    s2 = s.copy()
    s2[same] = -9
    nn_out[k] = np.argsort(-s2, axis=1)[:, :K_OUT]
holds = {k: float(same[np.arange(n)[:, None], v].mean()) for k, v in nn_in.items()}
overlap = lambda a, b: float(
    np.mean([len(set(x) & set(y)) for x, y in zip(nn_out[a], nn_out[b], strict=True)]) / K_OUT
)
M = np.array([[overlap(a, b) for b in names] for a in names])
subject = {k: M[names.index(k), names.index("image model, pooled")] for k in names}
chance_in = float(np.mean([(item == i).sum() - 1 for i in item]) / (n - 1))
res = {
    k: {
        "group": fam[k][1],
        "numbers": int(fam[k][0].shape[1]),
        "holds_together": holds[k],
        "follows_subject": subject[k],
    }
    for k in names
}
(OUT / "results.json").write_text(
    json.dumps({"frames": n, "chance_holds_together": chance_in, "families": res}, indent=1)
)
for k in sorted(names, key=lambda k: -holds[k]):
    print(
        f"{k:38s} {fam[k][0].shape[1]:5d}  holds {holds[k]:.2f}  follows subject {subject[k]:.2f}"
    )

plt.style.use("dark_background")
real = [k for k in names if k != "random numbers" and k != "image model, pooled"]
best_new = max((k for k in real if fam[k][1] != "image model"), key=lambda k: holds[k] - subject[k])
fig, top = figure(
    20,
    9.6,
    70,
    "MEASUREMENT FAMILIES  ·  WHAT EACH KIND OF READING CARRIES",
    "Which measurements say something about a frame, and which say something the image model does not?",
    f"{n} frames from 50 items, every measure taken on the whole frame at its own size  ·  {len(names) - 1} families, {sum(fam[k][0].shape[1] for k in names if k != 'random numbers'):,} numbers per frame  ·  "
    f"holds together = share of a frame's {K_IN} nearest that are from its own item (chance {chance_in:.2f})  ·  follows subject = share of its {K_OUT} nearest from other items that pooled SigLIP also picks",
)
gs = fig.add_gridspec(
    1, 2, left=0.17, right=0.975, bottom=0.1, top=top - 0.07, wspace=0.32, width_ratios=[1, 1.12]
)
ax = fig.add_subplot(gs[0])
style_axes(ax)
o = leaves_list(linkage(M, "average"))
cmap = saturated_magma()
show = M[np.ix_(o, o)].copy()
np.fill_diagonal(show, np.nan)
ax.imshow(punch(show / np.nanmax(show), 0.6), cmap=cmap, vmin=0, vmax=1)
ax.set_xticks([])
ax.set_yticks(range(len(o)))
ax.set_yticklabels([names[i].replace("_", " ") for i in o], color=TEXT, fontsize=8.5)
panel_title(
    ax,
    "How much each pair of families agrees on what is near what (rows reordered so alike families sit together)",
    width=62,
)
ax = fig.add_subplot(gs[1])
style_axes(ax)
col = {
    "color, light, texture": GOLD,
    "where things are": CYAN,
    "image model": PURPLE,
    "reference": MUTED,
}
ax.axhline(chance_in, color=DIM, lw=6, label="holds together by chance")
ax.axvline(subject["random numbers"], color=DIM, lw=6)
for g, c in col.items():
    ks = [k for k in names if fam[k][1] == g and k != "image model, pooled"]
    ax.scatter(
        [subject[k] for k in ks],
        [holds[k] for k in ks],
        s=120,
        color=c,
        label=g if g != "reference" else "a family of random numbers",
        zorder=3,
    )
for k in names:
    if k == "image model, pooled":
        continue
    ax.annotate(
        k.replace("image model, ", "").replace("_", " "),
        (subject[k], holds[k]),
        xytext=(7, 4),
        textcoords="offset points",
        color=TEXT,
        fontsize=8,
    )
ax.axhline(
    holds["image model, pooled"],
    color=PURPLE,
    lw=1,
    ls="--",
    label="pooled image model, how well it holds together",
)
ax.set_xlim(0, max(v for k, v in subject.items() if k != "image model, pooled") * 1.25)
ax.set_xlabel(
    "follows subject: agreement with the pooled image model on neighbors from other items"
)
ax.set_ylabel("holds together: nearest frames come from the same item")
ax.legend(frameon=False, fontsize=8.5, labelcolor=TEXT, loc="lower right")
panel_title(ax, "Up is signal, left is something the image model does not already say", width=70)
key = fig.add_axes((0.17, 0.035, 0.18, 0.012))
key.imshow(np.linspace(0, 1, 256)[None, :], cmap=cmap, aspect="auto")
key.set_xticks([])
key.set_yticks([])
key._is_colorbar = True
key.set_title(
    "matrix color: shared neighbors between two families", color=TEXT, fontsize=9, loc="left", pad=4
)
fig.text(0.17, 0.018, "none", color=MUTED, fontsize=8.5)
fig.text(0.35, 0.018, f"{np.nanmax(show):.0%}", color=MUTED, fontsize=8.5, ha="right")
verdict(
    fig,
    f"{best_new.replace('_', ' ')} holds together {holds[best_new]:.0%} of the time and shares {subject[best_new]:.0%} of neighbors with the image model",
)
frame_panels(fig)
fig.savefig(OUT / "01-families.png", dpi=300, facecolor=BG)
print("saved")
_ = ramp_legend
