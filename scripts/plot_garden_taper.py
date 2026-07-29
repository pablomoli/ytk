"""Limb taper under three girth schemes, for docs/assets/14-garden-allometry/.

The question this settles: Murray's law fixes radius only at junctions, so
what happens along the unbranched run between two forks depends entirely on
how stage 4 interpolates. Panel B is what the current geometry code does with
Murray radii; panel C is the proposed redistribution.

    uv run --with matplotlib python scripts/plot_garden_taper.py

Mirrors the real math: the Murray pass from web/src/lib/garden/girth.ts and
the per-control-point lerp at web/src/lib/garden/tree.ts:331.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from plot_assets import BG, DIM, FRAME, GOLD, MUTED, PANEL, TEXT, use_house_font

use_house_font()

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "14-garden-allometry"
DPI = 200

TIP_RADIUS = 0.030
EXPONENT = 2.5
# Old scheme, from the pre-rework generator: per-step decay plus an extra
# cut at forks. Kept only so panel A reproduces what shipped.
GIRTH_DECAY = 0.94
FORK_CUT = 0.72
GIRTH = 1.0


class Node:
    __slots__ = ("children", "pos", "radius", "weight")

    def __init__(self, pos: tuple[float, float]) -> None:
        self.pos = np.array(pos, dtype=float)
        self.children: list[Node] = []
        self.radius = 0.0
        self.weight = 1.0


def build(depth: int = 4, run: int = 7, step: float = 0.34) -> Node:
    """A deterministic 2D skeleton: unbranched runs of `run` nodes between forks."""
    root = Node((0.0, 0.0))

    def grow(node: Node, heading: float, level: int) -> None:
        cursor = node
        for _ in range(run):
            nxt = Node(
                (
                    cursor.pos[0] + math.cos(heading) * step,
                    cursor.pos[1] + math.sin(heading) * step,
                )
            )
            cursor.children.append(nxt)
            cursor = nxt
        if level >= depth:
            return
        spread = 0.40 + 0.06 * level
        for side in (-1.0, 1.0):
            grow(cursor, heading + side * spread, level + 1)

    grow(root, math.pi / 2, 0)
    return root


def walk(root: Node) -> list[Node]:
    out: list[Node] = []
    stack = [root]
    while stack:
        n = stack.pop()
        out.append(n)
        stack.extend(n.children)
    return out


def murray_girth(root: Node, tip_radius: float, exponent: float) -> None:
    order = walk(root)
    inv = 1.0 / exponent
    for node in reversed(order):
        if not node.children:
            node.radius = tip_radius
        elif len(node.children) == 1:
            node.radius = node.children[0].radius
        else:
            node.radius = sum(c.radius**exponent for c in node.children) ** inv


def decay_girth(root: Node, girth: float) -> None:
    root.weight = 1.0
    stack = [root]
    while stack:
        node = stack.pop()
        node.radius = node.weight * girth * TIP_RADIUS * 12.0
        cut = FORK_CUT if len(node.children) > 1 else 1.0
        for child in node.children:
            child.weight = node.weight * GIRTH_DECAY * cut
            stack.append(child)


def chains(root: Node) -> list[list[Node]]:
    """Maximal single-child runs, each starting at its parent branch node.

    Mirrors decompose() in tree.ts: the chain includes the upstream fork and
    terminates on the next fork or tip.
    """
    out: list[list[Node]] = []

    def descend(start: Node) -> None:
        for first in start.children:
            seq = [start, first]
            node = first
            while len(node.children) == 1:
                node = node.children[0]
                seq.append(node)
            out.append(seq)
            if node.children:
                descend(node)

    descend(root)
    return out


def resample(seq: list[Node], mode: str, samples: int = 96):
    """Positions and radii along one chain.

    control : piecewise-linear between adjacent control points, i.e. what
              tree.ts:331 does today
    arc     : the transition spread across the chain's full arc length
    """
    pts = np.array([n.pos for n in seq])
    radii = np.array([n.radius for n in seq])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    total = arc[-1]
    ts = np.linspace(0.0, total, samples)

    xs = np.interp(ts, arc, pts[:, 0])
    ys = np.interp(ts, arc, pts[:, 1])
    if mode == "control":
        rs = np.interp(ts, arc, radii)
    else:
        rs = radii[0] + (radii[-1] - radii[0]) * (ts / total if total else ts)
    return np.column_stack([xs, ys]), rs, ts / (total or 1.0)


def outline(pts: np.ndarray, rs: np.ndarray) -> np.ndarray:
    d = np.gradient(pts, axis=0)
    n = np.column_stack([-d[:, 1], d[:, 0]])
    norm = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, norm, out=np.zeros_like(n), where=norm > 0)
    left = pts + n * rs[:, None]
    right = pts - n * rs[:, None]
    return np.vstack([left, right[::-1]])


def normalise(root: Node, trunk: float) -> None:
    """Equalise trunk radius across schemes so the panels compare shape, not scale."""
    if root.radius <= 0:
        return
    k = trunk / root.radius
    for n in walk(root):
        n.radius *= k


def draw(ax, cs: list[list[Node]], mode: str, hot_index: int) -> None:
    for i, seq in enumerate(cs):
        pts, rs, _ = resample(seq, mode)
        hot = i == hot_index
        ax.fill(
            *outline(pts, rs).T,
            color=GOLD if hot else "#cdc7bb",
            alpha=1.0 if hot else 0.30,
            linewidth=0,
            zorder=3 if hot else 2,
        )
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(PANEL)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    schemes = [
        ("A. top-down decay\n(what shipped)", "decay", "control"),
        (
            "B. Murray + per-control-point lerp\n(what the current code would do)",
            "murray",
            "control",
        ),
        ("C. Murray + arc-length taper\n(proposed)", "murray", "arc"),
    ]

    fig = plt.figure(figsize=(13.5, 8.4), facecolor=BG)
    gs = fig.add_gridspec(2, 3, height_ratios=[2.4, 1.0], hspace=0.16, wspace=0.16)

    TRUNK = 0.26  # every scheme normalised to this, so shape is what differs
    profiles = []
    for col, (title, girth_mode, interp) in enumerate(schemes):
        root = build()
        if girth_mode == "murray":
            murray_girth(root, TIP_RADIUS, EXPONENT)
        else:
            decay_girth(root, GIRTH)
        normalise(root, TRUNK)

        cs = chains(root)
        # a second-order limb: long enough to show what a run does between forks
        hot = len(cs) // 2

        ax = fig.add_subplot(gs[0, col])
        draw(ax, cs, interp, hot)
        ax.set_title(title, color=TEXT, fontsize=12.5, pad=12, linespacing=1.5)

        pts, rs, t = resample(cs[hot], interp)
        profiles.append((t, rs))

        px = fig.add_subplot(gs[1, col])
        px.set_facecolor(PANEL)
        px.plot(t, rs, color=GOLD, linewidth=2.3)
        px.fill_between(t, 0, rs, color=GOLD, alpha=0.13)
        px.set_xlim(0, 1)
        px.set_xlabel("along the limb, fork to fork", color=MUTED, fontsize=10)
        if col == 0:
            px.set_ylabel("radius", color=MUTED, fontsize=10)
        px.tick_params(colors=MUTED, labelsize=8.5)
        for s in px.spines.values():
            s.set_color(FRAME)
        px.grid(True, color=DIM, linewidth=0.5, alpha=0.5)

        if interp == "control" and girth_mode == "murray":
            px.annotate(
                "entire change here",
                xy=(0.045, (rs[0] + rs[-1]) / 2),
                xytext=(0.42, rs[0] * 0.995),
                color=TEXT,
                fontsize=10,
                arrowprops={"arrowstyle": "->", "color": TEXT, "linewidth": 1.2},
            )

    # one shared y-window across the three profiles, tight to the data, so the
    # panels are readable and comparable at the same time
    lo = min(r.min() for _, r in profiles)
    hi = max(r.max() for _, r in profiles)
    pad = (hi - lo) * 0.35 or hi * 0.1
    for col in range(3):
        fig.axes[1 + col * 2].set_ylim(lo - pad, hi + pad)

    fig.suptitle(
        "Garden limb taper: Murray fixes radius only at junctions",
        color=TEXT,
        fontsize=16.5,
        y=0.975,
    )
    fig.subplots_adjust(bottom=0.16)
    fig.text(
        0.5,
        0.015,
        "Highlighted limb runs between two forks. B concentrates the entire width change "
        "into the first inter-node interval, leaving the rest cylindrical;\nC spreads the same "
        "endpoint values across the arc. Junction radii are identical in B and C, so the "
        "Murray invariant is untouched either way.",
        color=MUTED,
        fontsize=10.5,
        ha="center",
        linespacing=1.6,
    )

    out = OUTDIR / "01-limb-taper.png"
    fig.savefig(out, dpi=DPI, facecolor=BG, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
