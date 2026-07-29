"""Silent 3D companion clip for the semantic-domains figures (docs/assets/06-semantic-domains/).

The rung's argument in motion: the map's positions were always semantic,
only the labels were provenance. The cloud appears unlabeled, then the
shipped legend ignites bucket by bucket -- an overbright spark at each
slug's core washing radially outward, largest first, leftovers dimming
quietly to grey -- the camera orbits the blobs in 3D, then holds
dead still while the colors crossfade to the garden buckets -- themes
wake up gold, the three hackathon slugs unify, and every note has a home
(rule-unmatched notes are adopted into the nearest bucket by embedding
kNN at map build) -- and only then orbits again before settling onto the stills'
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
    FadeToColor,
    LaggedStart,
    ManimColor,
    MovingCameraScene,
    Succession,
    ValueTracker,
    VGroup,
    config,
    interpolate_color,
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

        # after: the payload's live buckets; kind per label from counts.json
        kind_of = {e["label"]: e["kind"] for e in counts["after_bucketed"]}
        dom_color, dom_kind = [], []
        ti = 0
        for d in domains:
            kind = kind_of.get(d["label"], "other")
            if kind == "path" and d["label"] in AFTER_PATH:
                dom_color.append(ManimColor(AFTER_PATH[d["label"]]))
            elif kind == "theme":
                dom_color.append(ManimColor(WARM[ti % len(WARM)]))
                ti += 1
            else:
                dom_color.append(other_c)
            dom_kind.append(kind)

        rng = np.random.default_rng(7)
        idx = rng.permutation(len(points))[:2600]
        pts_xyz = z3[idx]

        # before-key per dot: the shipped legend's slug via the exact shipped
        # rule, everything else `other`; after-key: the live bucket label
        b_key = []
        for i in idx:
            slug = project_from_path(points[int(i)]["p"])
            b_key.append(slug if slug in BEFORE_PATH else "other")
        a_key = [domains[points[int(i)]["dom"]]["label"] for i in idx]
        b_cols = [slug_color.get(k, other_c) for k in b_key]
        a_cols = [dom_color[points[int(i)]["dom"]] for i in idx]

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

        white_c = ManimColor("#ffffff")

        def ignition(members: list[int], color: ManimColor) -> LaggedStart:
            """One bucket lights up: overbright spark washing radially out
            from the bucket's core, settling into its color."""
            centroid = pts_xyz[members].mean(axis=0)
            radial = sorted(members, key=lambda i: float(np.sum((pts_xyz[i] - centroid) ** 2)))
            spark = interpolate_color(color, white_c, 0.6)
            return LaggedStart(
                *(
                    Succession(FadeToColor(cloud[i], spark), FadeToColor(cloud[i], color))
                    for i in radial
                ),
                lag_ratio=2.0 / max(len(radial), 1),
            )

        # roll call: each slug ignites as a group, largest first...
        members_of: dict[str, list[int]] = {}
        for row, k in enumerate(b_key):
            members_of.setdefault(k, []).append(row)
        slugs = sorted(
            (k for k in members_of if k != "other"),
            key=lambda k: -len(members_of[k]),
        )
        self.play(
            LaggedStart(
                *(ignition(members_of[k], slug_color[k]) for k in slugs),
                lag_ratio=0.3,
            ),
            run_time=4.6,
        )
        # ...and the leftovers dim quietly to grey -- the residue, unannounced
        self.play(
            *(FadeToColor(cloud[i], other_c) for i in members_of.get("other", [])),
            run_time=0.9,
        )
        self.wait(0.4)

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

        # the swap, camera dead still: identical layout, new membership,
        # delivered per destination bucket -- the merges pulse first, the
        # grey mass catches fire, and the warm theme buckets close the show
        changed_of: dict[str, list[int]] = {}
        for row, (b, a) in enumerate(zip(b_cols, a_cols)):
            if str(b) != str(a):
                changed_of.setdefault(a_key[row], []).append(row)
        dom_color_of = {d["label"]: c for d, c in zip(domains, dom_color)}
        dom_kind_of = {d["label"]: k for d, k in zip(domains, dom_kind)}
        dests = sorted(
            changed_of,
            key=lambda k: (dom_kind_of.get(k) == "theme", -len(changed_of[k])),
        )
        self.play(
            LaggedStart(
                *(ignition(changed_of[k], dom_color_of[k]) for k in dests),
                lag_ratio=0.25,
            ),
            run_time=4.6,
        )
        self.wait(0.6)

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
