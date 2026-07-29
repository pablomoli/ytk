"""Silent 3D companion clip for the flow-pulses figures (docs/assets/03-flow-pulses/).

The stills freeze four instants of the same web because a PNG cannot show
motion -- this clip shows the thing itself. The 8 traced filaments carry
the shader's exact brightness wave, brightness = 0.65 + 0.35*sin(arclen*18
- time*4.5), the light freezes for a beat (the geometry never moves; only
the light travels), then the camera orbits the pulsing web and settles
onto the stills' matplotlib view (elev 30, azim -60).

Geometry, arclengths and per-vertex density come from the live map
payload; palette from plot_assets so the clip cannot drift from the
stills. Billboard reprojection from tracked view angles, same machinery
as scripts/render_fog_video.py.

    uv run --with manim --with matplotlib manim -ql -r 540,540 \
        scripts/manim/flow_pulses.py FlowPulses           # draft
    uv run --with manim --with matplotlib manim -qh -r 1080,1080 --fps 30 \
        scripts/manim/flow_pulses.py FlowPulses           # post render
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from manim import (
    Dot,
    FadeIn,
    LaggedStart,
    ManimColor,
    MovingCameraScene,
    Square,
    ValueTracker,
    VGroup,
    VMobject,
    config,
    interpolate_color,
    rate_functions,
)

from scripts.plot_assets import BG, GOLD, PURPLE, punch, saturated_magma

MAP = os.path.expanduser("~/.ytk/map.json")

config.background_color = BG

_CMAP = saturated_magma()

# the stills' matplotlib camera; the clip ends on this view
STILL_ELEV, STILL_AZIM = 30.0, -60.0

# the shader's dials, verbatim from the figure-02 header
WAVELEN_K, SPEED = 18.0, 4.5

PEAK = "#fff3d0"  # pulse crest; trough stays gold


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


class FlowPulses(MovingCameraScene):
    def construct(self):
        data = json.loads(open(MAP).read())

        splats = np.asarray(data["all"]["fog"]["splats"])
        keep = splats[:, 3] >= 0.12
        xyz, den = splats[keep, :3], splats[keep, 3]

        # filament columns: x, y, z, cumulative arclength, density
        fils = [np.asarray(f) for f in data["all"]["web"]["filaments"]]

        c3 = (xyz.min(axis=0) + xyz.max(axis=0)) / 2
        ref = project(xyz - c3, STILL_ELEV, STILL_AZIM)
        scale = 6.8 / (ref.max(axis=0) - ref.min(axis=0)).max()

        elev, azim = ValueTracker(STILL_ELEV), ValueTracker(STILL_AZIM)
        clock = ValueTracker(0.0)

        def place(p3: np.ndarray) -> np.ndarray:
            return project(p3 - c3, elev.get_value(), azim.get_value()) * scale

        rng = np.random.default_rng(7)
        idx = rng.permutation(len(xyz))[:1500]
        fog_xyz, fog_den = xyz[idx], den[idx]

        def splat(p: np.ndarray, d: float) -> Dot:
            return Dot(
                point=p,
                radius=0.012 + 0.05 * d,
                color=fog_color(d),
                fill_opacity=0.08 + 0.38 * d,
                stroke_width=0,
            )

        fog = VGroup(*(splat(p, d) for p, d in zip(place(fog_xyz), fog_den)))
        fog.set_z_index(0)

        # strands as short segments so the brightness wave resolves along
        # the arc; stride 2 keeps the count near 500 across all 8 strands
        seg_xyz, seg_arc, seg_w, seg_mobs = [], [], [], []
        for f in fils:
            for i in range(0, len(f) - 2, 2):
                pair = f[i : i + 3 : 2, :3]
                arc = float(f[i : i + 3 : 2, 3].mean())
                d = float(f[i : i + 3 : 2, 4].mean())
                w = 2.8 + 2.8 * d
                seg = VMobject(stroke_color=GOLD, stroke_width=w)
                seg.set_points_as_corners(place(pair))
                seg.set_stroke(opacity=0.55)
                seg_xyz.append(pair)
                seg_arc.append(arc)
                seg_w.append(w)
                seg_mobs.append(seg)
        strands = VGroup(*seg_mobs)
        strands.set_z_index(2)

        veil = Square(side_length=13, fill_color=BG, fill_opacity=0.28, stroke_width=0)
        veil.set_z_index(1)

        purple_c, gold_c, peak_c = ManimColor(PURPLE), ManimColor(GOLD), ManimColor(PEAK)

        # one combined updater: reproject from the tracked angles and light
        # every segment from the tracked clock -- attached to an anchor that
        # is IN the scene (updaters never run on off-scene mobjects)
        def refresh(_=None):
            t = clock.get_value()
            for grp, p in zip(fog, place(fog_xyz)):
                grp.move_to(p)
            for seg, pair, arc, w in zip(seg_mobs, seg_xyz, seg_arc, seg_w):
                seg.set_points_as_corners(place(pair))
                b = 0.65 + 0.35 * np.sin(arc * WAVELEN_K - t * SPEED)
                # the stills' look: purple troughs, gold body, cream crests
                u = (b - 0.3) / 0.7
                if u < 0.5:
                    color = interpolate_color(purple_c, gold_c, u * 2)
                else:
                    color = interpolate_color(gold_c, peak_c, u * 2 - 1)
                seg.set_stroke(color=color, opacity=0.3 + 0.7 * u, width=w * (0.7 + 0.8 * u))

        anchor = Dot(fill_opacity=0.0, stroke_width=0)

        # the web appears with the light off: fog first, then the strands
        self.play(
            LaggedStart(*(FadeIn(m, scale=1.8) for m in fog), lag_ratio=0.0015),
            run_time=2.6,
            rate_func=rate_functions.ease_out_sine,
        )
        self.add(veil)
        self.play(
            LaggedStart(*(FadeIn(s) for s in seg_mobs), lag_ratio=0.004),
            run_time=2.4,
        )

        self.add(anchor)
        anchor.add_updater(refresh)

        # ignition: the light starts to travel, geometry and camera held
        self.play(clock.animate.increment_value(3.2), run_time=3.2, rate_func=rate_functions.linear)

        # the A-B beat from the stills, in time: the light freezes...
        self.wait(1.2)

        # ...and resumes, and the camera starts to orbit the pulsing web
        self.play(
            clock.animate.increment_value(6.5),
            elev.animate.increment_value(16),
            azim.animate.increment_value(110),
            run_time=6.5,
            rate_func=rate_functions.linear,
        )

        # settle back onto the stills' view, light still traveling
        self.play(
            clock.animate.increment_value(4.5),
            elev.animate.set_value(STILL_ELEV),
            azim.animate.set_value(STILL_AZIM),
            self.camera.frame.animate.scale(0.84),
            run_time=4.5,
            rate_func=rate_functions.ease_in_out_sine,
        )

        # hold: pulses keep running on the canonical view
        self.play(clock.animate.increment_value(2.5), run_time=2.5, rate_func=rate_functions.linear)
        anchor.remove_updater(refresh)
