"""Silent companion clip for the fog figures (docs/assets/01-fog/).

Animates the figure-05 story from the same live data the stills use,
in 3D: the fog condenses, the camera orbits the cloud, chained walkers
draw as broken dashes and dim, traced strands draw through the same
cloud, and the camera settles onto the stills' exact matplotlib view
(elev 30, azim -60) -- the video ends where the figures begin.

Dots are orthographic billboards reprojected per frame from tracked
view angles; far cheaper than sphere meshes, and it matches how the
stills' matplotlib scatters read.

    uv run --with manim --with matplotlib manim -ql -r 540,540 \
        scripts/render_fog_video.py FogToStrands          # draft
    uv run --with manim --with matplotlib manim -qh -r 1080,1080 --fps 30 \
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
    ValueTracker,
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

# the stills' matplotlib camera; the clip ends on this view
STILL_ELEV, STILL_AZIM = 30.0, -60.0


def fog_color(den: float) -> str:
    r, g, b, _ = _CMAP(float(punch(np.asarray(den))))
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def project(xyz: np.ndarray, elev: float, azim: float) -> np.ndarray:
    """Orthographic view, same convention as matplotlib's 3d axes."""
    e, a = np.radians(elev), np.radians(azim)
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    sx = -x * np.sin(a) + y * np.cos(a)
    sy = -(x * np.cos(a) + y * np.sin(a)) * np.sin(e) + z * np.cos(e)
    return np.column_stack([sx, sy, np.zeros(len(x))])


class FogToStrands(MovingCameraScene):
    def construct(self):
        data = json.loads(open(MAP).read())
        cache = json.loads(open(CACHE).read())

        splats = np.asarray(data["all"]["fog"]["splats"])
        keep = splats[:, 3] >= 0.12
        xyz, den = splats[keep, :3], splats[keep, 3]

        strand_data = [np.asarray(f)[:, :3] for f in data["all"]["web"]["filaments"]]
        dash_data = [np.asarray(c) for c in cache["chained"]]

        # centre the 3d data once; a centred cloud stays centred under any
        # orthographic view, so panning cannot drift it off frame
        c3 = (xyz.min(axis=0) + xyz.max(axis=0)) / 2
        ref = project(xyz - c3, STILL_ELEV, STILL_AZIM)
        scale = 6.8 / (ref.max(axis=0) - ref.min(axis=0)).max()

        elev, azim = ValueTracker(38.0), ValueTracker(-135.0)

        def place(p3: np.ndarray) -> np.ndarray:
            return project(p3 - c3, elev.get_value(), azim.get_value()) * scale

        rng = np.random.default_rng(7)
        idx = rng.permutation(len(xyz))[:2600]
        fog_xyz, fog_den = xyz[idx], den[idx]

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

        fog = VGroup(*(splat(p, d) for p, d in zip(place(fog_xyz), fog_den)))
        fog.set_z_index(0)

        def strand(vertices: np.ndarray, width: float, opacity: float) -> VGroup:
            core = VMobject(stroke_color=GOLD, stroke_width=width)
            core.set_points_as_corners(place(vertices))
            core.set_stroke(opacity=opacity)
            halo = core.copy().set_stroke(width=width * 2.6, opacity=opacity * 0.22)
            return VGroup(halo, core)

        dashes = VGroup(*(strand(c, 3.0, 0.9) for c in dash_data))
        dashes.set_z_index(2)
        strands = VGroup(*(strand(f, 3.6, 0.95) for f in strand_data))
        strands.set_z_index(3)

        # reproject everything from the tracked angles; attached only while
        # the camera moves so Create() phases animate undisturbed
        def refresh(_=None):
            for grp, p in zip(fog, place(fog_xyz)):
                grp.move_to(p)
            for group, source in ((dashes, dash_data), (strands, strand_data)):
                for vg, verts in zip(group, source):
                    pts = place(verts)
                    for layer in vg:
                        layer.set_points_as_corners(pts)

        world = VGroup(fog, dashes, strands)

        def orbit(d_elev: float, d_azim: float, run_time: float):
            world.add_updater(refresh)
            self.play(
                elev.animate.increment_value(d_elev),
                azim.animate.increment_value(d_azim),
                run_time=run_time,
                rate_func=rate_functions.ease_in_out_sine,
            )
            world.remove_updater(refresh)

        # fog condenses, dim points first, cores land last
        order = np.argsort(fog_den)
        self.play(
            LaggedStart(
                *(FadeIn(fog[int(i)], scale=2.2) for i in order),
                lag_ratio=0.0012,
            ),
            run_time=4.5,
            rate_func=rate_functions.ease_out_sine,
        )

        # the reveal pan: the flat picture turns out to be a volume
        orbit(d_elev=14, d_azim=95, run_time=4.5)

        # bg-colored veil between fog and line work: dims the cloud
        # uniformly (density contrast survives) so the strands read on top
        veil = Square(side_length=13, fill_color=BG, fill_opacity=0.0, stroke_width=0)
        veil.set_z_index(1)
        self.add(veil)

        # the chained attempt: dashes appear, then die down to embers
        refresh()
        self.play(
            LaggedStart(*(Create(d) for d in dashes), lag_ratio=0.06),
            veil.animate.set_fill(opacity=0.3),
            run_time=3.0,
        )
        self.wait(0.6)
        self.play(dashes.animate.set_stroke(opacity=0.12), run_time=1.0)

        # swing back with the embers in tow
        orbit(d_elev=-10, d_azim=-55, run_time=2.5)

        # the traced strands walk the ridge through the same fog
        refresh()
        self.play(
            LaggedStart(
                *(Create(s, rate_func=rate_functions.ease_in_out_sine) for s in strands),
                lag_ratio=0.18,
            ),
            run_time=5.5,
        )

        # arrival: settle onto the stills' exact view -- the projection the
        # figures show -- embers out, veil deepens, camera eases in
        world.add_updater(refresh)
        self.play(
            elev.animate.set_value(STILL_ELEV),
            azim.animate.set_value(STILL_AZIM),
            dashes.animate.set_stroke(opacity=0.0),
            veil.animate.set_fill(opacity=0.5),
            self.camera.frame.animate.scale(0.8),
            run_time=4.0,
            rate_func=rate_functions.ease_in_out_sine,
        )
        world.remove_updater(refresh)
        self.wait(1.5)
