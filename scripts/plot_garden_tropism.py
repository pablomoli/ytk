"""The two tropism axes, isolated, for docs/assets/14-garden-allometry/.

The complaint this settles: limbs sprout up rather than up and out. The shipped
generator adds a constant upward pull at every step regardless of branch order,
so any limb that forks laterally is immediately re-aimed vertical. Stage 1 of
the rework composes two gradients instead -- one on branch order, one on height
-- and this figure separates their contributions.

    uv run --with matplotlib python scripts/plot_garden_tropism.py

Mirrors the rules specified for web/src/lib/garden/scaffold.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from plot_assets import BG, FRAME, GOLD, MUTED, PANEL, TEXT, use_house_font
from plot_garden_taper import Node, chains, murray_girth, outline, resample, walk

use_house_font()

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "14-garden-allometry"
DPI = 200

CROWN_H = 3.2
TIP_RADIUS = 0.016
EXPONENT = 2.5


@dataclass
class Tropism:
    up_bias: float = 0.55
    order_decay: float = 1.0  # 1.0 = no gradient, the shipped behaviour
    sag: float = 0.0
    sag_floor: float = 0.22
    length_gradient: float = 0.0
    stiffness: float = 0.62
    step: float = 0.17


def unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else np.array([0.0, 1.0])


def grow_limb(start: Node, direction: np.ndarray, order: int, steps: int, p: Tropism) -> Node:
    node = start
    d = unit(np.array(direction, dtype=float))
    run = 0.0
    for _ in range(steps):
        # Gravitropism falls off with branch order: the trunk holds vertical,
        # outer limbs barely feel it.
        up_pull = p.up_bias * (p.order_decay**order)
        pull = d + np.array([0.0, 1.0]) * up_pull

        if p.sag > 0.0:
            h = min(1.0, max(0.0, node.pos[1] / CROWN_H))
            # Long and low droops; short and high does not.
            weight = (run / max(p.step, 1e-6)) * p.step
            pull = pull + np.array([0.0, -1.0]) * p.sag * weight * (1.0 - h)

        d = unit(p.stiffness * d + (1.0 - p.stiffness) * unit(pull))
        pos = node.pos + d * p.step
        pos[1] = max(pos[1], p.sag_floor)
        nxt = Node((float(pos[0]), float(pos[1])))
        node.children.append(nxt)
        node = nxt
        run += p.step
    return node


def build(p: Tropism) -> Node:
    """Trunk with tiers of lateral limbs -- the clearest read on tropism."""
    root = Node((0.0, 0.0))
    trunk = root
    tiers = [0.36, 0.52, 0.68, 0.84]
    trunk_steps = 5
    for ti, frac in enumerate(tiers):
        trunk = grow_limb(trunk, np.array([0.0, 1.0]), 0, trunk_steps, p)
        h = min(1.0, max(0.0, trunk.pos[1] / CROWN_H))
        # Length must come from the gradient alone, or a per-tier taper would
        # double-count it and the panels would not isolate the rule.
        base = 11
        steps = max(3, round(base * (1.0 - p.length_gradient * h)))
        for side in (-1.0, 1.0):
            lift = 0.30 + 0.16 * ti
            start = grow_limb(trunk, np.array([side, lift]), 1, steps, p)
            if steps > 5:
                for s2 in (-1.0, 1.0):
                    grow_limb(
                        start, np.array([side * 0.8, lift + s2 * 0.25]), 2, max(3, steps // 2), p
                    )
        _ = frac
    grow_limb(trunk, np.array([0.0, 1.0]), 0, 4, p)
    return root


def draw(ax, root: Node, title: str, sag_floor: float | None) -> None:
    murray_girth(root, TIP_RADIUS, EXPONENT)
    for seq in chains(root):
        pts, rs, _ = resample(seq, "arc")
        ax.fill(*outline(pts, rs).T, color="#cdc7bb", alpha=0.82, linewidth=0)
    if sag_floor is not None:
        ax.axhline(sag_floor, color=GOLD, linewidth=0.9, alpha=0.55, linestyle=(0, (5, 4)))
        ax.text(
            2.42,
            sag_floor + 0.07,
            "sag floor",
            color=GOLD,
            fontsize=8.4,
            ha="right",
            alpha=0.8,
        )
    ax.set_title(title, color=TEXT, fontsize=12, pad=12, linespacing=1.5)
    ax.set_xlim(-2.55, 2.55)
    ax.set_ylim(-0.25, 4.15)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(PANEL)


def spread_metric(root: Node) -> tuple[float, float]:
    pts = np.array([n.pos for n in walk(root)])
    return float(np.abs(pts[:, 0]).max()), float(pts[:, 1].max())


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    cases = [
        ("A. shipped\nconstant up-pull at every step", Tropism(), None),
        (
            "B. + order gradient\nup-pull decays with branch order",
            Tropism(order_decay=0.30),
            None,
        ),
        (
            "C. + gravity sag\nlong low limbs droop, crown reaches up",
            Tropism(order_decay=0.30, sag=1.15),
            0.22,
        ),
        (
            "D. both, plus length gradient\nwhat stage 1 specifies",
            Tropism(order_decay=0.30, sag=1.15, length_gradient=0.35),
            0.22,
        ),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(17.0, 5.9), facecolor=BG)
    stats = []
    for ax, (title, p, floor) in zip(axes, cases, strict=True):
        root = build(p)
        draw(ax, root, title, floor)
        w, h = spread_metric(root)
        stats.append((title.split("\n")[0], w, h, w / max(h, 1e-6)))

    fig.suptitle(
        "Garden tropism: why limbs sprout up instead of up and out",
        color=TEXT,
        fontsize=16.5,
        y=1.0,
    )
    bits = "     ".join(f"{name}  w/h {r:.2f}" for name, _, _, r in stats)
    fig.text(
        0.5,
        0.055,
        "Same topology, same seed, same step count in A-C; only the tropism rules differ.\n" + bits,
        color=MUTED,
        fontsize=10.2,
        ha="center",
        linespacing=1.8,
    )
    for s in fig.axes:
        for sp in s.spines.values():
            sp.set_color(FRAME)

    out = OUTDIR / "03-tropism-axes.png"
    fig.savefig(out, dpi=DPI, facecolor=BG, bbox_inches="tight")
    print(f"wrote {out}")
    for name, w, h, r in stats:
        print(f"  {name:<12} half-width {w:.2f}  height {h:.2f}  w/h {r:.2f}")


if __name__ == "__main__":
    main()
