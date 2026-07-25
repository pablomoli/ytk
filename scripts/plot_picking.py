"""Ground-truth figures for GPU colour-ID picking (#101 fix 2).

The matplotlib witness, same role it played for the fog series: an independent
reimplementation of what the renderer claims to do, so the claim can be checked
against something not written by the same hand as the shader. It has already
earned its keep twice here — see the PICK_PAD story in mapRenderer.ts.

Rungs:
  01  cost — the linear scan against the block read as the corpus grows
  02  encoding — an id surviving the round trip through three bytes
  03  agreement — where the block read and the old 12px scan disagree
  04  measured — idle frame rate and hover cost from a real browser

House style is imported from plot_assets rather than restated, so these can
never drift from docs/assets/fog/.

Usage: uv run --with matplotlib --with numpy python scripts/plot_picking.py
Figures land in docs/assets/picking/.
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
    BLUE,
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
    punch,
    saturated_magma,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "picking"
MAP = Path.home() / ".ytk" / "map.json"
MEASURED = OUTDIR / "measured.json"

# Mirrors mapRenderer.ts.
SCAN_RADIUS = 12.0  # the old pick()'s distance < 144, and now the block radius
PICK_PAD = 2.0  # PICK_PAD
CANVAS = 1200  # px, square, for the agreement grid


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=FIG_BG)
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def legend(ax, **kw):
    return ax.legend(fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT, **kw)


def load_points():
    """Screen-space point centres and diameters at the overview resting state.

    At overview the renderer draws the 2D layout (dim = 0), so the camera
    reduces to a scale and an offset, and the relative geometry — all the
    agreement test depends on — is exact.
    """
    data = json.loads(MAP.read_text())
    pts = data["points"]
    xy = np.array([[p["x"], p["y"]] for p in pts], dtype=float)
    r = np.array([p.get("r", 0) for p in pts], dtype=float)
    has_c3 = np.array([1.0 if p.get("c3") else 0.0 for p in pts])
    size = 3.2 + r * 1.8 + has_c3 * 0.8  # the size attribute, from draw()
    # gl_PointSize = clamp(size * zoom / depth * dpr, 1.8, 26 * dpr); at rest
    # zoom = 1, depth = 1.35, dpr = 1.
    diam = np.clip(size / 1.35, 1.8, 26.0)
    lo, hi = xy.min(0), xy.max(0)
    screen = (xy - lo) / (hi - lo).max() * (CANVAS * 0.86) + CANVAS * 0.07
    screen[:, 1] = CANVAS - screen[:, 1]
    return screen, diam


def fig01():
    """The complexity claim, in the only unit that matters: work per hover."""
    n = np.logspace(1, 6, 240)
    block = (2 * SCAN_RADIUS + 1) ** 2  # pixels read, constant in n

    fig, top = figure(
        11.0,
        6.2,
        1,
        "the cost of a hover",
        "What does it cost to answer 'what is under the cursor?'",
        f"the scan projects every point; the block read touches {block:.0f} pixels "
        f"whatever the corpus does",
    )
    gs = fig.add_gridspec(1, 1, left=0.085, right=1 - MARGIN - 0.02, top=top, bottom=0.13)
    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "work per hover event, relative")

    ax.loglog(n, n, color=RED, lw=2.2, label="CPU scan — project every point, O(n)")
    ax.loglog(
        n,
        np.full_like(n, block),
        color=GOLD,
        lw=2.2,
        label=f"GPU colour-ID — one {block:.0f}px block read, O(1)",
    )
    ax.axvline(4067, color=DIM, ls="--", lw=1.2)
    ax.annotate(
        "the map today\n4,067 points",
        xy=(4067, 4067),
        xytext=(220, 60000),
        color=MUTED,
        fontsize=TICK_SIZE,
        arrowprops={"arrowstyle": "->", "color": DIM, "lw": 1.1},
    )
    ax.annotate(
        "the lines cross at ~625 points:\nbelow it the scan is cheaper,\nand nobody would notice",
        xy=(625, 625),
        xytext=(14, 4),
        color=MUTED,
        fontsize=TICK_SIZE,
        arrowprops={"arrowstyle": "->", "color": DIM, "lw": 1.1},
    )
    ax.set_xlabel("points in the corpus")
    ax.set_ylabel("relative work per hover")
    legend(ax, loc="upper left")
    save(fig, "01-cost-scaling.png")


def fig02():
    """An id is an integer wearing a costume. Show the costume, and the seam."""
    ids = np.arange(1, 4068)
    r, g, b = ids % 256, (ids // 256) % 256, (ids // 65536) % 256
    decoded = r + (g << 8) + (b << 16)

    fig, top = figure(
        14.0,
        6.0,
        2,
        "the id in three bytes",
        "Colour is an integer wearing a costume — does it survive the trip?",
        "no blending, no antialiasing on this pass: a filtered edge pixel "
        "would decode to an id that names nothing",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1.25, 1.0], left=0.062, right=1 - MARGIN - 0.02, top=top, bottom=0.135
    )

    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "the three channels across the corpus")
    ax.plot(ids, r, color=RED, lw=0.5, label="red   = id mod 256")
    ax.plot(ids, g, color=GOLD, lw=1.6, label="green = (id / 256) mod 256")
    ax.plot(ids, b, color=BLUE, lw=1.6, label="blue  = (id / 65536) mod 256")
    ax.set_xlabel("point id")
    ax.set_ylabel("byte value")
    legend(ax, loc="upper left")

    ax = fig.add_subplot(gs[1])
    style_axes(ax)
    panel_title(ax, "round trip: decoded − original")
    ax.plot(ids, decoded - ids, color=GOLD, lw=1.6)
    ax.set_ylim(-1, 1)
    ax.set_xlabel("point id")
    ax.set_ylabel("error")
    ax.text(
        0.5,
        0.56,
        f"exact for all {len(ids):,} ids",
        transform=ax.transAxes,
        ha="center",
        color=TEXT,
        fontsize=12,
    )
    ax.text(
        0.5,
        0.42,
        "headroom before a fourth byte: 16,777,215",
        transform=ax.transAxes,
        ha="center",
        color=MUTED,
        fontsize=TICK_SIZE,
    )
    save(fig, "02-id-encoding.png")


def fig03(screen, diam):
    """Does the block read pick what the scan picked?

    CPU model — nearest centre within SCAN_RADIUS wins.
    GPU model — each point paints a disc of (visual diameter + PICK_PAD); the
                block read takes the painted pixel nearest the cursor. A pixel
                of point i lies at distance >= d_i - r_i, so the winner is the
                point minimising (distance to centre - own radius).
    """
    rng = np.random.default_rng(20260724)
    probes = rng.uniform(0, CANVAS, size=(6000, 2))
    pick_r = (diam + PICK_PAD) / 2.0

    d = np.linalg.norm(probes[:, None, :] - screen[None, :, :], axis=2)
    within = d <= SCAN_RADIUS
    cpu = np.where(within.any(1), np.argmin(np.where(within, d, np.inf), axis=1), -1)
    edge = np.maximum(d - pick_r[None, :], 0.0)
    reach = edge <= SCAN_RADIUS
    gpu = np.where(reach.any(1), np.argmin(np.where(reach, edge, np.inf), axis=1), -1)

    both = (cpu >= 0) & (gpu >= 0)
    agree = (cpu == gpu) & both
    cpu_only = (cpu >= 0) & (gpu < 0)
    gpu_only = (gpu >= 0) & (cpu < 0)
    differ = both & (cpu != gpu)
    n_hit = int((cpu >= 0).sum())
    rate = 100.0 * agree.sum() / max(n_hit, 1)

    fig, top = figure(
        15.0,
        7.6,
        3,
        "agreement with the scan it replaces",
        "Does reading a pixel pick the same note the scan picked?",
        f"{rate:.1f}% of {n_hit:,} scan hits  ·  {int(cpu_only.sum())} positions where the scan "
        f"hit and picking misses  ·  6,000 probes",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1.06, 1.0], left=0.05, right=1 - MARGIN - 0.02, top=top, bottom=0.135
    )

    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "where the two models disagree")
    # Same treatment the fog series gives its cloud: the magma ramp keyed to
    # local density and gamma-lifted, so the crowded neighbourhoods — which is
    # exactly where the two models can disagree — read bright.
    cmap = saturated_magma()
    knn = np.sort(np.linalg.norm(screen[:, None, :] - screen[None, :, :], axis=2)[:, :64], axis=1)[
        :, 8
    ]
    dens = 1.0 / np.maximum(knn, 1e-6)
    # Rank-normalised, not min-max: one very dense cluster owns the top of the
    # raw range and squashes everything else into magma's near-black end — the
    # same trap the fog notes describe at a median density of 0.17.
    dens = np.argsort(np.argsort(dens)) / max(len(dens) - 1, 1)
    ax.scatter(
        screen[:, 0],
        screen[:, 1],
        c=punch(dens),
        cmap=cmap,
        vmin=0,
        vmax=1,
        s=3 + 10 * dens,
        alpha=0.5,
        linewidths=0,
        zorder=1,
    )
    ax.scatter(probes[agree, 0], probes[agree, 1], s=2.4, color=GOLD, zorder=2, label="agree")
    ax.scatter(
        probes[cpu_only, 0],
        probes[cpu_only, 1],
        s=11,
        color=RED,
        zorder=4,
        label=f"scan hit, pick missed ({int(cpu_only.sum())})",
    )
    ax.scatter(
        probes[gpu_only, 0],
        probes[gpu_only, 1],
        s=9,
        color=BLUE,
        zorder=3,
        label=f"pick hit, scan missed ({int(gpu_only.sum())})",
    )
    ax.scatter(
        probes[differ, 0],
        probes[differ, 1],
        s=13,
        color="#9159ff",
        zorder=5,
        label=f"both hit, different point ({int(differ.sum())})",
    )
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    legend(ax, loc="upper right")

    ax = fig.add_subplot(gs[1])
    style_axes(ax)
    panel_title(ax, "reach from a point's centre")
    # Two different quantities, and conflating them is what briefly made a
    # 22px pad look reasonable: the sprite stays small on purpose, and the
    # forgiveness comes from the block search around it.
    ax.hist(pick_r, bins=30, color=DIM, label=f"painted footprint (pad {PICK_PAD:g})")
    ax.hist(
        pick_r + SCAN_RADIUS,
        bins=30,
        color=GOLD,
        label=f"+ {SCAN_RADIUS:g}px block search = what the cursor feels",
    )
    ax.axvline(
        SCAN_RADIUS, color=RED, ls="--", lw=1.8, label=f"old scan tolerance ({SCAN_RADIUS:g}px)"
    )
    ax.set_xlabel("distance from centre at which a point can still be picked / px")
    ax.set_ylabel("points")
    legend(ax, loc="upper center")
    save(fig, "03-scan-agreement.png")

    return {
        "probes": len(probes),
        "scan_hits": n_hit,
        "agree_pct": round(rate, 1),
        "scan_only": int(cpu_only.sum()),
        "pick_only": int(gpu_only.sum()),
        "differ": int(differ.sum()),
    }


def fig04():
    """Measured in a real browser, not modelled. Skipped if no run exists."""
    if not MEASURED.exists():
        print(f"skip 04 — no {MEASURED.name}; run scripts/measure_picking.mjs first")
        return
    m = json.loads(MEASURED.read_text())
    before, after = m["before"], m["after"]

    fig, top = figure(
        15.0,
        6.6,
        4,
        "measured, not modelled",
        "What the two fixes actually cost in a running browser",
        f"{m['runs']} runs  ·  {m['idle_seconds']}s idle window  ·  "
        f"{m['hover_events']} synthetic hovers  ·  {m['agent']}",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1.0, 1.0], left=0.075, right=1 - MARGIN - 0.02, top=top, bottom=0.15
    )

    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "rAF calls the map schedules while nothing moves (#101 fix 1)")
    vend_b = before.get("runs", [{}])[0].get("vendor_fps", 0)
    vend_a = after.get("runs", [{}])[0].get("vendor_fps", 0)
    ramp = saturated_magma()
    hot, cool = ramp(0.62), ramp(0.86)  # same ramp the cloud is painted with
    ax.bar(
        ["before", "after"],
        [before["idle_fps"], after["idle_fps"]],
        color=[hot, cool],
        width=0.55,
        label="map render loop",
    )
    ax.bar(
        ["before", "after"],
        [vend_b, vend_a],
        bottom=[before["idle_fps"], after["idle_fps"]],
        color=DIM,
        width=0.55,
        label="React scheduler (unrelated)",
    )
    for i, value in enumerate([before["idle_fps"], after["idle_fps"]]):
        ax.text(
            i,
            value + max(before["idle_fps"], 1) * 0.04,
            f"{value:.1f} / s",
            ha="center",
            color=TEXT,
            fontsize=11,
        )
    # Attribution matters here: the totals barely move, because when the map
    # parks React simply takes the frames it used to occupy. Only the split
    # shows the loop going to zero.
    ax.set_ylabel("rAF calls / second at rest")
    legend(ax, loc="upper center")

    ax = fig.add_subplot(gs[1])
    style_axes(ax)
    panel_title(ax, "time to resolve one hover (#101 fix 2)")
    bars = ax.bar(
        ["before", "after"],
        [before["hover_ms"], after["hover_ms"]],
        color=[hot, cool],
        width=0.55,
    )
    for rect, value in zip(bars, [before["hover_ms"], after["hover_ms"]]):
        ax.text(
            rect.get_x() + rect.get_width() / 2,
            rect.get_height() + max(before["hover_ms"], 0.01) * 0.03,
            f"{value:.3f} ms",
            ha="center",
            color=TEXT,
            fontsize=11,
        )
    ax.set_ylabel("median ms per hover")
    save(fig, "04-measured.png")


def main():
    screen, diam = load_points()
    print(
        f"points: {len(screen):,}   visual diameter "
        f"{diam.min():.1f}–{diam.max():.1f}px (median {np.median(diam):.1f})"
    )
    fig01()
    fig02()
    stats = fig03(screen, diam)
    fig04()
    print()
    for key, value in stats.items():
        print(f"  {key:12} {value}")


if __name__ == "__main__":
    main()
