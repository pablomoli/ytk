"""Section 72, part 2: the same three frames, with the correlations taken inside the lit part and the busy part only.

On a frame that is mostly black every map marks the same small lit region, so its whole-frame
matrix is dense for a reason that has nothing to do with how the picture is made.

    uv run --with matplotlib python scripts/taste_conditional_figure.py
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import taste_maps_cuda as tm
from PIL import Image
from plot_assets import BG, MUTED, TEXT, figure, frame_panels, saturated_magma, verdict

T = Path.home() / ".ytk" / "taste-test"
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "72-look-or-file"
PICKS = [
    ("carousel-38_00.jpg", "a render on black"),
    ("youtube-04_05.jpg", "type on black"),
    ("tiktok-47_04.jpg", "live footage"),
]
VERSIONS = [
    ("together_scale_1", "across the whole frame"),
    ("together_lit", "inside the lit part only"),
    ("together_busy", "inside the busy part only"),
]
C = len(tm.NAMES)
iu = np.triu_indices(C, 1)
cmap = saturated_magma()
cmap.set_bad("#1c1c22")


def full(v: np.ndarray) -> np.ndarray:
    M = np.full((C, C), np.nan)
    M[iu] = v[:231]
    M.T[iu] = v[:231]
    return M


stats = []
for name, _ in PICKS:
    s, _maps = tm.measure(T / "flat" / name)
    stats.append(s)
    del _maps
gap = {}
for key, label in VERSIONS:
    m = [full(s[key]) for s in stats]
    d = lambda a, b: float(np.nanmean(np.abs(a - b)))
    gap[label] = {
        "render_vs_type": d(m[0], m[1]),
        "render_vs_live": d(m[0], m[2]),
        "type_vs_live": d(m[1], m[2]),
        "mean_abs_correlation": [float(np.nanmean(np.abs(x))) for x in m],
    }
(OUT / "conditional.json").write_text(
    json.dumps(
        {
            "frames": [label for _, label in PICKS],
            "support_lit": [float(s["support_lit"][0]) for s in stats],
            "support_busy": [float(s["support_busy"][0]) for s in stats],
            "differences": gap,
        },
        indent=1,
    )
)
print(json.dumps(gap, indent=1))

plt.style.use("dark_background")
w, l = gap["across the whole frame"], gap["inside the lit part only"]
fig, top = figure(
    20,
    15.4,
    72,
    "THE LOOK OR THE FILE  ·  CORRELATIONS INSIDE A PART OF THE FRAME",
    "Is the type card's dense matrix about the type, or about the black around it?",
    f"the three frames of section 71  ·  the 231 pair correlations taken across every pixel, then only where the frame is lit, then only where it is busy (not flat)  ·  "
    f"mean strength of correlation on the type card: {w['mean_abs_correlation'][1]:.2f} across the whole frame, {l['mean_abs_correlation'][1]:.2f} inside the lit part",
)
gs = fig.add_gridspec(
    3,
    4,
    left=0.03,
    right=0.98,
    bottom=0.06,
    top=top - 0.04,
    wspace=0.14,
    hspace=0.14,
    width_ratios=[0.9, 1, 1, 1],
)
for r, ((name, label), s) in enumerate(zip(PICKS, stats, strict=True)):
    ax = fig.add_subplot(gs[r, 0])
    ax.imshow(Image.open(T / "flat" / name))
    ax.set_axis_off()
    ax.set_title(
        f"{label}  ·  lit {s['support_lit'][0]:.0%} of the frame, busy {s['support_busy'][0]:.0%}",
        color=TEXT,
        fontsize=10,
        pad=8,
    )
    for c, (key, vlabel) in enumerate(VERSIONS):
        ax = fig.add_subplot(gs[r, c + 1])
        ax.imshow(np.ma.masked_invalid((full(s[key]) + 1) / 2), cmap=cmap, vmin=0, vmax=1)
        ax.set_xticks([])
        ax.set_yticks(range(C))
        ax.set_yticklabels(tm.NAMES if c == 0 else [], color=TEXT, fontsize=6.5)
        ax.set_title(vlabel, color=TEXT, fontsize=10, pad=8)
key = fig.add_axes((0.72, 0.03, 0.18, 0.008))
key.imshow(np.linspace(0, 1, 256)[None, :], cmap=cmap, aspect="auto")
key.set_xticks([])
key.set_yticks([])
key._is_colorbar = True
key.set_title("matrix color: correlation of two maps", color=TEXT, fontsize=9, loc="left", pad=4)
fig.text(0.72, 0.016, "-1, opposite", color=MUTED, fontsize=8.5)
fig.text(0.81, 0.016, "0", color=MUTED, fontsize=8.5, ha="center")
fig.text(0.90, 0.016, "+1, together", color=MUTED, fontsize=8.5, ha="right")
fig.text(
    0.03,
    0.022,
    "dark gray cells: no answer, the map does not vary inside that part of the frame",
    color=MUTED,
    fontsize=9,
)
verdict(
    fig,
    f"render against type: {w['render_vs_type']:.2f} apart across the whole frame, {l['render_vs_type']:.2f} inside the lit part; render against live footage {w['render_vs_live']:.2f} and {l['render_vs_live']:.2f}",
)
frame_panels(fig)
fig.savefig(OUT / "02-inside-the-lit-part.png", dpi=250, facecolor=BG)
print("saved")
