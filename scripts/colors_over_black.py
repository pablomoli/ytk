"""Section 68: "colors over black" written as a number, scored on every distinct look.

The owner's sentence, as two measured quantities per frame:
  dark   = share of pixels that are near-black
  color  = mean of saturation x brightness over the pixels that are not
  score  = dark x color
No model. Videos in the taste test set are left out so that set stays unseen.

    uv run --with matplotlib python scripts/colors_over_black.py
"""

import colorsys
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from plot_assets import (
    BG,
    CYAN,
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

SPRITES = Path.home() / ".ytk" / "sprites"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "68-colors-over-black"
PRIVATE = Path.home() / ".ytk" / "taste-spike"
NEAR_BLACK = 0.08
_hsv = np.vectorize(colorsys.rgb_to_hsv)
mo = np.load(SPRITES / "moments.npz")
sample = json.loads((Path.home() / ".ytk" / "taste-test" / "sample.json").read_text())
held_out = {x["url"].split("v=")[1] for x in sample if x["kind"] == "youtube"}


def tile(vid: str, i: int) -> np.ndarray:
    grid = json.loads((SPRITES / vid / "grid.json").read_text())
    frag, k = divmod(i, grid["rows"] * grid["cols"])
    r, c = divmod(k, grid["cols"])
    with Image.open(SPRITES / vid / f"{frag:03d}.jpg") as im:
        w, h = im.width // grid["cols"], im.height // grid["rows"]
        return (
            np.asarray(im.convert("RGB").crop((c * w, r * h, (c + 1) * w, (r + 1) * h)), float)
            / 255
        )


def measure(a: np.ndarray) -> tuple[float, float]:
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    dark = lum < NEAR_BLACK
    if dark.all():
        return 1.0, 0.0
    _, s, v = _hsv(a[..., 0], a[..., 1], a[..., 2])
    return float(dark.mean()), float((s * v)[~dark].mean())


cache = SPRITES / "colors_over_black.npz"
if cache.exists():
    z = np.load(cache)
    D, C, keep = z["dark"], z["color"], z["rows"]
else:
    keep = np.array([i for i, v in enumerate(mo["look_video"]) if v not in held_out])
    vals = [measure(tile(str(mo["look_video"][i]), int(mo["look_rep"][i]))) for i in keep]
    D, C = np.array([v[0] for v in vals]), np.array([v[1] for v in vals])
    np.savez(cache, dark=D, color=C, rows=keep)
S = D * C
order = np.argsort(-S)
# The two frames whose look he marked right on the review page.
marked = []
for vid, letter in (("VcvhiDV_t3c", "D"), ("ztkh1r1ioZo", "I")):
    rows = np.where(mo["look_video"] == vid)[0]
    j = np.where(keep == rows[ord(letter) - 65])[0]
    if len(j):
        marked.append(int(j[0]))
pct = [float((S[j] > S).mean()) for j in marked]
res = {
    "looks": len(S),
    "videos_left_out": len(held_out),
    "score_percentiles": {str(q): float(np.percentile(S, q)) for q in (50, 90, 99)},
    "share_above_0.1": float((S > 0.1).mean()),
    "marked_right_score_percentile": pct,
    "marked_right": [{"dark": float(D[j]), "color": float(C[j])} for j in marked],
}
(OUT / "results.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))

plt.style.use("dark_background")
cmap = saturated_magma()
fig, top = figure(
    17,
    8,
    68,
    "COLORS OVER BLACK  ·  ONE SENTENCE AS A NUMBER",
    'Where do the looks he has saved fall when "colors over black" is measured?',
    f"{len(S):,} distinct looks from {len(set(mo['look_video'][keep]))} videos ({len(held_out)} test-set videos left out)  ·  dark = share of pixels under {NEAR_BLACK} luminance, "
    f"color = mean saturation x brightness of the rest, score = dark x color  ·  half of all looks score under {np.median(S):.3f}, 1 in 100 above {np.percentile(S, 99):.2f}",
)
gs = fig.add_gridspec(
    1, 2, left=0.06, right=0.97, bottom=0.11, top=top - 0.08, wspace=0.16, width_ratios=[1.5, 1]
)
ax = fig.add_subplot(gs[0])
style_axes(ax)
o = np.argsort(S)
ax.scatter(
    D[o],
    C[o],
    c=punch(S[o] / S.max(), 0.5),
    cmap=cmap,
    vmin=0,
    vmax=1,
    s=9,
    linewidths=0,
    alpha=0.85,
)
gx = np.linspace(0.02, 1, 200)
for lvl in (0.05, 0.1, 0.2):
    ax.plot(
        gx,
        lvl / gx,
        color=MUTED,
        lw=0.8,
        ls="--",
        label="equal score: 0.05, 0.1, 0.2" if lvl == 0.05 else None,
    )
if marked:
    ax.scatter(
        D[marked],
        C[marked],
        s=260,
        facecolors="none",
        edgecolors=CYAN,
        linewidths=2.2,
        label="the two frames whose look he marked right",
        zorder=5,
    )
ax.set_xlim(-0.02, 1.02)
ax.set_ylim(-0.01, min(C.max() * 1.08, 1))
ax.set_xlabel("dark: share of the frame that is near-black")
ax.set_ylabel("color: saturation x brightness of everything that is not")
ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper right")
ramp_legend(
    ax, cmap, "dot color: the score, dark x color", "0", f"{S.max():.2f}", room=0, at=(0.03, 0.9)
)
panel_title(ax, "Every look, by how dark its ground is and how colored the rest is", width=80)
ax = fig.add_subplot(gs[1])
style_axes(ax)
ax.hist(S, bins=np.linspace(0, S.max(), 60), color=GOLD, label="looks")
ax.set_yscale("log")
for j in marked:
    ax.axvline(S[j], color=CYAN, lw=2, label="a frame he marked right" if j == marked[0] else None)
ax.axvline(np.percentile(S, 99), color=MUTED, lw=1, ls="--", label="99th percentile")
ax.set_xlabel("score")
ax.set_ylabel("looks (log)")
ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper right")
panel_title(ax, "How rare a high score is", width=40)
verdict(
    fig,
    "the two looks he marked right sit at the "
    + " and ".join(f"{p:.0%}" for p in pct)
    + " percentile of the score",
)
frame_panels(fig)
fig.savefig(OUT / "01-score.png", dpi=300, facecolor=BG)

# Private sheet: what the number picks, top, middle and two kinds of near miss.
PRIVATE.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(3)
one_per_video = lambda idx, n: list({mo["look_video"][keep[i]]: i for i in idx[::-1]}.values())[
    ::-1
][:n]
groups = [
    ("highest score", one_per_video(order[:400], 18)),
    (
        "middle of the pack",
        list(
            rng.choice(
                np.where((np.percentile(S, 45) < S) & (np.percentile(S, 55) > S))[0],
                6,
                replace=False,
            )
        ),
    ),
    ("dark but colorless (near miss)", one_per_video(np.argsort(-(D * (C < 0.05)))[:200], 6)),
    ("colorful but not dark (near miss)", one_per_video(np.argsort(-(C * (D < 0.1)))[:200], 6)),
]
fig, axes = plt.subplots(6, 6, figsize=(18, 11.2), facecolor=BG)
k = 0
for name, idx in groups:
    for i in idx:
        ax = axes.flat[k]
        ax.imshow(tile(str(mo["look_video"][keep[i]]), int(mo["look_rep"][keep[i]])))
        ax.set_title(
            f"{name}\ndark {D[i]:.2f} x color {C[i]:.2f} = {S[i]:.2f}",
            color=TEXT,
            fontsize=8,
            pad=3,
        )
        ax.set_axis_off()
        k += 1
for ax in axes.flat[k:]:
    ax.set_axis_off()
fig.suptitle(
    "What the number picks: 18 highest-scoring looks (one per video), 6 from the middle, and 12 near misses",
    color=TEXT,
    fontsize=12,
    y=0.995,
)
fig.subplots_adjust(left=0.005, right=0.995, top=0.94, bottom=0.005, wspace=0.03, hspace=0.3)
fig.savefig(OUT / "02-what-it-picks.png", dpi=200, facecolor=BG)
json.dump(
    {name: [int(keep[i]) for i in idx] for name, idx in groups},
    open(PRIVATE / "colors_over_black_picks.json", "w"),
)
print("saved")
