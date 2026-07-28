"""Manim explainers for the two overnight experiments.

    NullModel     -- why a size-matched null is the whole experiment (#37)
    ReplayCurve   -- do generated key moments land where people rewatch (#144)

Every number and every point position is real, loaded from the experiment
sidecars in docs/assets/. tag_data.json carries the actual UMAP layout of the
493 notes; heat_data.json carries one video's actual replay curve.

Render (ephemeral env, nothing installed system-wide):

    uv run --with manim manim -qm --media_dir /tmp/manim \\
        scripts/manim/experiments.py NullModel ReplayCurve
    cp /tmp/manim/videos/experiments/720p30/*.mp4 docs/assets/11-animations/

Only the finished mp4s are committed; manim's media dir also holds font caches
and per-animation partial movie files that are pure build artifacts.

Quality flags: -ql draft, -qm medium, -qh 1080p60.
"""

from __future__ import annotations

import json
from pathlib import Path

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Arrow,
    Create,
    Dot,
    FadeIn,
    FadeOut,
    Line,
    Rectangle,
    Scene,
    Text,
    VGroup,
    Write,
    config,
)

HERE = Path(__file__).resolve().parent

# the docs/assets house palette, so stills from these sit beside the figures
BG = "#08080a"
GOLD = "#f2b950"
CYAN = "#7fd4ff"
RED = "#ff4d6d"
TEXT = "#eceae7"
MUTED = "#9a968f"
DIM = "#3a3a42"

config.background_color = BG


def _title(text: str, sub: str = "") -> VGroup:
    t = Text(text, font_size=40, color=TEXT)
    if not sub:
        return VGroup(t)
    s = Text(sub, font_size=22, color=MUTED)
    s.next_to(t, DOWN, buff=0.28)
    return VGroup(t, s)


