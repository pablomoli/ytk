"""One full orbit of the E30 planet, rendered in the stills' own language.

Supersedes the manim clip: cairo could only offer a lit grey mesh with drawn
outlines, which is not what the figures look like. Here every frame is the
same per-pixel orthographic projection the section's globes use — magma-glow
land anchored at the shoreline, dark sea, cyan coast, limb shading — so the
motion is literally the stills rotating. Frames are numpy + matplotlib,
assembly is ffmpeg.

    uv run --with matplotlib,scipy python scripts/render_planet_orbit.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e30_coastlines as e30
from e30b_fbm import ortho_sample
from e30b_organic_coast import level_for_area
from plot_assets import BG, CYAN, MUTED, PANEL, TEXT, punch, saturated_magma, use_house_font

SECONDS = 18.0
FPS = 30
SIZE_IN = 5.4  # x 200 dpi = 1080px
VIEW_LAT = np.radians(12)


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    use_house_font()
    d = e30.load()
    r_deg = e30.ocean_radius(d["lattice"])
    ll, tt, xyz = e30.grid()
    dist, _ = e30.fields(xyz, d["pos"], np.zeros(len(d["pos"]), dtype=int))
    target = float((np.cos(tt) * (dist < r_deg)).sum() / np.cos(tt).sum())
    field = e30.organic_field(d["pos"], xyz, r_deg)
    sd = field - level_for_area(field, tt, target)
    atlas = json.loads((e30.ASSETS / "continents.json").read_text())
    cmap = saturated_magma()

    n_frames = int(SECONDS * FPS)
    tmp = Path(tempfile.mkdtemp(prefix="planet-orbit-"))
    caption = (
        f"the ytk planet — {len(d['pos'])} notes, {len(atlas['continents'])} continents, "
        f"coast at {r_deg:.1f}°"
    )
    for f in range(n_frames):
        view_lon = np.radians(-35) + 2 * np.pi * f / n_frames
        img, mask, z = ortho_sample(sd, view_lon, VIEW_LAT)
        near = punch(np.clip(1.0 - (img + r_deg) / (2.5 * r_deg), 0, 1))
        shade = 0.55 + 0.45 * z
        rgba = cmap(near)
        rgba[..., :3] *= shade[..., None]
        rgba[~mask] = mcolors.to_rgba(BG)

        fig = plt.figure(figsize=(SIZE_IN, SIZE_IN), facecolor=BG)
        ax = fig.add_axes((0.0, 0.0, 1.0, 1.0), facecolor=PANEL)
        ax.imshow(rgba, origin="lower", interpolation="bilinear", extent=(-1, 1, -1, 1))
        signed = np.where(mask, img, np.nan)
        ax.contour(
            np.linspace(-1, 1, signed.shape[1]),
            np.linspace(-1, 1, signed.shape[0]),
            signed,
            levels=[0.0],
            colors=[CYAN],
            linewidths=1.1,
            linestyles="solid",
        )
        # the notes themselves, near-side only, in the stills' quiet dots
        cl, sl = np.cos(VIEW_LAT), np.sin(VIEW_LAT)
        co, so = np.cos(view_lon), np.sin(view_lon)
        ez = np.array([cl * co, cl * so, sl])
        ex = np.array([-so, co, 0.0])
        ey = np.cross(ez, ex)
        depth = d["pos"] @ ez
        vis = depth > 0.08
        ax.scatter(d["pos"][vis] @ ex, d["pos"][vis] @ ey, s=2.2, c=TEXT, alpha=0.5, linewidths=0)
        ax.set_xlim(-1.04, 1.04)
        ax.set_ylim(-1.04, 1.04)
        ax.set_axis_off()
        fig.text(0.035, 0.028, caption, color=MUTED, fontsize=8.5)
        fig.savefig(tmp / f"{f:04d}.png", dpi=200, facecolor=BG)
        plt.close(fig)
        if f % 60 == 0:
            print(f"frame {f}/{n_frames}")

    out = e30.ASSETS / "03-the-planet-turns.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            str(tmp / "%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "19",
            str(out),
        ],
        check=True,
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
