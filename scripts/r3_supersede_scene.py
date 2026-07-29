"""R3 mechanism as motion: overwrite destroys state history, supersede demotes
it. Renders docs/assets/memory-field/r3-supersede.mp4:

    uv run --with manim manim -ql --media_dir /tmp/manim-r3 \
        scripts/r3_supersede_scene.py R3Supersede
"""

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    DashedLine,
    FadeIn,
    FadeOut,
    Rectangle,
    Scene,
    Text,
    VGroup,
    config,
)

config.background_color = "#08080a"

GOLD = "#f2b950"
BLUE = "#5a8cff"
RED = "#ff4d6d"
TEXT = "#eceae7"
MUTED = "#9a968f"


def card(label: str, color: str) -> VGroup:
    box = Rectangle(
        width=3.4,
        height=0.72,
        stroke_color=color,
        stroke_width=2,
        fill_opacity=0.12,
        fill_color=color,
    )
    txt = Text(label, font_size=20, color=TEXT)
    return VGroup(box, txt)


class R3Supersede(Scene):
    def construct(self):
        title = Text("state.md: overwrite vs supersede", font_size=30, color=TEXT).to_edge(UP)
        left_head = Text("before R3: overwrite", font_size=22, color=RED).shift(
            LEFT * 3.4 + UP * 2.2
        )
        right_head = Text("after R3: supersede", font_size=22, color=BLUE).shift(
            RIGHT * 3.4 + UP * 2.2
        )
        self.play(FadeIn(title), FadeIn(left_head), FadeIn(right_head))

        divider = DashedLine(RIGHT * 1.6 + UP * 0.6, RIGHT * 5.2 + UP * 0.6, color=MUTED)
        div_label = (
            Text("superseded", font_size=16, color=MUTED)
            .next_to(divider, RIGHT * 0.2 + UP * 0.2)
            .shift(LEFT * 1.4)
        )

        days = ["Jul 27: blocked on chroma", "Jul 28: eval gate green", "Jul 29: building batch"]
        left_card = None
        right_stack: list[VGroup] = []

        for i, label in enumerate(days):
            new_left = card(label, RED).shift(LEFT * 3.4 + UP * 1.2)
            new_right = card(label, BLUE).shift(RIGHT * 3.4 + UP * 1.2)

            anims = [FadeIn(new_left, shift=DOWN * 0.3), FadeIn(new_right, shift=DOWN * 0.3)]
            if left_card is not None:
                anims.append(FadeOut(left_card, shift=DOWN * 0.5))  # gone forever
            if right_stack:
                if i == 1:
                    anims += [FadeIn(divider), FadeIn(div_label)]
                for j, old in enumerate(right_stack):
                    anims.append(old.animate.shift(DOWN * 1.0).set_opacity(0.55 - 0.15 * j))
            self.play(*anims, run_time=1.1)
            left_card = new_left
            right_stack.insert(0, new_right)
            self.wait(0.4)

        gone = Text("history: gone", font_size=20, color=RED).shift(LEFT * 3.4 + DOWN * 1.6)
        kept = Text("history: dated, greppable, unembedded", font_size=18, color=GOLD).shift(
            RIGHT * 3.4 + DOWN * 2.4
        )
        self.play(FadeIn(gone), FadeIn(kept))
        self.wait(1.2)
