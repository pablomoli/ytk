"""HUD frame sequence for the garden growth video, in the house style.

    uv run --with matplotlib python scripts/hud_frames.py [outDir] [seconds] [fps]

The local ffmpeg is built without freetype, so drawtext is unavailable and the
animated parts are rendered here rather than composited. Static artists are
drawn once and only the counter and bar are updated per frame, which keeps the
sequence cheap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from plot_assets import FRAME, GOLD, MUTED, TEXT, use_house_font

use_house_font()

W, H, DPI = 1600, 900, 100
GROW_START, GROW_SPAN = 0.6, 14.5

KEY = [
    ("height", "notes in the topic, on a log scale"),
    ("trunk girth", "the twigs it carries, by the pipe model"),
    ("limb length", "how persistent that cluster is"),
    ("canopy colour", "the topic itself"),
    ("roots", "the same pipeline, mirrored"),
]


def main() -> None:
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/hudframes")
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    fps = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    outdir.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    ax.patch.set_alpha(0.0)

    ax.text(64, H - 62, "the garden", color=TEXT, fontsize=34, va="top")
    ax.text(
        66,
        H - 112,
        "2,652 notes  ·  10 topics  ·  grown from the vault",
        color=MUTED,
        fontsize=15,
        va="top",
    )
    ax.text(64, 246, "what the shape means", color=TEXT, fontsize=15, va="top")
    y = 208
    for name, meaning in KEY:
        ax.plot([64, 82], [y, y], color=GOLD, linewidth=1.6, alpha=0.85)
        ax.text(96, y, name, color=TEXT, fontsize=12.5, va="center")
        ax.text(224, y, meaning, color=MUTED, fontsize=12.5, va="center")
        y -= 30
    ax.add_patch(plt.Rectangle((W - 480, 92), 416, 7, facecolor=FRAME, edgecolor="none"))
    ax.text(W - 64, 118, "growth", color=MUTED, fontsize=13, ha="right", va="bottom")
    ax.text(
        64,
        44,
        "epicmap and nine others  ·  replayed from the live vault",
        color=MUTED,
        fontsize=13,
        va="bottom",
    )

    fill = ax.add_patch(plt.Rectangle((W - 480, 92), 1, 7, facecolor=GOLD, edgecolor="none"))
    pct = ax.text(W - 64, 150, "0%", color=GOLD, fontsize=42, ha="right", va="bottom")

    total = int(seconds * fps)
    for i in range(total):
        t = i / fps
        frac = min(1.0, max(0.0, (t - GROW_START) / GROW_SPAN))
        fill.set_width(max(1.0, 416 * frac))
        pct.set_text(f"{round(frac * 100)}%")
        fig.savefig(outdir / f"hud_{i:04d}.png", dpi=DPI, transparent=True)
    print(f"wrote {total} frames to {outdir}")


if __name__ == "__main__":
    main()
