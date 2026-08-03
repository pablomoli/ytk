"""The plane of two documents, with the camera moving.

    ShadowPlane  -- a plane through two notes, and what every other note's
                    shadow on it is actually worth

Companion to the stills in docs/assets/15-plane-geometry. The stills answer
"how much of each note survives the projection" with numbers; this answers
"why" with parallax. A 2D scatter cannot show the one thing that matters here,
which is the direction the cloud sits in relative to the plane it is being
flattened onto.

STAND-IN, stated plainly: the scene is three of the corpus's 1024 dimensions —
the cone basis (mean direction, then the top two residual directions) — so the
plane you see is the 3D shadow of the real plane, and shadow lengths on screen
are 3D lengths. Every number in the captions is measured in the full 1024
dimensions by scripts/plot_plane.py. Same data, same palette as the stills.

Render (ephemeral env, nothing installed system-wide):

    uv run --with manim manim -qm --media_dir /tmp/manim \\
        scripts/manim/plane.py ShadowPlane
    cp /tmp/manim/videos/plane/720p30/*.mp4 docs/assets/15-plane-geometry/

Cost is point count, as in space3d.py: every dot is a sphere manim re-sorts by
depth on every frame. Background is subsampled (SUBSAMPLE), shadow lines are
drawn for a smaller seeded subset (SHADOWS) because each one is a stroke that
also re-sorts. Both subsamples are seeded, so the same notes drop every run.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from manim import (
    DEGREES,
    DOWN,
    RIGHT,
    UP,
    Create,
    Dot3D,
    FadeIn,
    FadeOut,
    Line,
    Line3D,
    Polygon,
    Text,
    ThreeDAxes,
    ThreeDScene,
    Transform,
    VGroup,
    Write,
    config,
)

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "plane3d.json").read_text())

SUBSAMPLE = 190
SHADOWS = 46
RES = (4, 4)  # sphere facets; 4x4 is the floor before dots read as diamonds

BG = "#08080a"
GOLD = "#f2b950"
CYAN = "#7fd4ff"
RED = "#ff4d6d"
BLUE = "#5a8cff"
TEXT = "#eceae7"
MUTED = "#9a968f"
DIM = "#3a3a42"

config.background_color = BG

# manimpango's fallback font swallows spaces at these sizes -- captions render
# as "theorigin". Naming a font fixes it (space3d.py:80).
FONT = "Helvetica Neue"


def _seeded(n: int, size: int) -> np.ndarray:
    rng = np.random.default_rng(DATA["seed"])
    return np.sort(rng.choice(n, size=min(size, n), replace=False))


def _axes(rng: float = 1.15) -> ThreeDAxes:
    ax = ThreeDAxes(
        x_range=[-rng, rng, rng / 2],
        y_range=[-rng, rng, rng / 2],
        z_range=[-rng, rng, rng / 2],
        x_length=6.4,
        y_length=6.4,
        z_length=6.4,
    )
    ax.set_color(DIM)
    ax.set_stroke(width=1.6, opacity=0.75)
    for tip in (ax.get_x_axis().tip, ax.get_y_axis().tip, ax.get_z_axis().tip):
        tip.set_fill(color=DIM, opacity=0.9).set_stroke(width=0)
        tip.scale(0.55)
    return ax


def _caption(scene: ThreeDScene, *lines: str) -> VGroup:
    g = VGroup()
    for i, s in enumerate(lines):
        g.add(Text(s, font=FONT, font_size=26 if i == 0 else 20, color=TEXT if i == 0 else MUTED))
    g.arrange(DOWN, buff=0.18)
    g.to_corner(UP + RIGHT, buff=0.45)
    scene.add_fixed_in_frame_mobjects(g)
    return g


def _frame(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Orthonormal 2-frame for the plane's 3D shadow.

    plane_u and plane_v are unit vectors in 1024 dimensions; their images in
    this 3-subspace are neither unit nor orthogonal, so they are re-framed here
    rather than drawn as-is.
    """
    e1 = u / np.linalg.norm(u)
    r = v - (v @ e1) * e1
    return np.vstack([e1, r / np.linalg.norm(r)])


