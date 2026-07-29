"""Trunk radius against bucket size, on the real vault buckets.

The complaint this settles: a one-note bucket and a two-thousand-note bucket
came out with near-identical trunks. Top row is the shipped scheme, middle row
is bottom-up Murray. Height is identical between the rows on purpose, so the
only variable is how girth is decided.

    uv run --with matplotlib python scripts/plot_garden_allometry.py

Bucket sizes come from the live hub when it is reachable and fall back to the
values recorded on 2026-07-28 otherwise, so the figure stays reproducible.
Envelope height mirrors web/src/lib/garden/envelope.ts; trunk radius mirrors
web/src/lib/garden/girth.ts.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from plot_assets import BG, CYAN, DIM, FRAME, GOLD, MUTED, PANEL, TEXT, use_house_font
from plot_garden_taper import Node, chains, murray_girth, outline, resample, walk

use_house_font()

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "14-garden-allometry"
DPI = 200

# Recorded 2026-07-28; used when the hub is not running.
FALLBACK = [
    ("epicmap", 2065),
    ("ai-building", 444),
    ("visual-craft", 76),
    ("youtube-channel", 23),
    ("mind-systems", 16),
    ("combat-sports", 12),
    ("film", 9),
    ("eating", 4),
    ("adhd", 2),
    ("playful-tools", 1),
]

TIP_RADIUS = 0.030
EXPONENT = 2.5
TIPS_PER_NOTE = 1.5
TIP_BUDGET = 4000

# Shipped scheme: the trunk always started at weight 1, so per-bucket variation
# came only from this scale factor -- the whole of the equal-width complaint.
OLD_GIRTH = 0.12


def buckets() -> list[tuple[str, int]]:
    try:
        with urllib.request.urlopen("http://localhost:6969/api/garden", timeout=2) as r:
            data = json.load(r)
        got = [(b["bucket"], int(b["n_notes"])) for b in data.get("buckets", [])]
        if got:
            return sorted(got, key=lambda kv: -kv[1])
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        pass
    try:
        with urllib.request.urlopen("http://localhost:6969/api/grove", timeout=2) as r:
            data = json.load(r)
        got = [(b["bucket"], int(b["n_notes"])) for b in data.get("buckets", [])]
        if got:
            return sorted(got, key=lambda kv: -kv[1])
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        pass
    return FALLBACK


def envelope_height(n: int, cap: int, max_height: float = 1.0) -> float:
    """Mirrors envelopeFor: sqrt of the note share, floored at 18%."""
    t = min(1.0, math.sqrt(min(n, cap) / max(1, cap)))
    return max(1e-4, max_height * (0.18 + 0.82 * t))


def tip_count(n: float) -> float:
    return min(TIP_BUDGET, max(3.0, TIPS_PER_NOTE * n))


# Absolute girth scale is a free parameter in both schemes (r_tip here, the
# girth knob there), so both are anchored to the same trunk on the largest
# bucket. What the figure compares is how each thins from that anchor.
TARGET_TRUNK = 0.135


def murray_trunk(n: float, cap: int) -> float:
    """r_trunk = r_tip * tips^(1/exponent) -- what the bottom-up pass yields."""
    return TARGET_TRUNK * (tip_count(n) / tip_count(cap)) ** (1.0 / EXPONENT)


def old_trunk(n: float, cap: int) -> float:
    size = 0.45 + 0.55 * math.sqrt(min(n, cap) / max(1, cap))
    return TARGET_TRUNK * size / (0.45 + 0.55)


def scaled_tree(n: int, cap: int, trunk: float, height: float) -> Node:
    """A silhouette whose structure is plausible and whose trunk is exact.

    Drawn depth is capped for legibility, so the tree is Murray-ed for shape
    and then rescaled to the trunk radius implied by the true tip count.
    """
    from plot_garden_taper import build

    depth = int(min(6, max(1, round(math.log2(max(2, tip_count(n)))) - 3)))
    root = build(depth=depth, run=5, step=0.30)

    pts = np.array([node.pos for node in walk(root)])
    span = float(pts[:, 1].max() - pts[:, 1].min()) or 1.0
    k = height / span
    for node in walk(root):
        node.pos = node.pos * k

    murray_girth(root, TIP_RADIUS, EXPONENT)
    if root.radius > 0:
        s = trunk / root.radius
        for node in walk(root):
            node.radius *= s
    return root


def draw_row(ax, data, cap, scheme: str) -> None:
    x = 0.0
    for name, n in data:
        height = envelope_height(n, cap, max_height=3.0)
        trunk = murray_trunk(n, cap) if scheme == "murray" else old_trunk(n, cap)
        root = scaled_tree(n, cap, trunk, height)
        for node in walk(root):
            node.pos = node.pos + np.array([x, 0.0])
        for seq in chains(root):
            pts, rs, _ = resample(seq, "arc")
            ax.fill(*outline(pts, rs).T, color="#cdc7bb", alpha=0.72, linewidth=0)
        ax.text(
            x,
            -0.30,
            f"{name}\n{n}",
            color=MUTED,
            fontsize=7.6,
            ha="center",
            va="top",
            linespacing=1.4,
        )
        x += 2.05
    ax.set_xlim(-1.3, x - 0.75)
    ax.set_ylim(-1.15, 3.35)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(PANEL)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    data = buckets()
    cap = max(n for _, n in data)
    ordered = sorted(data, key=lambda kv: kv[1])

    fig = plt.figure(figsize=(16.0, 12.2), facecolor=BG)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.0, 1.0, 1.15], hspace=0.30)

    ax_old = fig.add_subplot(gs[0])
    draw_row(ax_old, ordered, cap, "old")
    ax_old.set_title(
        "A. shipped: trunk radius is a fixed girth times a size factor",
        color=TEXT,
        fontsize=13.5,
        pad=10,
    )

    ax_new = fig.add_subplot(gs[1])
    draw_row(ax_new, ordered, cap, "murray")
    ax_new.set_title(
        "B. bottom-up Murray: trunk radius is what the limb carries",
        color=TEXT,
        fontsize=13.5,
        pad=10,
    )

    ax = fig.add_subplot(gs[2])
    ax.set_facecolor(PANEL)
    ns = np.logspace(0, math.log10(cap), 220)
    ax.plot(
        ns,
        [old_trunk(v, cap) for v in ns],
        color=CYAN,
        linewidth=2.2,
        label="shipped",
    )
    ax.plot(
        ns,
        [murray_trunk(v, cap) for v in ns],
        color=GOLD,
        linewidth=2.2,
        label="Murray",
    )
    for name, n in data:
        ax.scatter([n], [murray_trunk(n, cap)], color=GOLD, s=26, zorder=4)
        ax.scatter([n], [old_trunk(n, cap)], color=CYAN, s=26, zorder=4)
        ax.annotate(
            name,
            xy=(n, murray_trunk(n, cap)),
            xytext=(0, 9),
            textcoords="offset points",
            color=MUTED,
            fontsize=8,
            ha="center",
        )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("notes in bucket", color=MUTED, fontsize=11)
    ax.set_ylabel("trunk radius", color=MUTED, fontsize=11)
    ax.tick_params(colors=MUTED, labelsize=9)
    for s in ax.spines.values():
        s.set_color(FRAME)
    ax.grid(True, which="both", color=DIM, linewidth=0.5, alpha=0.45)
    leg = ax.legend(facecolor=PANEL, edgecolor=FRAME, fontsize=10, loc="upper left")
    for t in leg.get_texts():
        t.set_color(TEXT)

    old_ratio = old_trunk(cap, cap) / old_trunk(min(n for _, n in data), cap)
    new_ratio = murray_trunk(cap, cap) / murray_trunk(min(n for _, n in data), cap)
    fig.suptitle(
        f"Garden allometry: trunk radius across the real buckets, 1 note to {cap:,}",
        color=TEXT,
        fontsize=17,
        y=0.965,
    )
    fig.text(
        0.5,
        0.055,
        f"Across a {cap:,}x range in notes, the shipped scheme spans only "
        f"{old_ratio:.2f}x in trunk radius; Murray spans {new_ratio:.1f}x. "
        "Height is identical in both rows, so girth is the only variable.\n"
        "Both axes are logarithmic: the shipped curve flattens because its size "
        "factor is bounded to [0.45, 1.0] by construction, while Murray follows "
        "tips^(1/2.5) with no ceiling but the node budget.",
        color=MUTED,
        fontsize=10.5,
        ha="center",
        linespacing=1.7,
    )

    out = OUTDIR / "02-trunk-allometry.png"
    fig.savefig(out, dpi=DPI, facecolor=BG, bbox_inches="tight")
    print(f"wrote {out}")
    print(f"shipped span {old_ratio:.3f}x   murray span {new_ratio:.2f}x")
    for name, n in sorted(data, key=lambda kv: kv[1]):
        print(f"  {n:>6}  {name:<16} old {old_trunk(n, cap):.4f}   new {murray_trunk(n, cap):.4f}")


if __name__ == "__main__":
    main()