class NullModel(Scene):
    """Why 0.44 means nothing until you know what random looks like."""

    def construct(self) -> None:
        data = json.loads((HERE / "tag_data.json").read_text())
        pts = data["points"]
        stats = data["stats"]

        head = _title(
            "Does a tag mean anything?",
            "493 notes from the vault, laid out by what they are about",
        )
        self.play(Write(head[0]), run_time=1.4)
        self.play(FadeIn(head[1]), run_time=0.8)
        self.wait(0.6)
        self.play(head.animate.scale(0.55).to_edge(UP, buff=0.35), run_time=0.9)

        # the corpus. positions are the real UMAP layout, scaled to the frame
        SX, SY = 5.4, 2.9
        dots = VGroup(
            *[
                Dot([p[0] * SX, p[1] * SY, 0], radius=0.035, color=DIM, fill_opacity=0.75)
                for p in pts
            ]
        )
        dots.shift(DOWN * 0.35)
        self.play(FadeIn(dots, lag_ratio=0.002), run_time=2.2)
        self.wait(0.5)

        # --- a tag that works -------------------------------------------------
        label = Text("ai-coding  ·  49 notes", font_size=26, color=GOLD)
        label.to_edge(LEFT, buff=0.7).shift(UP * 2.0)
        self.play(Write(label), run_time=0.8)

        hits = data["ai_coding"]
        self.play(
            *[dots[i].animate.set_color(GOLD).scale(1.9) for i in hits],
            run_time=1.3,
        )
        self.wait(0.6)

        obs = Text(
            f"average closeness  {stats['ai-coding']['cohesion']:.2f}",
            font_size=26,
            color=GOLD,
        )
        obs.next_to(label, DOWN, buff=0.35).align_to(label, LEFT)
        self.play(Write(obs), run_time=0.9)
        self.wait(0.8)

        ask = Text("...is that good?", font_size=30, color=TEXT)
        ask.to_edge(RIGHT, buff=1.0).shift(UP * 2.0)
        self.play(Write(ask), run_time=0.9)
        self.wait(0.9)

        # --- the null ---------------------------------------------------------
        self.play(
            *[dots[i].animate.set_color(DIM).scale(1 / 1.9) for i in hits],
            FadeOut(ask),
            run_time=0.9,
        )

        null_label = Text("49 notes picked at random", font_size=26, color=CYAN).move_to(label)
        self.play(FadeOut(label), FadeIn(null_label), run_time=0.7)

        import random

        rng = random.Random(20260728)
        for round_i in range(3):
            pick = rng.sample(range(len(pts)), 49)
            self.play(
                *[dots[i].animate.set_color(CYAN).scale(1.7) for i in pick],
                run_time=0.45,
            )
            self.wait(0.18)
            self.play(
                *[dots[i].animate.set_color(DIM).scale(1 / 1.7) for i in pick],
                run_time=0.35,
            )

        null_val = Text(
            f"every time, about  {stats['ai-coding']['null_mean']:.2f}",
            font_size=26,
            color=CYAN,
        )
        null_val.next_to(null_label, DOWN, buff=0.35).align_to(null_label, LEFT)
        self.play(Write(null_val), run_time=0.9)
        self.wait(0.8)

        # --- the verdict ------------------------------------------------------
        # Plotted in z units, not raw cohesion: the two tags have DIFFERENT nulls
        # (different n gives a different spread), so a shared raw axis would put
        # reference's arrow in the wrong place. z is the common ruler.
        self.play(FadeOut(dots), FadeOut(null_label), FadeOut(null_val), FadeOut(obs))

        Y = -0.9
        span = 6.0  # z units visible either side, to start

        def bell_and_axis(span_: float) -> tuple[VGroup, VGroup]:
            ax = Line([-6.0, Y, 0], [6.0, Y, 0], color=DIM, stroke_width=3)
            marks_ = VGroup(ax)
            # symmetric about zero, so the eye reads the bell as centred
            step = span_ / 6.0
            for k in range(-6, 7):
                x = (k * step) / span_ * 5.6
                marks_.add(Line([x, Y - 0.13, 0], [x, Y + 0.13, 0], color=DIM, stroke_width=2))
            b = VGroup()
            for k in range(-42, 43):
                zv = k / 12.0
                h = 2.3 * pow(2.718281828, -(zv**2) / 2)
                x = zv / span_ * 5.6
                b.add(
                    Rectangle(
                        width=max(0.13 / span_ * 6, 0.02),
                        height=max(h, 0.015),
                        fill_color=CYAN,
                        fill_opacity=0.55,
                        stroke_width=0,
                    ).move_to([x, Y + max(h, 0.015) / 2, 0])
                )
            return marks_, b

        axis_g, bell = bell_and_axis(span)
        null_cap = Text("what random looks like", font_size=24, color=CYAN)
        null_cap.move_to([0, Y + 2.9, 0])
        self.play(Create(axis_g), run_time=0.7)
        self.play(FadeIn(bell, lag_ratio=0.02), Write(null_cap), run_time=1.5)
        self.wait(0.6)

        def arrow_at(zv: float, span_: float, col: str) -> Arrow:
            x = zv / span_ * 5.6
            return Arrow([x, Y + 2.1, 0], [x, Y + 0.16, 0], color=col, buff=0.04, stroke_width=6)

        rz = stats["reference"]["z"]
        a_ref = arrow_at(rz, span, RED)
        c_ref = Text("reference", font_size=26, color=RED).next_to(a_ref, UP, buff=0.12)
        self.play(Create(a_ref), Write(c_ref), run_time=1.0)
        self.wait(0.5)
        note_ref = Text("below random", font_size=23, color=RED)
        note_ref.move_to([0, Y - 0.75, 0])
        self.play(Write(note_ref), run_time=0.8)
        self.wait(1.2)

        # now zoom the ruler out to fit the tag that works
        az = stats["ai-coding"]["z"]
        span2 = 20.0
        axis2, bell2 = bell_and_axis(span2)
        a_ref2 = arrow_at(rz, span2, RED)
        c_ref2 = Text("reference", font_size=20, color=RED).next_to(a_ref2, UP, buff=0.10)

        ask2 = Text("and the tag that worked?", font_size=27, color=TEXT)
        ask2.move_to([0, Y + 3.05, 0])
        self.play(FadeOut(note_ref), FadeOut(null_cap), Write(ask2), run_time=0.9)
        self.play(
            axis_g.animate.become(axis2),
            bell.animate.become(bell2),
            a_ref.animate.become(a_ref2),
            c_ref.animate.become(c_ref2),
            run_time=1.8,
        )
        self.wait(0.4)

        a_ai = arrow_at(az, span2, GOLD)
        c_ai = Text("ai-coding", font_size=26, color=GOLD).next_to(a_ai, UP, buff=0.12)
        self.play(Create(a_ai), Write(c_ai), run_time=1.1)
        z_ai = Text("17 standard deviations from random", font_size=22, color=GOLD)
        z_ai.move_to([0, Y - 0.78, 0])
        self.play(Write(z_ai), run_time=1.0)
        self.wait(1.4)

        punch = Text(
            "Two notes sharing 'reference' are less alike than two picked at random.",
            font_size=25,
            color=TEXT,
        )
        punch.to_edge(DOWN, buff=0.45)
        self.play(FadeOut(ask2), Write(punch), run_time=1.8)
        self.wait(2.4)