class ShadowPlane(ThreeDScene):
    """A plane through two notes, and what the other 491 shadows are worth."""

    def construct(self) -> None:
        cone = np.array(DATA["cone"])
        cen = np.array(DATA["centred"])
        i, j = DATA["pair"]
        keep = _seeded(len(cone), SUBSAMPLE)
        keep = np.array([k for k in keep if k not in (i, j)])
        shadow_idx = keep[:: max(1, len(keep) // SHADOWS)][:SHADOWS]

        # each cloud scaled to its own extent, as in space3d.TheCone: the raw
        # and centred clouds live at different radii and a shared scale would
        # render the comparison as a size change rather than a position change
        def fit(A):
            return A / (np.abs(A).max() * 1.05)

        P, Pc = fit(cone), fit(cen)
        B = _frame(np.array(DATA["plane_u"]), np.array(DATA["plane_v"]))
        proj = lambda A: (A @ B.T) @ B

        self.set_camera_orientation(phi=72 * DEGREES, theta=-58 * DEGREES, zoom=1.0)
        axes = _axes()
        self.add(axes)
        c2p = axes.c2p

        stand_in = Text(
            "3 of 1024 dimensions · numbers measured in all 1024",
            font=FONT,
            font_size=17,
            color=DIM,
        ).to_corner(DOWN + RIGHT, buff=0.4)
        self.add_fixed_in_frame_mobjects(stand_in)

        origin = Dot3D(point=c2p(0, 0, 0), radius=0.075, color=RED, resolution=(8, 8))
        self.play(FadeIn(origin), run_time=0.8)

        cap = _caption(self, "the vault, as stored", f"{len(keep)} of 493 notes")
        cloud = VGroup(
            *[Dot3D(point=c2p(*P[k]), radius=0.036, color=DIM, resolution=RES) for k in keep]
        )
        self.play(FadeIn(cloud, lag_ratio=0.004), Write(cap[0]), run_time=2.4)
        self.play(FadeIn(cap[1]), run_time=0.5)

        # the two notes that will define the plane
        a_dot = Dot3D(point=c2p(*P[i]), radius=0.075, color=GOLD, resolution=(8, 8))
        b_dot = Dot3D(point=c2p(*P[j]), radius=0.075, color=GOLD, resolution=(8, 8))
        a_arm = Line3D(start=c2p(0, 0, 0), end=c2p(*P[i]), color=GOLD, thickness=0.016)
        b_arm = Line3D(start=c2p(0, 0, 0), end=c2p(*P[j]), color=GOLD, thickness=0.016)
        cap2 = _caption(self, "two notes span a plane", "a coding interview and a heatmap")
        self.play(
            FadeOut(cap),
            FadeIn(cap2),
            FadeIn(a_dot),
            FadeIn(b_dot),
            Create(a_arm),
            Create(b_arm),
            run_time=1.8,
        )

        # the plane itself: a square patch of span(u, v) through the origin
        s = 1.05
        corners = [c2p(*(su * B[0] + sv * B[1])) for su, sv in ((s, s), (-s, s), (-s, -s), (s, -s))]
        plane = Polygon(*corners, color=CYAN, fill_color=CYAN, fill_opacity=0.13, stroke_width=1.4)
        plane.set_shade_in_3d(True)
        self.play(Create(plane), run_time=1.6)

        self.begin_ambient_camera_rotation(rate=0.30)
        self.wait(4)

        # every note's shadow on that plane
        S = proj(P)
        shadows = VGroup(
            *[Dot3D(point=c2p(*S[k]), radius=0.030, color=CYAN, resolution=RES) for k in shadow_idx]
        )
        drops = VGroup(
            *[
                Line(c2p(*P[k]), c2p(*S[k]), color=MUTED, stroke_width=1.1, stroke_opacity=0.55)
                for k in shadow_idx
            ]
        )
        drops.set_shade_in_3d(True)
        cap3 = _caption(
            self,
            "every note casts a long shadow",
            "median 0.370 of its length survives — chance is 0.044",
        )
        self.play(FadeOut(cap2), FadeIn(cap3), run_time=0.8)
        self.play(Create(drops, lag_ratio=0.02), FadeIn(shadows, lag_ratio=0.02), run_time=2.6)
        self.wait(5)

        # subtract the shared direction; same plane, same camera
        Sc = proj(Pc)
        cap4 = _caption(
            self,
            "subtract the shared direction",
            "the same plane now keeps 0.088 — twice chance, not eight times",
        )
        self.play(
            FadeOut(cap3),
            FadeIn(cap4),
            Transform(
                cloud,
                VGroup(
                    *[
                        Dot3D(point=c2p(*Pc[k]), radius=0.036, color=DIM, resolution=RES)
                        for k in keep
                    ]
                ),
            ),
            Transform(
                shadows,
                VGroup(
                    *[
                        Dot3D(point=c2p(*Sc[k]), radius=0.030, color=BLUE, resolution=RES)
                        for k in shadow_idx
                    ]
                ),
            ),
            Transform(
                drops,
                VGroup(
                    *[
                        Line(
                            c2p(*Pc[k]),
                            c2p(*Sc[k]),
                            color=MUTED,
                            stroke_width=1.1,
                            stroke_opacity=0.55,
                        )
                        for k in shadow_idx
                    ]
                ),
            ),
            FadeOut(a_arm),
            FadeOut(b_arm),
            FadeOut(a_dot),
            FadeOut(b_dot),
            run_time=3.0,
        )
        self.wait(6)
        self.stop_ambient_camera_rotation()

        closing = _caption(
            self,
            "the plane never moved",
            "the cloud did — the offset was most of what it was showing",
        )
        self.play(FadeOut(cap4), FadeIn(closing), run_time=1.2)
        self.wait(2.0)
