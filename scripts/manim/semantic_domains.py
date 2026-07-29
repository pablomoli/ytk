"""Silent 3D companion clip for the semantic-domains figures (docs/assets/06-semantic-domains/).

The rung's argument in motion: the map's positions were always semantic,
only the labels were provenance. The cloud appears unlabeled, the
shipped legend's colors sweep in (blue = path slugs, grey = `other`,
figure-01's encoding), the camera orbits the blobs in 3D, then holds
dead still while the colors crossfade to the garden buckets -- themes
wake up gold, the three hackathon slugs unify, a third of the map goes
grey -- and only then orbits again before settling onto the stills'
matplotlib view (elev 30, azim -60). The held camera is the point: the
layout is visibly identical through the swap, so the change can only be
membership, never projection (same device as 13-space-3d/TagInSpace).

Before-labels are computed per point with the exact shipped rule,
ytk.mapdomains.project_from_path, on each point's vault path; the two
legacy theme groups of the old legend (97 notes, ~2%) are folded into
`other`. After-labels are the payload's live `dom` indices; each
bucket's kind (path/theme/other) is read from the rung's counts.json.

The invisible anchor carrying the reprojection updater is the scene's
FIRST mobject -- manim's cairo renderer bakes everything listed before
the first animated-or-updated mobject into a static per-play background
(see scripts/manim/flow_pulses.py, where the fog froze mid-orbit).

    uv run --with manim --with matplotlib manim -ql -r 540,540 \
        scripts/manim/semantic_domains.py SemanticDomains  # draft
    uv run --with manim --with matplotlib manim -qh -r 1080,1080 --fps 30 \
        scripts/manim/semantic_domains.py SemanticDomains  # post render
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
    ValueTracker,
    VGroup,
    config,
    rate_functions,
)

from scripts.plot_assets import BG
from ytk.mapdomains import project_from_path

MAP = os.path.expanduser("~/.ytk/map.json")
COUNTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "assets",
    "06-semantic-domains",
    "counts.json",
)

config.background_color = BG

STILL_ELEV, STILL_AZIM = 30.0, -60.0

NEUTRAL = "#242428"  # the unlabeled cloud
OTHER = "#5c5c66"  # other/unplaced -- visibly grey, not background-black

# cool family = path groups, warm family = themes (figure-01's kinds, with
# hue separation the stills' single blue/gold could not afford). epicmap
# keeps one hue through the swap because its membership does not change;
# niloc/usf/hacklytics visibly collapse into the one hackathons hue.
BEFORE_PATH = {
    "epicmap": "#5a8cff",
    "niloc": "#7fd4ff",
    "usf": "#4fd8b8",
    "hacklytics-goldenbyte": "#6a6afc",
    "ytk": "#9159ff",
    "config": "#8ea8d8",
}
AFTER_PATH = {
    "epicmap": "#5a8cff",
    "hackathons": "#7fd4ff",
    "ai-building": "#9159ff",
    "visual-craft": "#4fd8b8",
    "youtube-channel": "#8ea8d8",
}
WARM = ("#f2b950", "#ffd98a", "#e8975f", "#fff3d0", "#ffb26b")


def project(xyz: np.ndarray, elev: float, azim: float) -> np.ndarray:
    """Orthographic view, same convention as matplotlib's 3d axes."""
    e, a = np.radians(elev), np.radians(azim)
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    sx = -x * np.sin(a) + y * np.cos(a)
    sy = -(x * np.cos(a) + y * np.sin(a)) * np.sin(e) + z * np.cos(e)
    return np.column_stack([sx, sy, np.zeros(len(x))])


