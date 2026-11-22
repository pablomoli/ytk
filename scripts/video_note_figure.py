"""Section 66: six videos as strips of their looks, beside what the whole-video note says each is kept for.

uv run --with matplotlib python scripts/video_note_figure.py
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
    GOLD,
    MUTED,
    PURPLE,
    TEXT,
    figure,
    frame_panels,
    punch,
    saturated_magma,
    style_axes,
    verdict,
)

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "66-video-note"
V = Path.home() / ".ytk" / "describer" / "video"
mo = np.load(Path.home() / ".ytk" / "sprites" / "moments.npz")
VIDEOS = [
    ("LQoFN1K1dZ8", "video essay on a film\n(saved for content,\nexecution and looks)"),
    ("urKKrMlhgwI", "fight film study"),
    ("vSczTbgc8Rc", "math animation"),
    ("VcvhiDV_t3c", "video synth tutorial"),
    ("ztkh1r1ioZo", "voxel rendering explainer"),
    ("0iEfNt5vYWQ", "audiobook reading"),
]
ARMS = [
    ("notes", "moment notes only", MUTED),
    ("structure", "+ how it is cut", CYAN),
    ("frames", "+ the frames themselves", GOLD),
]
DIMS = ["content", "execution", "look", "vibe"]
W = 500
notes = {
    a: {
        v: json.loads((V / a / f"{v}.json").read_text())
        for v, _ in VIDEOS
        if (V / a / f"{v}.json").exists()
    }
    for a, _, _ in ARMS
}
(OUT / "results.json").write_text(
    json.dumps(
        {
            a: {v: n["weight"] | {"come_back_for": n["come_back_for"]} for v, n in d.items()}
            for a, d in notes.items()
        },
        indent=1,
    )
)

plt.style.use("dark_background")
fg = notes["frames"]
essay, fight = fg["LQoFN1K1dZ8"]["weight"], fg["urKKrMlhgwI"]["weight"]
fig, top = figure(
    18,
    10.5,
    66,
    "THE WHOLE-VIDEO NOTE  ·  SIX VIDEOS, THREE LEVELS OF EVIDENCE",
    "Can a note about the whole video see what a note about one frame cannot?",
    "left: each video as a strip of its looks over time  ·  right: how much the note says content, execution, look and vibe are reasons to keep it (0 to 3), "
    "written from the moment notes alone, then with how the video is cut, then with the frames themselves",
)
gs = fig.add_gridspec(
    len(VIDEOS),
    2,
    left=0.16,
    right=0.975,
    bottom=0.1,
    top=top - 0.05,
    wspace=0.1,
    hspace=0.42,
    width_ratios=[2.1, 1],
)
cmap = saturated_magma()
share = {
    (v, int(k)): s
    for v, k, s in zip(mo["look_video"], mo["look_id"], mo["look_share"], strict=True)
}
for r, (vid, name) in enumerate(VIDEOS):
    ax = fig.add_subplot(gs[r, 0])
    style_axes(ax)
    m = mo["moment_video"] == vid
    dur = float(mo["moment_end"][m].max())
    row = np.zeros((1, W))
    for k, s, e in zip(
        mo["moment_look"][m], mo["moment_start"][m], mo["moment_end"][m], strict=True
    ):
        a = int(s / dur * W)
        row[0, a : max(int(e / dur * W), a + 1)] = share[(vid, int(k))]
    ax.imshow(
        punch(row, 0.55),
        cmap=cmap,
        vmin=0,
        vmax=1,
        aspect="auto",
        interpolation="nearest",
        extent=(0, dur / 60, 0, 1),
    )
    ax.set_yticks([])
    ax.set_ylabel(name, rotation=0, ha="right", va="center", color=TEXT, fontsize=10, labelpad=12)
    ax.tick_params(labelsize=8)
    if r == len(VIDEOS) - 1:
        ax.set_xlabel("minutes into the video")
    if r == 0:
        ax.set_title("Looks over time", color=TEXT, fontsize=10.5, pad=10)
    ax2 = fig.add_subplot(gs[r, 1])
    style_axes(ax2)
    for j, (arm, label, col) in enumerate(ARMS):
        if vid in notes[arm]:
            w = notes[arm][vid]["weight"]
            ax2.plot(
                np.arange(4) + (j - 1) * 0.2,
                [w[d] for d in DIMS],
                color=col,
                lw=0,
                marker="o",
                markersize=9 + 2 * j,
                label=label,
            )
    ax2.set_ylim(-0.4, 3.4)
    ax2.set_xlim(-0.6, 3.6)
    ax2.set_yticks([0, 1, 2, 3])
    ax2.set_xticks(range(4))
    ax2.set_xticklabels(DIMS if r == len(VIDEOS) - 1 else [], color=TEXT, fontsize=9.5)
    ax2.tick_params(labelsize=8)
    ax2.grid(axis="y", color="#1c1c22", lw=0.8)
    if r == 0:
        ax2.set_title("Reasons to keep it, by the note", color=TEXT, fontsize=10.5, pad=10)
        ax2.legend(
            frameon=False,
            fontsize=8.5,
            labelcolor=TEXT,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.75),
            ncol=3,
        )
key = fig.add_axes((0.16, 0.03, 0.2, 0.011))
key.imshow(np.linspace(0, 1, 256)[None, :], cmap=cmap, aspect="auto", vmin=0, vmax=1)
key.set_xticks([])
key.set_yticks([])
key._is_colorbar = True
key.set_title(
    "strip color: share of the video a look fills", color=TEXT, fontsize=9, loc="left", pad=4
)
fig.text(0.16, 0.014, "a brief look", color=MUTED, fontsize=8.5, ha="left")
fig.text(0.36, 0.014, "the whole video", color=MUTED, fontsize=8.5, ha="right")
verdict(
    fig,
    f"with the frames: the film essay scores execution {essay['execution']} and look {essay['look']}; the fight study {fight['execution']} and {fight['look']}",
)
frame_panels(fig)
fig.savefig(OUT / "01-video-notes.png", dpi=300, facecolor=BG)
print("saved")
for vid, name in VIDEOS:
    for arm, _, _ in ARMS:
        n = notes[arm].get(vid)
        if n:
            print(f"{name.splitlines()[0]:26s} {arm:9s} {n['weight']} back={n['come_back_for']}")
_ = PURPLE
