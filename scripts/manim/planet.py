"""The E30 planet in motion: one full orbit around the coastline render.

The stills (docs/assets/30-coastlines/) argue the geography; what the orbit
adds is the same thing 13-space-3d bought — parallax. A still sphere cannot
prove the far side exists. Payload from `e30_coastlines.py export`
(scripts/manim/planet.json): tiles with continent tints, coast paths in
lon/lat radians, drawn here at the sphere's surface.

Point count is the cost driver (see space3d.py): every tile is a real sphere
depth-sorted per frame under a moving camera, so tiles render at the coarse
floor resolution and nothing else is meshed.

The invisible anchor carrying a no-op updater is the scene's FIRST mobject —
cairo bakes everything added before the first animated-or-updated mobject
into a static per-play background, which under a rotating camera means a
frozen planet (scripts/manim/flow_pulses.py war story).

    uv run --with manim --with matplotlib manim -ql -r 480,480 \
        --media_dir /tmp/manim scripts/manim/planet.py PlanetTurn   # draft
    uv run --with manim --with matplotlib manim -qh -r 1080,1080 --fps 30 \
        --media_dir /tmp/manim scripts/manim/planet.py PlanetTurn   # post render
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from manim import (
    DEGREES,
    TAU,
    Create,
    Dot,
    Dot3D,
    FadeIn,
    LaggedStart,
    Sphere,
    Text,
    ThreeDScene,
    VGroup,
    VMobject,
    config,
)
from plot_assets import BG, FRAME, MUTED, TEXT

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "planet.json").read_text())

R = 2.25
SEA = "#101016"  # a shade above BG so the body reads against space
ORBIT_SECONDS = 18.0


def lonlat_to_xyz(lon: float, lat: float, r: float) -> np.ndarray:
    return r * np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])


class PlanetTurn(ThreeDScene):
    def construct(self):
        config.background_color = BG

        # cairo guard: the first add must carry an updater (see module docstring)
        anchor = Dot(radius=0.0, fill_opacity=0.0)
        anchor.add_updater(lambda m, dt: m)
        self.add(anchor)

        sea = Sphere(radius=R, resolution=(28, 28), checkerboard_colors=[SEA, SEA])
        sea.set_fill(SEA, opacity=1.0)
        sea.set_stroke(FRAME, width=0.25, opacity=0.35)
        sea.set_shade_in_3d(True)

        coasts = VGroup()
        for seg in DATA["coasts"]:
            # hug the surface: anything floated above R protrudes past the limb
            # on the far side and reads as debris around the silhouette
            pts = np.array([lonlat_to_xyz(lon, lat, R * 1.005) for lon, lat in seg])
            path = VMobject()
            path.set_points_as_corners(pts)
            path.set_stroke(TEXT, width=2.4, opacity=0.95)
            path.set_shade_in_3d(True)
            coasts.add(path)

        tiles = VGroup()
        for xyz, tint in zip(DATA["tiles"], DATA["tints"]):
            p = np.asarray(xyz, dtype=float) * R * 1.003
            tiles.add(Dot3D(point=p, radius=0.019, resolution=(4, 4), color=tint))

        title = Text(
            f"the ytk planet — {DATA['n']} notes, {DATA['continents']} continents, "
            f"coast at {DATA['coast_deg']:.1f}°",
            font="CMU Serif",
            font_size=17,
            color=MUTED,
        )
        title.to_corner(np.array([-1, -1, 0]), buff=0.32)
        self.add_fixed_in_frame_mobjects(title)
        title.set_opacity(0.0)

        self.set_camera_orientation(phi=72 * DEGREES, theta=-30 * DEGREES, zoom=1.6)
        self.begin_ambient_camera_rotation(rate=TAU / ORBIT_SECONDS)

        self.add(sea)
        self.play(
            LaggedStart(
                FadeIn(tiles, run_time=2.0),
                Create(coasts, run_time=2.6, lag_ratio=0.02),
                title.animate.set_opacity(1.0),
                lag_ratio=0.25,
            )
        )
        self.wait(ORBIT_SECONDS - 3.2)
        self.stop_ambient_camera_rotation()
        self.wait(0.4)
