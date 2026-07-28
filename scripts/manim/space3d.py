"""Camera-moving versions of the 3D figures in docs/assets/09-12.

    CorpusSolid   -- the vault as a solid, coloured by where each note came from
    TagInSpace    -- ai-coding as a region, reference as confetti (fig 11)
    TheCone       -- the corpus, an isotropic control, and the centred corpus

Additive: the static PNGs stay. What these add is parallax. A still 3D scatter
is ambiguous by construction -- depth reads as size, and a cluster can be an
artifact of the viewing angle. Orbiting the camera removes that doubt, which is
the one thing the stills cannot do.

Same palette as docs/assets so frames sit beside the figures.

Render (ephemeral env, nothing installed system-wide):

    uv run --with manim manim -qm --media_dir /tmp/manim \\
        scripts/manim/space3d.py CorpusSolid TagInSpace TheCone
    cp /tmp/manim/videos/space3d/720p30/*.mp4 docs/assets/13-space-3d/

Point count is the cost driver and it is steep: every dot is a real sphere that
manim re-sorts by depth on every frame, and camera rotation means every frame is
a new sort. A first attempt with all 493 notes at full sphere resolution did not
finish a draft render in ten minutes.

So the background cloud is subsampled (SUBSAMPLE below) and spheres are coarse.
The highlighted sets are always drawn in full -- those are the subject, and
dropping members of the set being measured would misrepresent it. The subsample
is seeded, so the same notes are dropped every run.
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
    Dot3D,
    FadeIn,
    FadeOut,
    Line3D,
    Text,
    ThreeDAxes,
    ThreeDScene,
    VGroup,
    Write,
    config,
)

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "space3d.json").read_text())

# Background cloud only. Highlighted tags are never subsampled.
SUBSAMPLE = 200
RES = (4, 4)  # sphere facets; 4x4 is the floor before dots read as diamonds


def _bg_index(n: int) -> np.ndarray:
    """A seeded subsample of the background cloud, stable across renders."""
    rng = np.random.default_rng(DATA["seed"])
    return np.sort(rng.choice(n, size=min(SUBSAMPLE, n), replace=False))


BG = "#08080a"
GOLD = "#f2b950"
CYAN = "#7fd4ff"
RED = "#ff4d6d"
BLUE = "#5a8cff"
PURPLE = "#9159ff"
TEXT = "#eceae7"
MUTED = "#9a968f"
DIM = "#3a3a42"

config.background_color = BG

# manimpango's fallback font was swallowing spaces at these sizes -- captions
# rendered as "theorigin" and "theunit sphere". Naming a font fixes it.
FONT = "Helvetica Neue"

SOURCE_COLOR = {
    "youtube": GOLD,
    "instagram": CYAN,
    "web": RED,
    "tiktok": BLUE,
    "pinterest": PURPLE,
    "reddit": "#ff9f43",
    "journal": TEXT,
}


def _axes(rng: float = 1.25) -> ThreeDAxes:
    ax = ThreeDAxes(
        x_range=[-rng, rng, rng / 2],
        y_range=[-rng, rng, rng / 2],
        z_range=[-rng, rng, rng / 2],
        x_length=6.4,
        y_length=6.4,
        z_length=6.4,
    )
    # set_color, not set_stroke: the tips are separate mobjects with their own
    # fill, and stroke alone left them rendering as big white arrowheads
    ax.set_color(DIM)
    ax.set_stroke(width=1.6, opacity=0.75)
    for tip in (ax.get_x_axis().tip, ax.get_y_axis().tip, ax.get_z_axis().tip):
        tip.set_fill(color=DIM, opacity=0.9).set_stroke(width=0)
        tip.scale(0.55)
    return ax


def _caption(scene: ThreeDScene, *lines: str) -> VGroup:
    """Text fixed to the frame, so the camera can orbit under it."""
    g = VGroup()
    for i, s in enumerate(lines):
        t = Text(s, font=FONT, font_size=26 if i == 0 else 20, color=TEXT if i == 0 else MUTED)
        g.add(t)
    g.arrange(DOWN, buff=0.18)
    g.to_corner(UP + RIGHT, buff=0.45)
    scene.add_fixed_in_frame_mobjects(g)
    return g


class CorpusSolid(ThreeDScene):
    """The vault as a solid. Does provenance separate? (No.)"""

    def construct(self) -> None:
        P = np.array(DATA["umap3"]) * 1.15
        sources = DATA["sources"]
        keep = _bg_index(len(P))
        P, sources = P[keep], [sources[i] for i in keep]

        self.set_camera_orientation(phi=68 * DEGREES, theta=-52 * DEGREES, zoom=0.95)
        axes = _axes()
        self.play(FadeIn(axes), run_time=1.0)

        dots = VGroup(
            *[
                Dot3D(
                    point=axes.c2p(*p),
                    radius=0.042,
                    color=SOURCE_COLOR.get(s, DIM),
                    resolution=RES,
                )
                for p, s in zip(P, sources)
            ]
        )
        cap = _caption(
            self,
            f"{len(P)} of 493 notes, in three dimensions",
            "colour = where the note came from",
        )
        self.play(FadeIn(dots, lag_ratio=0.004), Write(cap[0]), run_time=3.0)
        self.play(FadeIn(cap[1]), run_time=0.7)

        # one full orbit: the whole point of animating this
        self.begin_ambient_camera_rotation(rate=0.30)
        self.wait(7.5)
        self.stop_ambient_camera_rotation()

        note = Text(
            "YouTube and Instagram interleave — the space is organised by subject, not source",
            font=FONT,
            font_size=21,
            color=MUTED,
        ).to_edge(DOWN, buff=0.45)
        self.add_fixed_in_frame_mobjects(note)
        self.play(Write(note), run_time=2.0)
        self.move_camera(phi=28 * DEGREES, theta=-110 * DEGREES, run_time=3.2)
        self.wait(1.6)


class TagInSpace(ThreeDScene):
    """A tag that names a region, and one that names nothing."""

    def construct(self) -> None:
        P = np.array(DATA["umap3"]) * 1.15

        self.set_camera_orientation(phi=66 * DEGREES, theta=-48 * DEGREES, zoom=0.95)
        axes = _axes()
        self.add(axes)

        keep = {int(i) for i in _bg_index(len(P))}
        base = VGroup(
            *[
                Dot3D(point=axes.c2p(*P[i]), radius=0.030, color=DIM, resolution=RES)
                for i in range(len(P))
                if i in keep
            ]
        )
        self.play(FadeIn(base, lag_ratio=0.003), run_time=2.4)

        cap = _caption(self, "ai-coding", "49 notes  ·  z = +17")
        hits = DATA["ai_coding"]
        lit = VGroup(
            *[Dot3D(point=axes.c2p(*P[i]), radius=0.056, color=GOLD, resolution=RES) for i in hits]
        )
        self.play(FadeIn(lit, lag_ratio=0.03), Write(cap[0]), run_time=1.8)
        self.play(FadeIn(cap[1]), run_time=0.6)

        self.begin_ambient_camera_rotation(rate=0.32)
        self.wait(6.5)
        self.stop_ambient_camera_rotation()

        # swap the highlight without moving the camera, so the layout is
        # visibly identical and only the membership changes
        cap2 = VGroup(
            Text("reference", font=FONT, font_size=26, color=RED),
            Text("125 notes  ·  z = -3.4", font=FONT, font_size=20, color=MUTED),
        ).arrange(DOWN, buff=0.18)
        cap2.to_corner(UP + RIGHT, buff=0.45)
        self.add_fixed_in_frame_mobjects(cap2)

        ref = VGroup(
            *[
                Dot3D(point=axes.c2p(*P[i]), radius=0.056, color=RED, resolution=RES)
                for i in DATA["reference"]
            ]
        )
        self.play(
            FadeOut(lit), FadeOut(cap), FadeIn(ref, lag_ratio=0.01), FadeIn(cap2), run_time=2.2
        )

        self.begin_ambient_camera_rotation(rate=0.32)
        self.wait(7.5)
        self.stop_ambient_camera_rotation()

        note = Text(
            "No angle makes 'reference' a cluster — that is what z = -3.4 means",
            font=FONT,
            font_size=22,
            color=TEXT,
        ).to_edge(DOWN, buff=0.45)
        self.add_fixed_in_frame_mobjects(note)
        self.play(Write(note), run_time=2.0)
        self.wait(2.0)


class TheCone(ThreeDScene):
    """The corpus does not surround its own origin."""

    def construct(self) -> None:
        keep = _bg_index(len(DATA["cone"]))
        cone = np.array(DATA["cone"])[keep]
        iso = np.array(DATA["iso"])[keep]
        cen = np.array(DATA["centred"])[keep]

        # each cloud scaled to its own extent: in 1024 dimensions an isotropic
        # vector has tiny components in any fixed 3D subspace, so a shared scale
        # would render the control as a dot and hide the actual difference
        def fit(A):
            return A / (np.abs(A).max() * 1.05)

        self.set_camera_orientation(phi=70 * DEGREES, theta=-56 * DEGREES, zoom=1.0)
        axes = _axes(rng=1.1)
        self.add(axes)

        origin = Dot3D(point=axes.c2p(0, 0, 0), radius=0.085, color=RED, resolution=(8, 8))
        olab = Text("the origin", font=FONT, font_size=20, color=RED).to_corner(
            DOWN + RIGHT, buff=0.5
        )
        self.add_fixed_in_frame_mobjects(olab)
        self.play(FadeIn(origin), FadeIn(olab), run_time=1.0)

        cap = _caption(self, "the vault, as stored", f"{len(cone)} of 493, on the unit sphere")
        P = fit(cone)
        cloud = VGroup(
            *[Dot3D(point=axes.c2p(*p), radius=0.038, color=GOLD, resolution=RES) for p in P]
        )
        self.play(FadeIn(cloud, lag_ratio=0.003), Write(cap[0]), run_time=2.6)
        self.play(FadeIn(cap[1]), run_time=0.6)

        m = P.mean(0)
        arrow = Line3D(start=axes.c2p(0, 0, 0), end=axes.c2p(*m), color=GOLD, thickness=0.022)
        self.play(FadeIn(arrow), run_time=1.0)

        self.begin_ambient_camera_rotation(rate=0.34)
        self.wait(7)
        self.stop_ambient_camera_rotation()

        # the control
        cap2 = VGroup(
            Text("{len(iso)} random vectors", font=FONT, font_size=26, color=TEXT),
            Text("same dimension, no structure", font=FONT, font_size=20, color=MUTED),
        ).arrange(DOWN, buff=0.18)
        cap2.to_corner(UP + RIGHT, buff=0.45)
        self.add_fixed_in_frame_mobjects(cap2)
        Q = fit(iso)
        control = VGroup(
            *[Dot3D(point=axes.c2p(*q), radius=0.038, color=DIM, resolution=RES) for q in Q]
        )
        self.play(
            FadeOut(cloud),
            FadeOut(arrow),
            FadeOut(cap),
            FadeIn(control, lag_ratio=0.003),
            FadeIn(cap2),
            run_time=2.4,
        )
        self.begin_ambient_camera_rotation(rate=0.34)
        self.wait(6)
        self.stop_ambient_camera_rotation()

        # and the corpus once the shared direction is gone
        cap3 = VGroup(
            Text("the vault, centred", font=FONT, font_size=26, color=CYAN),
            Text("one direction subtracted", font=FONT, font_size=20, color=MUTED),
        ).arrange(DOWN, buff=0.18)
        cap3.to_corner(UP + RIGHT, buff=0.45)
        self.add_fixed_in_frame_mobjects(cap3)
        Rr = fit(cen)
        centred = VGroup(
            *[Dot3D(point=axes.c2p(*p), radius=0.038, color=CYAN, resolution=RES) for p in Rr]
        )
        self.play(
            FadeOut(control),
            FadeOut(cap2),
            FadeIn(centred, lag_ratio=0.003),
            FadeIn(cap3),
            run_time=2.4,
        )
        self.begin_ambient_camera_rotation(rate=0.34)
        self.wait(6)
        self.stop_ambient_camera_rotation()

        note = Text(
            "Cosine measures angle AT the origin — so a corpus that misses the origin leans in every measurement",
            font=FONT,
            font_size=20,
            color=TEXT,
        ).to_edge(DOWN, buff=0.42)
        self.add_fixed_in_frame_mobjects(note)
        self.play(FadeOut(olab), Write(note), run_time=2.2)
        self.wait(2.2)
