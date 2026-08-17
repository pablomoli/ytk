"""Lead stills for the two video-only sections of the record (#190).

Sections 11 (animations) and 13 (space-3d) publish only mp4s; the public
experiment index and folder previews need one PNG per section. Frames are
extracted from the committed clips with ffmpeg, then composed through the
house anatomy so the stills match the rest of the series.

    uv run --with matplotlib python scripts/plot_video_stills.py
    uv run --with matplotlib python scripts/plot_video_stills.py --outdir /tmp/x
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    DPI,
    MARGIN,
    PANEL,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
    verdict,
)

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"

# Timestamps are hand-picked fully-drawn states; mid-draw frames carry
# half-rendered text.
FRAMES = {
    "NullModel": (ASSETS / "11-animations/NullModel.mp4", 35.90),
    "ReplayCurve": (ASSETS / "11-animations/ReplayCurve.mp4", 15.54),
    "TheCone": (ASSETS / "13-space-3d/TheCone.mp4", 8.35),
    "TagInSpace": (ASSETS / "13-space-3d/TagInSpace.mp4", 24.25),
    "CorpusSolid": (ASSETS / "13-space-3d/CorpusSolid.mp4", 18.43),
}


def extract(workdir: Path) -> dict:
    import matplotlib.image as mpimg

    out = {}
    for name, (video, t) in FRAMES.items():
        png = workdir / f"{name}.png"
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-ss",
                f"{t:.2f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-y",
                str(png),
            ],
            check=True,
        )
        out[name] = mpimg.imread(png)
    return out


def sha() -> str:
    r = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() or "unstamped"


def emberize(img, cmap):
    """Video frames wear the record's continuous ramp: luminance through
    saturated magma. Hue distinctions inside a frame become brightness."""
    import numpy as np

    lum = np.asarray(img)[..., :3] @ np.array([0.2126, 0.7152, 0.0722])
    # subtract the frame's near-black floor first, or punch() lifts the video
    # background to magma's indigo and the panels no longer sit on house black
    lum = np.clip((lum - 0.04) / 0.96, 0, 1)
    return cmap(punch(lum))[..., :3]


def panel(fig, spec, img, cmap, title: str) -> None:
    ax = fig.add_subplot(spec)
    ax.imshow(emberize(img, cmap))
    ax.set_axis_off()
    ax.set_facecolor(PANEL)
    panel_title(ax, title, width=86)


def fig_animations(frames, cmap, outdir: Path) -> Path:
    fig, top = figure(
        12.6,
        13.4,
        1,
        "animated nulls",
        "The two null-model explainers, one frame each",
        "stills at 35.9s of NullModel.mp4 (37s) and 15.5s of ReplayCurve.mp4 (26s)  ·  "
        f"data: sections 09-10 sidecars — 493 notes; 156 videos, 3024 key moments  ·  {sha()}",
    )
    panel(
        fig,
        211,
        frames["NullModel"],
        cmap,
        "NullModel — 'reference' at z = -3.4, 'ai-coding' at z = +17 on the null's ruler",
    )
    panel(
        fig,
        212,
        frames["ReplayCurve"],
        cmap,
        "ReplayCurve — the 10 generated key moments against where people actually rewatch",
    )
    verdict(fig, "every moving point is measured data — the nulls are size-matched, not stand-ins")
    # row gap holds the second panel title plus 2x the frame pad, or frames merge
    fig.subplots_adjust(left=MARGIN, right=1 - MARGIN, top=top, bottom=MARGIN, hspace=0.16)
    frame_panels(fig)
    out = outdir / "11-animations" / "01-null-and-replay-stills.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    return out


def fig_space3d(frames, cmap, outdir: Path) -> Path:
    fig, top = figure(
        12.6,
        13.0,
        1,
        "orbit stills",
        "The 3D claims, one orbit frame each",
        "TheCone at 8.4s (33s), TagInSpace at 24.3s (25s), CorpusSolid at 18.4s (19s)  ·  "
        f"200 of 493 notes shown; highlighted tags never subsampled  ·  {sha()}",
    )
    gs = fig.add_gridspec(
        2,
        2,
        height_ratios=[2.1, 1],
        left=MARGIN,
        right=1 - MARGIN,
        top=top,
        bottom=MARGIN,
        wspace=0.11,
        hspace=0.18,
    )
    panel(
        fig,
        gs[0, :],
        frames["TheCone"],
        cmap,
        "TheCone — the vault as stored, leaning off the marked origin",
    )
    panel(
        fig,
        gs[1, 0],
        frames["TagInSpace"],
        cmap,
        "TagInSpace — 'reference' as confetti; no angle makes it a cluster",
    )
    panel(
        fig,
        gs[1, 1],
        frames["CorpusSolid"],
        cmap,
        "CorpusSolid — sources interleave; the space is organised by subject",
    )
    verdict(fig, "same numbers, camera moving — the claims survive every angle")
    frame_panels(fig)
    out = outdir / "13-space-3d" / "01-orbit-stills.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=Path, default=ASSETS, help="write PNGs under this root")
    args = ap.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    cmap = saturated_magma()
    with tempfile.TemporaryDirectory() as td:
        frames = extract(Path(td))
    for path in (fig_animations(frames, cmap, args.outdir), fig_space3d(frames, cmap, args.outdir)):
        print(f"wrote {path}  ({path.stat().st_size // 1024}KB)")
    plt.close("all")


if __name__ == "__main__":
    main()
