"""Ground-truth figures for ribbon strands (feature B, epic #107).

The claim B makes is geometric: gl.LINES cannot vary width, so each segment is
expanded into a quad and widened along the screen-space perpendicular, with the
width coming from density. That claim is checkable on paper — this recomputes
the expansion the vertex shader performs and draws the result, so the geometry
can be inspected without a GPU in the loop.

Rungs:
  01  expansion — one segment becoming two triangles, and why the perpendicular
  02  taper — the real web as hairlines against the same web as ribbons

Usage: uv run --with matplotlib --with numpy python scripts/plot_ribbons.py
Figures land in docs/assets/04-ribbons/.
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import BG as FIG_BG
from plot_assets import (
    DIM,
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    RED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    saturated_magma,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "04-ribbons"
MAP = Path.home() / ".ytk" / "map.json"

# Mirrors mapRenderer.ts: hw = width * (.35 + .65 * min(den * 1.6, 1)) / depth
WIDTH = 0.0075
TAPER_FLOOR, TAPER_SPAN = 0.35, 0.65


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=FIG_BG)
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def legend(ax, **kw):
    return ax.legend(fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT, **kw)


def half_width(den):
    """The vertex shader's taper, in the same terms."""
    return WIDTH * (TAPER_FLOOR + TAPER_SPAN * np.minimum(den * 1.6, 1.0))


def load_strands():
    data = json.loads(MAP.read_text())
    out = []
    for fil in data["all"]["web"]["filaments"]:
        f = np.asarray(fil, float)
        den = f[:, 4] if f.shape[1] > 4 else np.ones(len(f))
        out.append((f[:, :2], den))
    return out


