"""Ground-truth figures for GPU colour-ID picking (#101 fix 2).

The matplotlib witness, same role it played for the fog series: an independent
reimplementation of what the renderer claims to do, so the claim can be checked
against something that was not written by the same hand as the shader.

Three rungs:
  01  cost — the linear scan against the pixel read as the corpus grows
  02  encoding — how an integer id survives a round trip through three bytes
  03  agreement — where the painted footprint and the old 12px scan disagree

Usage: uv run --with matplotlib --with numpy python scripts/plot_picking.py
Figures land in docs/assets/picking/.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets" / "picking"
MAP = Path.home() / ".ytk" / "map.json"

# Mirrors mapRenderer.ts: the old scan's tolerance, and the pick pass's pad.
SCAN_RADIUS = 12.0  # distance < 144 in pick(), i.e. 12px
PICK_PAD = 2.0  # PICK_PAD in mapRenderer.ts
CANVAS = 1200  # px, square, for the agreement grid

BG = "#0b0b0f"
FG = "#e8e6e3"
GOLD = "#e2b04a"
BLUE = "#6ba7d4"
RED = "#d4674f"


def _style(ax, title=None):
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_color("#3a3a44")
    ax.tick_params(colors="#8a8a96", labelsize=8)
    ax.xaxis.label.set_color("#8a8a96")
    ax.yaxis.label.set_color("#8a8a96")
    if title:
        ax.set_title(title, color=FG, fontsize=10, pad=10)


def _fig(w, h):
    fig, axes = plt.subplots(1, w, figsize=(h[0], h[1]))
    fig.patch.set_facecolor(BG)
    return fig, axes


def _save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=150, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    size = path.stat().st_size // 1024
    print(
        f"wrote {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}"
        f"  ({size}KB)"
    )


def load_points():
    """Screen-space point centres and radii at the overview resting state.

    At overview the renderer draws the 2D layout (dim = 0), so the camera
    reduces to a scale and an offset and the relative geometry — which is all
    the agreement test depends on — is exact.
    """
    data = json.loads(MAP.read_text())
    pts = data["points"]
    xy = np.array([[p["x"], p["y"]] for p in pts], dtype=float)
    r = np.array([p.get("r", 0) for p in pts], dtype=float)
    has_c3 = np.array([1.0 if p.get("c3") else 0.0 for p in pts])
    # size attribute, straight out of the packing in draw()
    size = 3.2 + r * 1.8 + has_c3 * 0.8
    # gl_PointSize = clamp(size * zoom / depth * dpr, 1.8, 26 * dpr); at the
    # overview resting state zoom = 1, depth = 1.35, dpr = 1.
    px_diam = np.clip(size / 1.35, 1.8, 26.0)
    lo, hi = xy.min(0), xy.max(0)
    span = (hi - lo).max()
    screen = (xy - lo) / span * (CANVAS * 0.86) + CANVAS * 0.07
    screen[:, 1] = CANVAS - screen[:, 1]
    return screen, px_diam


def fig01_cost():
    """The complexity claim, in the only terms that matter: work per hover."""
    n = np.logspace(1, 6, 200)
    # The scan projects every point: ~4 trig calls + a distance, per point.
    scan = n
    # The pixel read is one draw pass plus one readPixels, independent of n.
    gpu = np.full_like(n, 1.0)
    fig, ax = plt.subplots(figsize=(8, 4.6))
    fig.patch.set_facecolor(BG)
    _style(ax, "Work per hover event")
    ax.loglog(n, scan, color=RED, lw=2, label="CPU scan — project every point, O(n)")
    ax.loglog(n, gpu, color=GOLD, lw=2, label="GPU colour-ID — one pixel read, O(1)")
    ax.axvline(4067, color=BLUE, ls="--", lw=1)
    ax.annotate(
        "the map today\n4,067 points",
        xy=(4067, 4067),
        xytext=(300, 30000),
        color=BLUE,
        fontsize=8,
        arrowprops={"arrowstyle": "->", "color": BLUE, "lw": 1},
    )
    ax.set_xlabel("points in the corpus")
    ax.set_ylabel("relative work per hover")
    leg = ax.legend(facecolor=BG, edgecolor="#3a3a44", fontsize=8)
    for text in leg.get_texts():
        text.set_color(FG)
    fig.suptitle(
        "01  ·  the cost stops scaling with the corpus",
        color=FG,
        fontsize=12,
        x=0.02,
        ha="left",
    )
    _save(fig, "01-cost-scaling.png")


def fig02_encoding():
    """An id is an integer wearing a costume. Show the costume, and the seam."""
    ids = np.arange(1, 4068)
    r = ids % 256
    g = (ids // 256) % 256
    b = (ids // 65536) % 256
    decoded = r + (g << 8) + (b << 16)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    fig.patch.set_facecolor(BG)

    _style(axes[0], "the three bytes across the corpus")
    axes[0].plot(ids, r, color=RED, lw=0.6, label="red   = id mod 256")
    axes[0].plot(ids, g, color="#7fc47f", lw=1.4, label="green = (id / 256) mod 256")
    axes[0].plot(ids, b, color=BLUE, lw=1.4, label="blue  = (id / 65536) mod 256")
    axes[0].set_xlabel("point id")
    axes[0].set_ylabel("byte value")
    leg = axes[0].legend(facecolor=BG, edgecolor="#3a3a44", fontsize=7.5)
    for text in leg.get_texts():
        text.set_color(FG)

    _style(axes[1], "round trip: decoded − original")
    axes[1].plot(ids, decoded - ids, color=GOLD, lw=1.5)
    axes[1].set_ylim(-1, 1)
    axes[1].set_xlabel("point id")
    axes[1].set_ylabel("error")
    axes[1].text(
        0.5,
        0.5,
        f"exact for all {len(ids):,} ids\n(headroom: 16,777,215)",
        transform=axes[1].transAxes,
        ha="center",
        va="center",
        color=FG,
        fontsize=10,
    )
    fig.suptitle(
        "02  ·  the id survives the round trip through three bytes",
        color=FG,
        fontsize=12,
        x=0.02,
        ha="left",
    )
    _save(fig, "02-id-encoding.png")


def fig03_agreement(screen, diam):
    """The real check: does the painted footprint pick what the scan picked?

    CPU model  — nearest centre within SCAN_RADIUS wins.
    GPU model  — each point paints a disc of (visual diameter + PICK_PAD); the
                 block read then takes the painted pixel nearest the cursor.
                 A pixel of point i sits at distance >= d_i - r_i from the
                 cursor, so the nearest painted pixel is the point minimising
                 (distance to centre - own radius), within the block.
    """
    rng = np.random.default_rng(20260724)
    probes = rng.uniform(0, CANVAS, size=(6000, 2))
    pick_r = (diam + PICK_PAD) / 2.0

    d = np.linalg.norm(probes[:, None, :] - screen[None, :, :], axis=2)

    within = d <= SCAN_RADIUS
    cpu = np.where(within.any(1), np.argmin(np.where(within, d, np.inf), axis=1), -1)

    # Distance from the cursor to the nearest pixel each point paints.
    edge = np.maximum(d - pick_r[None, :], 0.0)
    reach = edge <= SCAN_RADIUS
    gpu = np.where(reach.any(1), np.argmin(np.where(reach, edge, np.inf), axis=1), -1)

    both = (cpu >= 0) & (gpu >= 0)
    agree = (cpu == gpu) & both
    cpu_only = (cpu >= 0) & (gpu < 0)
    gpu_only = (gpu >= 0) & (cpu < 0)
    differ = both & (cpu != gpu)
    hit = cpu >= 0

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4))
    fig.patch.set_facecolor(BG)

    _style(axes[0], "where the two models disagree")
    axes[0].scatter(screen[:, 0], screen[:, 1], s=1.2, color="#4a4a56", zorder=1)
    axes[0].scatter(probes[agree, 0], probes[agree, 1], s=2.5, color=GOLD, zorder=2, label="agree")
    axes[0].scatter(
        probes[cpu_only, 0],
        probes[cpu_only, 1],
        s=9,
        color=RED,
        zorder=3,
        label="scan hit, pick missed",
    )
    axes[0].scatter(
        probes[gpu_only, 0],
        probes[gpu_only, 1],
        s=9,
        color=BLUE,
        zorder=3,
        label="pick hit, scan missed",
    )
    axes[0].scatter(
        probes[differ, 0],
        probes[differ, 1],
        s=14,
        color="#c77fd4",
        zorder=4,
        label="both hit, different point",
    )
    axes[0].set_aspect("equal")
    axes[0].set_xticks([])
    axes[0].set_yticks([])
    leg = axes[0].legend(facecolor=BG, edgecolor="#3a3a44", fontsize=7.5, loc="upper right")
    for text in leg.get_texts():
        text.set_color(FG)

    # Two different quantities, and conflating them is what made PICK_PAD=22
    # look reasonable: the sprite is deliberately small, and the forgiveness
    # comes from the block search around it. What the user feels is the sum.
    _style(axes[1], f"reach from a point's centre (PICK_PAD = {PICK_PAD:g})")
    axes[1].hist(
        pick_r, bins=30, color="#6a5a30", alpha=0.9, label=f"painted footprint (pad {PICK_PAD:g})"
    )
    axes[1].hist(
        pick_r + SCAN_RADIUS,
        bins=30,
        color=GOLD,
        alpha=0.9,
        label=f"+ {SCAN_RADIUS:g}px block search = what the cursor feels",
    )
    axes[1].axvline(
        SCAN_RADIUS, color=RED, ls="--", lw=1.8, label=f"old scan tolerance ({SCAN_RADIUS:g}px)"
    )
    axes[1].set_xlabel("distance from centre at which the point can still be picked / px")
    axes[1].set_ylabel("points")
    leg = axes[1].legend(facecolor=BG, edgecolor="#3a3a44", fontsize=7.5)
    for text in leg.get_texts():
        text.set_color(FG)

    n_hit = int(hit.sum())
    rate = 100.0 * agree.sum() / max(n_hit, 1)
    fig.suptitle(
        f"03  ·  agreement with the scan it replaces — {rate:.1f}% of {n_hit:,} scan hits",
        color=FG,
        fontsize=12,
        x=0.02,
        ha="left",
    )
    _save(fig, "03-scan-agreement.png")

    return {
        "probes": len(probes),
        "scan_hits": n_hit,
        "agree": int(agree.sum()),
        "agree_pct": rate,
        "scan_only": int(cpu_only.sum()),
        "pick_only": int(gpu_only.sum()),
        "differ": int(differ.sum()),
        "median_pick_r": float(np.median(pick_r)),
    }


def main():
    screen, diam = load_points()
    print(
        f"points: {len(screen):,}   visual diameter: "
        f"{diam.min():.1f}–{diam.max():.1f}px (median {np.median(diam):.1f})"
    )
    fig01_cost()
    fig02_encoding()
    stats = fig03_agreement(screen, diam)
    print()
    for key, value in stats.items():
        print(f"  {key:16} {value:.1f}" if isinstance(value, float) else f"  {key:16} {value}")


if __name__ == "__main__":
    main()