class SemanticDomains(MovingCameraScene):
    def construct(self):
        data = json.loads(open(MAP).read())
        counts = json.loads(open(COUNTS).read())
        points = data["points"]
        domains = data["all"]["domains"]

        z3 = np.array([p["z3"] for p in points])
        c3 = (z3.min(axis=0) + z3.max(axis=0)) / 2
        ref = project(z3 - c3, STILL_ELEV, STILL_AZIM)
        scale = 6.8 / (ref.max(axis=0) - ref.min(axis=0)).max()

        elev, azim = ValueTracker(STILL_ELEV), ValueTracker(STILL_AZIM)

        def place(p3: np.ndarray) -> np.ndarray:
            return project(p3 - c3, elev.get_value(), azim.get_value()) * scale

        other_c = ManimColor(OTHER)
        slug_color = {s: ManimColor(c) for s, c in BEFORE_PATH.items()}

        # before: the shipped legend's path slugs via the exact shipped rule
        def before_color(path: str) -> ManimColor:
            slug = project_from_path(path)
            return slug_color.get(slug, other_c)

        # after: the payload's live buckets; kind per label from counts.json
        kind_of = {e["label"]: e["kind"] for e in counts["after_bucketed"]}
        after_colors = []
        ti = 0
        for d in domains:
            kind = kind_of.get(d["label"], "other")
            if kind == "path" and d["label"] in AFTER_PATH:
                after_colors.append(ManimColor(AFTER_PATH[d["label"]]))
            elif kind == "theme":
                after_colors.append(ManimColor(WARM[ti % len(WARM)]))
                ti += 1
            else:
                after_colors.append(other_c)

        rng = np.random.default_rng(7)
        idx = rng.permutation(len(points))[:2600]
        pts_xyz = z3[idx]
        b_cols = [before_color(points[int(i)]["p"]) for i in idx]
        a_cols = [after_colors[points[int(i)]["dom"]] for i in idx]

        # the anchor carrying the updater must be the FIRST scene mobject
        anchor = Dot(fill_opacity=0.0, stroke_width=0)
        self.add(anchor)

        neutral_c = ManimColor(NEUTRAL)

        def splat(p: np.ndarray) -> VGroup:
            halo = Dot(point=p, radius=0.055, color=neutral_c, fill_opacity=0.11, stroke_width=0)
            core = Dot(point=p, radius=0.024, color=neutral_c, fill_opacity=0.78, stroke_width=0)
            return VGroup(halo, core)

        cloud = VGroup(*(splat(p) for p in place(pts_xyz)))

        def refresh(_=None):
            for grp, p in zip(cloud, place(pts_xyz)):
                grp.move_to(p)

        # the unlabeled cloud condenses on the canonical view
        self.play(
            LaggedStart(*(FadeIn(m, scale=1.8) for m in cloud), lag_ratio=0.0012),
            run_time=2.4,
            rate_func=rate_functions.ease_out_sine,
        )

        # the shipped legend sweeps in left-to-right: blue slugs, grey other
        order = np.argsort([m.get_center()[0] for m in cloud])
        self.play(
            LaggedStart(
                *(cloud[int(i)].animate.set_fill(color=b_cols[int(i)]) for i in order),
                lag_ratio=0.0012,
            ),
            run_time=2.4,
        )
        self.wait(0.5)

        # orbit the provenance blobs
        anchor.add_updater(refresh)
        self.play(
            elev.animate.increment_value(14),
            azim.animate.increment_value(100),
            run_time=5.0,
            rate_func=rate_functions.ease_in_out_sine,
        )
        anchor.remove_updater(refresh)
        self.wait(0.5)

        # the swap, camera dead still: identical layout, new membership
        self.play(
            *(m.animate.set_fill(color=c) for m, c in zip(cloud, a_cols)),
            run_time=1.8,
            rate_func=rate_functions.ease_in_out_sine,
        )
        self.wait(0.7)

        # orbit the buckets home and settle onto the stills' view
        anchor.add_updater(refresh)
        self.play(
            elev.animate.set_value(STILL_ELEV),
            azim.animate.set_value(STILL_AZIM),
            self.camera.frame.animate.scale(0.84),
            run_time=5.0,
            rate_func=rate_functions.ease_in_out_sine,
        )
        anchor.remove_updater(refresh)
        self.wait(1.3)