class ReplayCurve(Scene):
    """Do the generated timestamps land where the audience actually rewatches?"""

    def construct(self) -> None:
        data = json.loads((HERE / "heat_data.json").read_text())
        heat = data["heatmap"]
        dur = data["duration"]
        o = data["overall"]

        head = _title(
            "Are the timestamps any good?",
            "Claude marks key moments on every video. Nobody ever checked.",
        )
        self.play(Write(head[0]), run_time=1.4)
        self.play(FadeIn(head[1]), run_time=0.9)
        self.wait(0.8)
        self.play(head.animate.scale(0.55).to_edge(UP, buff=0.35), run_time=0.9)

        # the video as a timeline
        X0, X1, Y0 = -5.6, 5.6, -2.2
        bar = Line([X0, Y0, 0], [X1, Y0, 0], color=DIM, stroke_width=4)
        cap = Text(data["title"][:52], font_size=21, color=MUTED)
        cap.next_to(bar, DOWN, buff=0.25)
        self.play(Create(bar), FadeIn(cap), run_time=1.0)
        self.wait(0.4)

        # YouTube's own replay curve
        def x_at(t: float) -> float:
            return X0 + (t / dur) * (X1 - X0)

        HS = 2.9
        pts = [
            [X0 + (i + 0.5) / len(heat) * (X1 - X0), Y0 + heat[i] * HS, 0] for i in range(len(heat))
        ]
        curve = VGroup(
            *[Line(pts[i], pts[i + 1], color=GOLD, stroke_width=3) for i in range(len(pts) - 1)]
        )
        ylab = Text("how often people rewatch", font_size=21, color=GOLD)
        ylab.to_edge(LEFT, buff=0.5).shift(UP * 1.5)
        self.play(Create(curve, lag_ratio=0.03), run_time=2.6)
        self.play(FadeIn(ylab), run_time=0.6)
        self.wait(0.7)

        note = Text(
            "YouTube publishes this. ytk downloads it every time — and throws it away.",
            font_size=22,
            color=MUTED,
        )
        note.to_edge(DOWN, buff=0.35)
        self.play(Write(note), run_time=1.7)
        self.wait(1.4)
        self.play(FadeOut(note))

        # the generated marks
        marks = VGroup()
        for t in data["key_moments"]:
            if t > dur:
                continue
            idx = min(int(t / dur * len(heat)), len(heat) - 1)
            d = Dot([x_at(t), Y0 + heat[idx] * HS, 0], radius=0.085, color=CYAN)
            marks.add(d)
        mlab = Text(f"Claude's key moments  ({len(marks)})", font_size=23, color=CYAN)
        mlab.to_edge(RIGHT, buff=0.5).shift(UP * 1.5)
        self.play(FadeIn(marks, lag_ratio=0.14), Write(mlab), run_time=2.0)
        self.wait(1.0)

        # the comparison, on real corpus-wide numbers
        self.play(
            FadeOut(curve),
            FadeOut(marks),
            FadeOut(bar),
            FadeOut(cap),
            FadeOut(ylab),
            FadeOut(mlab),
            run_time=0.8,
        )

        rows = [
            ("picked at random", o["null_mean"], DIM),
            ("Claude's key moments", o["km_mean"], CYAN),
            ("the uploader's own chapters", o["chapter_mean"], GOLD),
        ]
        group = VGroup()
        for k, (name, val, col) in enumerate(rows):
            y = 1.1 - k * 1.15
            lbl = Text(name, font_size=25, color=col)
            lbl.move_to([-2.0, y, 0]).align_to([-5.4, y, 0], LEFT)
            barw = val * 9.5
            b = Rectangle(width=barw, height=0.42, fill_color=col, fill_opacity=0.8, stroke_width=0)
            b.move_to([0.6 + barw / 2, y, 0])
            num = Text(f"{val:.3f}", font_size=23, color=col)
            num.next_to(b, RIGHT, buff=0.2)
            group.add(VGroup(lbl, b, num))

        subtitle = Text(
            f"{o['videos_scored']} videos  ·  {o['key_moments_scored']} key moments",
            font_size=21,
            color=MUTED,
        )
        subtitle.to_edge(DOWN, buff=1.5)

        for row in group:
            self.play(FadeIn(row[0]), Create(row[1]), FadeIn(row[2]), run_time=0.85)
        self.play(FadeIn(subtitle), run_time=0.6)
        self.wait(1.2)

        punch = Text(
            f"Better than chance on {o['win_rate'] * 100:.0f}% of videos —"
            " and a third of what a human gets.",
            font_size=25,
            color=TEXT,
        )
        punch.to_edge(DOWN, buff=0.55)
        self.play(Write(punch), run_time=1.9)
        self.wait(2.4)
