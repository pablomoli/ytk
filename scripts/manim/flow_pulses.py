"""Silent 3D companion clip for the flow-pulses figures (docs/assets/03-flow-pulses/).

The stills freeze four instants of the same web because a PNG cannot show
motion -- this clip shows the thing itself. Light is emitted from the
web's 4 junction nodes and travels outward along each strand as soft
packets (two offset trains per node, amplitude decaying with distance,
purple troughs to cream crests), the light freezes for a beat (the
geometry never moves; only the light travels), then the camera orbits
the pulsing web and settles onto the stills' matplotlib view (elev 30,
azim -60).

Geometry, arclengths, per-vertex density and junction positions come
from the live map payload; palette from plot_assets so the clip cannot
drift from the stills. Billboard reprojection from tracked view angles,
same machinery as scripts/render_fog_video.py.

The invisible anchor that carries the per-frame updater is added to the
scene BEFORE anything else, deliberately: manim's cairo renderer bakes
every mobject listed before the first animated-or-updated one into a
static background image per play, so an anchor added last freezes
everything added before it (measured -- the fog held still through a
110-degree orbit while the strands turned).

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

PEAK = "#fff3d0"  # pulse crest

# pulse train dials, in payload arclength units per second
PULSE_SPEED = 0.55
PULSE_PERIOD = 2.6
PULSE_SIGMA = 0.17
PULSE_DECAY = 3.5  # amplitude e-folding distance from the emitting node


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
        junctions = np.asarray(data["all"]["web"]["junctions"])

        c3 = (xyz.min(axis=0) + xyz.max(axis=0)) / 2
        ref = project(xyz - c3, STILL_ELEV, STILL_AZIM)
        scale = 6.8 / (ref.max(axis=0) - ref.min(axis=0)).max()

        elev, azim = ValueTracker(STILL_ELEV), ValueTracker(STILL_AZIM)
        clock = ValueTracker(0.0)

        def place(p3: np.ndarray) -> np.ndarray:
            return project(p3 - c3, elev.get_value(), azim.get_value()) * scale

        # the anchor carrying the updater must be the FIRST scene mobject
        # (see module docstring); everything added after it re-renders
        anchor = Dot(fill_opacity=0.0, stroke_width=0)
        self.add(anchor)

        rng = np.random.default_rng(7)
        idx = rng.permutation(len(xyz))[:1500]
        fog_xyz, fog_den = xyz[idx], den[idx]

        # two layers per splat, same recipe as the fog clip, so the points
        # render identically across the series
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

        # per strand: arclengths of the vertices a junction sits on; every
        # strand gets at least its nearest-to-a-junction vertex as source
        def sources_for(f: np.ndarray) -> np.ndarray:
            verts, arcs = f[:, :3], f[:, 3]
            d2 = ((verts[:, None, :] - junctions[None, :, :]) ** 2).sum(axis=2)
            near = d2.min(axis=1)
            hits = arcs[near < 0.05**2]
            if len(hits) == 0:
                hits = arcs[[int(near.argmin())]]
            return np.unique(hits.round(3))

        # strands as short segments so the packets resolve along the arc
        seg_mobs, seg_xyz, seg_dist, seg_phase, seg_w = [], [], [], [], []
        for s_i, f in enumerate(fils):
            srcs = sources_for(f)
            phase = float(rng.uniform(0, PULSE_PERIOD))
            for i in range(0, len(f) - 2, 2):
                pair = f[i : i + 3 : 2, :3]
                arc = float(f[i : i + 3 : 2, 3].mean())
                d = float(f[i : i + 3 : 2, 4].mean())
                w = 2.8 + 2.8 * d
                seg = VMobject(stroke_color=GOLD, stroke_width=w)
                seg.set_points_as_corners(place(pair))
                seg.set_stroke(opacity=0.4)
                seg_mobs.append(seg)
                seg_xyz.append(pair)
                seg_dist.append(float(np.abs(arc - srcs).min()))
                seg_phase.append(phase)
                seg_w.append(w)
        strands = VGroup(*seg_mobs)
        strands.set_z_index(2)

        veil = Square(side_length=13, fill_color=BG, fill_opacity=0.28, stroke_width=0)
        veil.set_z_index(1)

        purple_c, gold_c, peak_c = ManimColor(PURPLE), ManimColor(GOLD), ManimColor(PEAK)
        dist_a = np.asarray(seg_dist)
        phase_a = np.asarray(seg_phase)
        w_a = np.asarray(seg_w)
        decay = np.exp(-dist_a / PULSE_DECAY)

        def brightness(t: float) -> np.ndarray:
            # two offset packet trains per node: the second at half strength
            # a half-period later reads as a heartbeat rather than a strobe
            b = np.full_like(dist_a, 0.22)
            for amp, off in ((0.85, 0.0), (0.45, PULSE_PERIOD / 2)):
                front = ((t + phase_a + off) % PULSE_PERIOD) * PULSE_SPEED
                b += amp * decay * np.exp(-(((dist_a - front) / PULSE_SIGMA) ** 2))
            return np.clip(b, 0.0, 1.0)

        def refresh(_=None):
            t = clock.get_value()
            for grp, p in zip(fog, place(fog_xyz)):
                grp.move_to(p)
            bs = brightness(t)
            for seg, pair, b, w in zip(seg_mobs, seg_xyz, bs, w_a):
                seg.set_points_as_corners(place(pair))
                if b < 0.5:
                    color = interpolate_color(purple_c, gold_c, b * 2)
                else:
                    color = interpolate_color(gold_c, peak_c, b * 2 - 1)
                seg.set_stroke(color=color, opacity=0.28 + 0.72 * b, width=w * (0.65 + 0.9 * b))

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

        anchor.add_updater(refresh)

        # ignition: packets leave the crossroads, geometry and camera held
        self.play(clock.animate.increment_value(3.4), run_time=3.4, rate_func=rate_functions.linear)

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

        # hold: the heartbeat keeps running on the canonical view
        self.play(clock.animate.increment_value(2.6), run_time=2.6, rate_func=rate_functions.linear)
        anchor.remove_updater(refresh)