def fig01():
    """One segment becoming two triangles. The whole of feature B, drawn."""
    a, b = np.array([0.15, 0.35]), np.array([0.85, 0.62])
    d = (b - a) / np.linalg.norm(b - a)
    n = np.array([-d[1], d[0]])
    hw = 0.075

    fig, top = figure(
        14.0,
        6.6,
        1,
        "a line is triangles in costume",
        "How one segment becomes a ribbon the GPU can actually draw",
        "gl.LINES has no per-vertex width, so the quad is built in the vertex "
        "shader from both endpoints and a side attribute",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1.0, 1.0], left=0.03, right=1 - MARGIN - 0.02, top=top, bottom=0.06
    )

    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "what gl.LINES draws")
    ax.plot([a[0], b[0]], [a[1], b[1]], color=DIM, lw=1.4)
    ax.scatter(*a, s=60, color=GOLD, zorder=3)
    ax.scatter(*b, s=60, color=GOLD, zorder=3)
    ax.annotate("a", a + np.array([-0.05, 0.05]), color=TEXT, fontsize=11)
    ax.annotate("b", b + np.array([0.03, -0.02]), color=TEXT, fontsize=11)
    ax.text(
        0.5,
        0.12,
        "two vertices, one width for every strand\nno matter what density it carries",
        transform=ax.transAxes,
        ha="center",
        color=MUTED,
        fontsize=TICK_SIZE,
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal")

    ax = fig.add_subplot(gs[1])
    style_axes(ax)
    panel_title(ax, "what the vertex shader builds")
    corners = np.array([a + n * hw, a - n * hw, b - n * hw, b + n * hw])
    ax.add_patch(plt.Polygon(corners, closed=True, facecolor=GOLD, alpha=0.16, edgecolor="none"))
    # The two triangles, drawn apart so the winding is visible.
    for tri, col in ((corners[[0, 1, 2]], GOLD), (corners[[0, 2, 3]], RED)):
        ax.add_patch(plt.Polygon(tri, closed=True, fill=False, edgecolor=col, lw=1.6))
    ax.plot([a[0], b[0]], [a[1], b[1]], color=DIM, ls="--", lw=1.1)
    for p, lab in ((a, "a"), (b, "b")):
        ax.scatter(*p, s=45, color=TEXT, zorder=4)
        ax.annotate(lab, p + np.array([0.0, -0.07]), color=TEXT, fontsize=10, ha="center")
    ax.annotate(
        "",
        xy=a + n * hw,
        xytext=a,
        arrowprops={"arrowstyle": "->", "color": "#7fd4ff", "lw": 1.6},
    )
    ax.annotate("side = +1", a + n * hw + np.array([0.02, 0.03]), color="#7fd4ff", fontsize=9)
    ax.annotate("side = −1", a - n * hw + np.array([0.02, -0.06]), color="#7fd4ff", fontsize=9)
    ax.text(
        0.5,
        0.06,
        "six vertices, two triangles — width is now per-vertex,\n"
        "offset along the perpendicular to the segment",
        transform=ax.transAxes,
        ha="center",
        color=MUTED,
        fontsize=TICK_SIZE,
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal")
    save(fig, "01-quad-expansion.png")


def fig02(strands):
    """The taper, on the real web. This is what the width buys."""
    cmap = saturated_magma()
    dens = np.concatenate([d for _, d in strands])
    hw = half_width(dens)

    fig, top = figure(
        15.5,
        7.0,
        2,
        "width carries density",
        "The same web as hairlines, and as ribbons",
        f"{len(strands)} strands  ·  density {dens.min():.2f}-{dens.max():.2f}  ·  "
        f"half-width {hw.min() * 1e3:.1f}-{hw.max() * 1e3:.1f} (×10⁻³ clip units)",
    )
    gs = fig.add_gridspec(
        1, 3, width_ratios=[1.0, 1.0, 0.82], left=0.03, right=1 - MARGIN - 0.02, top=top, bottom=0.1
    )

    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    ax.set_facecolor("#000000")
    panel_title(ax, "gl.LINES — one width for everything")
    for xy, _ in strands:
        ax.plot(xy[:, 0], xy[:, 1], color=GOLD, lw=1.1, solid_capstyle="round")
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])

    ax = fig.add_subplot(gs[1])
    style_axes(ax)
    ax.set_facecolor("#000000")
    panel_title(ax, "ribbons — width from density")
    for xy, den in strands:
        w = half_width(den)
        seg_w = 0.5 * (w[:-1] + w[1:])
        seg_d = 0.5 * (den[:-1] + den[1:])
        for i in range(len(xy) - 1):
            ax.plot(
                xy[i : i + 2, 0],
                xy[i : i + 2, 1],
                color=cmap(float(np.clip(0.35 + 0.6 * seg_d[i], 0, 1))),
                lw=seg_w[i] / WIDTH * 2.6,
                solid_capstyle="round",
            )
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])

    ax = fig.add_subplot(gs[2])
    style_axes(ax)
    panel_title(ax, "half-width across all vertices")
    ax.hist(hw * 1e3, bins=40, color=GOLD)
    ax.axvline(WIDTH * 1e3, color=RED, ls="--", lw=1.6, label=f"uniform width ({WIDTH * 1e3:.1f})")
    ax.set_xlabel("half-width / 10⁻³ clip units")
    ax.set_ylabel("vertices")
    legend(ax, loc="upper right")
    save(fig, "02-density-taper.png")


def main():
    strands = load_strands()
    dens = np.concatenate([d for _, d in strands])
    fig01()
    fig02(strands)
    print()
    print(f"  strands        {len(strands)}")
    print(f"  vertices       {len(dens)}")
    print(f"  density        {dens.min():.3f}-{dens.max():.3f} (median {np.median(dens):.3f})")
    hw = half_width(dens)
    print(f"  half-width     {hw.min() * 1e3:.2f}-{hw.max() * 1e3:.2f} x10^-3 clip units")
    print(f"  thickest/thin  {hw.max() / hw.min():.2f}x")


if __name__ == "__main__":
    main()
