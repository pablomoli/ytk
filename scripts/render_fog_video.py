"""Silent companion clip for the fog figures (docs/assets/01-fog/).

Animates the figure-05 story from the same live data the stills use:
fog condenses, chained walkers draw as broken dashes and dim, traced
strands draw through the same cloud, camera eases in on the web.

    uv run --with manim --with matplotlib manim -ql -r 540,540 \
        scripts/render_fog_video.py FogToStrands          # draft
    uv run --with manim --with matplotlib manim -qh -r 1080,1080 \
        scripts/render_fog_video.py FogToStrands          # post render
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from manim import (
    Create,
    Dot,
    FadeIn,
    LaggedStart,
    MovingCameraScene,
    Square,
    VGroup,
    VMobject,
    config,
    rate_functions,
)

from scripts.plot_assets import BG, GOLD, punch, saturated_magma

MAP = os.path.expanduser("~/.ytk/map.json")
CACHE = os.path.expanduser("~/.ytk/fog-assets-cache.json")

config.background_color = BG

# the stills' exact ramp: saturated magma sampled at punch(den)
_CMAP = saturated_magma()


def fog_color(den: float) -> str:
    r, g, b, _ = _CMAP(float(punch(np.asarray(den))))
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def project(xyz: np.ndarray, elev: float = 30.0, azim: float = -60.0) -> np.ndarray:
    """Orthographic view matching the stills' matplotlib camera."""
    e, a = np.radians(elev), np.radians(azim)
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    sx = -x * np.sin(a) + y * np.cos(a)
    sy = -(x * np.cos(a) + y * np.sin(a)) * np.sin(e) + z * np.cos(e)
    return np.column_stack([sx, sy])


def to_scene(pts2: np.ndarray, span: float = 6.4) -> np.ndarray:
    lo, hi = pts2.min(axis=0), pts2.max(axis=0)
    center, extent = (lo + hi) / 2, (hi - lo).max()
    out = (pts2 - center) / extent * span
    return np.column_stack([out, np.zeros(len(out))])


class FogToStrands(MovingCameraScene):
    def construct(self):
        data = json.loads(open(MAP).read())
        cache = json.loads(open(CACHE).read())

        splats = np.asarray(data["all"]["fog"]["splats"])
        keep = splats[:, 3] >= 0.12
        xyz, den = splats[keep, :3], splats[keep, 3]

        # one shared frame so fog, dashes and strands land in register
        all2 = project(
            np.vstack([xyz] + [np.asarray(f)[:, :3] for f in data["all"]["web"]["filaments"]])
        )
        lo, hi = all2.min(axis=0), all2.max(axis=0)
        center, extent = (lo + hi) / 2, (hi - lo).max()

        def place(p3: np.ndarray) -> np.ndarray:
            p2 = (project(p3) - center) / extent * 7.3
            return np.column_stack([p2, np.zeros(len(p2))])

        rng = np.random.default_rng(7)
        idx = rng.permutation(len(xyz))[:2600]
        fog_pts, fog_den = place(xyz[idx]), den[idx]

        # two layers per splat: wide soft halo under a small core, so the
        # cloud reads as fog like the stills, not as discrete dots
        def splat(p: np.ndarray, d: float) -> VGroup:
            color = fog_color(d)
            halo = Dot(
                point=p,
                radius=0.05 + 0.10 * d,
                color=color,
                fill_opacity=0.05 + 0.10 * d,
                stroke_width=0,
            )
            core = Dot(
                point=p,
                radius=0.010 + 0.038 * d,
                color=color,
                fill_opacity=0.12 + 0.55 * d,
                stroke_width=0,
            )
            return VGroup(halo, core)

        fog = VGroup(*(splat(p, d) for p, d in zip(fog_pts, fog_den)))
        fog.set_z_index(0)

        def strand(vertices: np.ndarray, width: float, opacity: float) -> VGroup:
            core = VMobject(stroke_color=GOLD, stroke_width=width)
            core.set_points_as_corners(place(vertices))
            core.set_stroke(opacity=opacity)
            halo = core.copy().set_stroke(width=width * 2.6, opacity=opacity * 0.22)
            return VGroup(halo, core)

        dashes = VGroup(*(strand(np.asarray(c), 3.0, 0.9) for c in cache["chained"]))
        dashes.set_z_index(2)
        strands = VGroup(
            *(strand(np.asarray(f)[:, :3], 3.6, 0.95) for f in data["all"]["web"]["filaments"])
        )
        strands.set_z_index(3)

        # fog condenses, dim points first, cores land last
        order = np.argsort(fog_den)
        self.play(
            LaggedStart(
                *(FadeIn(fog[int(i)], scale=2.2) for i in order),
                lag_ratio=0.0012,
            ),
            run_time=5,
            rate_func=rate_functions.ease_out_sine,
        )
        self.wait(0.6)

        # bg-colored veil between fog and line work: dims the cloud
        # uniformly (density contrast survives) so the strands read on top
        veil = Square(side_length=13, fill_color=BG, fill_opacity=0.0, stroke_width=0)
        veil.set_z_index(1)
        self.add(veil)

        # the chained attempt: dashes appear, then die down to embers
        self.play(
            LaggedStart(*(Create(d) for d in dashes), lag_ratio=0.06),
            veil.animate.set_fill(opacity=0.3),
            run_time=3.2,
        )
        self.wait(0.8)
        self.play(dashes.animate.set_stroke(opacity=0.12), run_time=1.2)

        # the traced strands walk the ridge through the same fog
        self.play(
            LaggedStart(
                *(Create(s, rate_func=rate_functions.ease_in_out_sine) for s in strands),
                lag_ratio=0.18,
            ),
            run_time=6,
        )

        # settle: embers out, veil deepens, camera eases into the web
        self.play(
            dashes.animate.set_stroke(opacity=0.0),
            veil.animate.set_fill(opacity=0.5),
            self.camera.frame.animate.scale(0.8),
            run_time=3.5,
            rate_func=rate_functions.ease_in_out_sine,
        )
        self.wait(1.5)
