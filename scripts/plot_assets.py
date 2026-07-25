"""Regenerate every figure in docs/assets/01-fog/ under one house style.

The figures are post/blog material (see docs/assets/01-fog/linkedin-notes.md),
so they are reproducible from the live map payload rather than from ad-hoc
snippets. One style lives here: palette, framing, saturation, resolution.

    uv run --with matplotlib python scripts/plot_assets.py            # all
    uv run --with matplotlib python scripts/plot_assets.py --only 6   # one
    uv run --with matplotlib python scripts/plot_assets.py --refresh  # ignore cache

Derived geometry that takes real compute (historical tracer variants) is
cached in ~/.ytk/fog-assets-cache.json; --refresh recomputes it.
"""

from __future__ import annotations

import argparse
import json
import os
import textwrap
from pathlib import Path

import numpy as np

MAP = Path(os.path.expanduser("~/.ytk/map.json"))
CACHE = Path(os.path.expanduser("~/.ytk/fog-assets-cache.json"))
OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "01-fog"

# --- house style -----------------------------------------------------------
DPI = 200
BG = "#08080a"  # figure background
PANEL = "#000000"  # panel interior
FRAME = "#2e2e36"  # panel + figure border
TEXT = "#eceae7"
MUTED = "#9a968f"
GOLD = "#f2b950"  # strands
BLUE = "#5a8cff"
RED = "#ff4d6d"
PURPLE = "#9159ff"
CYAN = "#7fd4ff"
DIM = "#3a3a42"

KICKER_SIZE = 9.5
TITLE_SIZE = 16
META_SIZE = 10
PANEL_SIZE = 10.5
TICK_SIZE = 9

MARGIN = 0.035  # figure-fraction padding on every side
PANEL_PAD = 0.014  # gap between a panel's frame and its content cell


def saturated_magma():
    """magma with chroma pushed up ~35% — same palette, more punch."""
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    base = plt.get_cmap("magma")(np.linspace(0, 1, 256))
    hsv = mcolors.rgb_to_hsv(base[:, :3])
    hsv[:, 1] = np.clip(hsv[:, 1] * 1.35, 0, 1)
    hsv[:, 2] = np.clip(hsv[:, 2] * 1.06, 0, 1)
    base[:, :3] = mcolors.hsv_to_rgb(hsv)
    return mcolors.ListedColormap(base, name="magma_sat")


def punch(den: np.ndarray, gamma: float = 0.72) -> np.ndarray:
    """Gamma-lift normalized density so mid values reach the bright end of
    the ramp — the fog's median sits near 0.17, which magma renders nearly
    black at gamma 1."""
    return np.clip(den, 0, 1) ** gamma


def figure(w: float, ht: float, number: int, kicker: str, title: str, meta: str = ""):
    """Figure with a deliberate header block rather than a centred sentence.

    Left-aligned on the same margin as the panels, stacked as
    kicker (gold, letterspaced) / title (large) / hairline rule / meta
    (muted stats). Returns (fig, top) where top is the figure-fraction the
    panel area may start at — the header reserves real estate in inches, so
    it stays the same physical size whatever the figure's aspect.
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig = plt.figure(figsize=(w, ht), facecolor=BG)
    lines = textwrap.wrap(title, 78)
    inch = lambda v: 1 - v / ht  # inches from the top -> figure fraction

    fig.text(
        MARGIN,
        inch(0.40),
        " ".join(f"FIGURE {number:02d}"),
        color=GOLD,
        fontsize=KICKER_SIZE,
        fontweight="bold",
        va="baseline",
    )
    fig.text(
        MARGIN + 0.088, inch(0.40), kicker.upper(), color=MUTED, fontsize=KICKER_SIZE, va="baseline"
    )
    y = 0.78
    for line in lines:
        fig.text(MARGIN, inch(y), line, color=TEXT, fontsize=TITLE_SIZE, va="baseline")
        y += 0.30
    rule = y - 0.09
    fig.add_artist(
        Line2D(
            [MARGIN, 1 - MARGIN],
            [inch(rule)] * 2,
            transform=fig.transFigure,
            color=FRAME,
            linewidth=1.0,
        )
    )
    if meta:
        fig.text(MARGIN, inch(rule + 0.26), meta, color=MUTED, fontsize=META_SIZE, va="baseline")
    # leave room for the panel titles that sit under the header
    header = rule + (0.92 if meta else 0.62)
    return fig, inch(header)


def panel_title(ax, text: str, width: int = 46) -> None:
    ax.set_title(textwrap.fill(text, width), color=TEXT, fontsize=PANEL_SIZE, pad=13)


def fit3d(ax, pts: np.ndarray, pad: float = 0.03, zoom: float = 1.72) -> None:
    """Frame a 3D panel on its actual data extent.

    The original figures hardcoded (-1, 1) on every axis while the embedding
    spans roughly x -1.2..0.8, y -0.8..0.7 — the data drew itself into a
    corner and matplotlib's default 3D margins ate the rest. Limits from the
    data plus a proportional box aspect fill the panel without distorting
    proportions; zoom eats the residual margin.
    """
    lo, hi = pts.min(0), pts.max(0)
    centre = (lo + hi) / 2
    radius = float((hi - lo).max()) / 2 * (1 + pad)
    ax.set_xlim(centre[0] - radius, centre[0] + radius)
    ax.set_ylim(centre[1] - radius, centre[1] + radius)
    ax.set_zlim(centre[2] - radius, centre[2] + radius)
    # Cube limits keep proportions honest AND keep the axes filling its
    # subplot cell — a proportional box aspect makes matplotlib shrink the
    # axes to satisfy it, which reintroduces the dead space. All the real
    # gain comes from zoom, which eats the generous default 3D margin.
    ax.set_box_aspect((1, 1, 1), zoom=zoom)
    ax.set_axis_off()
    ax.set_facecolor(PANEL)


def style_axes(ax) -> None:
    """2D panel styling: dark interior, muted spines, readable ticks."""
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_color(FRAME)
    ax.tick_params(colors=MUTED, labelsize=TICK_SIZE)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)


def frame_panels(fig, pad: float = PANEL_PAD) -> None:
    """Border every panel and the figure itself. 3D axes report a bbox much
    larger than the drawn cube, so the frame is drawn on the subplot cell —
    which is exactly the region we now fill."""
    from matplotlib.patches import Rectangle

    for ax in fig.axes:
        if getattr(ax, "_is_colorbar", False):
            continue
        box = ax.get_position()
        fig.add_artist(
            Rectangle(
                (box.x0 - pad, box.y0 - pad),
                box.width + 2 * pad,
                box.height + 2 * pad,
                transform=fig.transFigure,
                facecolor="none",
                edgecolor=FRAME,
                linewidth=1.0,
                zorder=-5,
            )
        )
    edge = MARGIN / 2.4
    fig.add_artist(
        Rectangle(
            (edge, edge),
            1 - 2 * edge,
            1 - 2 * edge,
            transform=fig.transFigure,
            facecolor="none",
            edgecolor=FRAME,
            linewidth=1.4,
            zorder=10,
        )
    )


def save(fig, name: str) -> None:
    frame_panels(fig)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    import matplotlib.pyplot as plt

    plt.close(fig)


def fog_scatter(ax, xyz: np.ndarray, den: np.ndarray, cmap, alpha: float = 0.42):
    return ax.scatter(
        xyz[:, 0],
        xyz[:, 1],
        xyz[:, 2],
        c=punch(den),
        cmap=cmap,
        vmin=0,
        vmax=1,
        s=7 + 46 * den,
        alpha=alpha,
        linewidths=0,
    )


def strand_plot(ax, filaments, color: str = GOLD, taper: bool = True) -> None:
    """Draw strands; per-vertex density (5th column) tapers width + alpha."""
    for fil in filaments:
        f = np.asarray(fil, float)
        if taper and f.shape[1] >= 5:
            for i in range(len(f) - 1):
                dv = float((f[i, 4] + f[i + 1, 4]) / 2)
                ax.plot(
                    f[i : i + 2, 0],
                    f[i : i + 2, 1],
                    f[i : i + 2, 2],
                    color=color,
                    linewidth=0.7 + 3.0 * dv,
                    alpha=0.4 + 0.6 * min(dv * 2, 1),
                    solid_capstyle="round",
                )
        else:
            ax.plot(
                f[:, 0],
                f[:, 1],
                f[:, 2],
                color=color,
                linewidth=1.6,
                alpha=0.95,
                solid_capstyle="round",
            )


# --- data ------------------------------------------------------------------
def load():
    return json.loads(MAP.read_text())


def derived(data, refresh: bool = False) -> dict:
    """Historical/recomputed geometry the figures compare against."""
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text())

    from ytk import ridges

    print("computing derived geometry (cached afterwards)...")
    z3 = np.array([p["z3"] for p in data["points"]])
    doms = [p["dom"] for p in data["points"]]
    n_dom = len(data["all"]["domains"])
    h = ridges.silverman_bandwidth(z3)
    rng = np.random.default_rng(7)

    # uniform-bandwidth fog (pre-adaptive, figures 01/02)
    idx = rng.integers(0, len(z3), 6000)
    uni_xyz = z3[idx] + rng.normal(0, 1.6 * h, (6000, 3))
    raw = ridges.kde(z3, h, uni_xyz)
    uni_den = np.minimum(raw / np.percentile(raw, 99), 1.0)
    keep = uni_den >= 0.01

    # adaptive-bandwidth filaments (the scale-space verdict, figure 04)
    hi = ridges.knn_bandwidths(z3)
    seeds = z3[:: len(z3) // 2500 + 1]
    ada_pts = ridges.scms3(z3, hi, seeds)
    ada_strands = ridges.trace_filaments(z3, hi, ada_pts)

    # chained walkers (pre-tracer reconstruction, figure 05)
    uni_ridge = ridges.scms3(z3, h, seeds)
    chained = [ridges._smooth(c) for c in ridges._chain_points(uni_ridge)]

    # pre-trim strands (sequential-tracer equivalent, figure 07)
    pretrim = ridges.trace_filaments(z3, h, uni_ridge, dedupe=False)

    out = {
        "h": float(h),
        "uniform_fog": np.column_stack([uni_xyz[keep], uni_den[keep]]).round(3).tolist(),
        "adaptive_strands": [s.round(3).tolist() for s in ada_strands],
        "chained": [c.round(3).tolist() for c in chained],
        "pretrim": [s.round(3).tolist() for s in pretrim],
        "n_dom": n_dom,
        "doms": doms,
    }
    CACHE.write_text(json.dumps(out))
    print(f"cached -> {CACHE}")
    return out


# --- figures ---------------------------------------------------------------
def fig01(data, d, cmap):
    """Uniform fog: first cloud + threshold sweep."""
    splats = np.asarray(d["uniform_fog"])
    xyz, den = splats[:, :3], splats[:, 3]
    fig, top = figure(
        12.6,
        13.1,
        1,
        "the first fog",
        "One bandwidth everywhere: the density field as Monte-Carlo splats",
        f"{len(splats)} splats  ·  uniform h = {d['h']:.3f}  ·  threshold sweep left-to-right, top-to-bottom",
    )
    panels = [
        (0.0, "full fog"),
        (0.25, "level 0.25 — haze burns off"),
        (0.5, "level 0.5 — cores nucleate"),
        (0.15, "level 0.15 — the working view"),
    ]
    for k, (level, title) in enumerate(panels):
        ax = fig.add_subplot(2, 2, k + 1, projection="3d")
        mask = den >= level
        fog_scatter(ax, xyz[mask], den[mask], cmap)
        fit3d(ax, xyz)
        panel_title(ax, f"{title}  ·  {int(mask.sum())} splats")
    fig.subplots_adjust(
        left=MARGIN, right=1 - MARGIN, top=top, bottom=MARGIN, wspace=0.05, hspace=0.16
    )
    save(fig, "01-uniform-fog-panels.png")


def fig02(data, d, cmap):
    """Uniform vs adaptive bandwidth."""
    from ytk import ridges

    uni = np.asarray(d["uniform_fog"])
    ada = np.asarray(data["all"]["fog"]["splats"])
    z3 = np.array([p["z3"] for p in data["points"]])
    hi = ridges.knn_bandwidths(z3)
    fig, top = figure(
        15,
        9.1,
        2,
        "the bandwidth dial",
        "One width for every note, or a width per note?",
        f"uniform h = {d['h']:.3f}  ·  adaptive h_i in [{hi.min():.3f}, {hi.max():.3f}], "
        f"median {np.median(hi):.3f}  ·  kNN-scaled, median-anchored, clamped",
    )
    for k, (arr, title) in enumerate(
        [
            (uni, "uniform bandwidth — one width everywhere; cores smear into their surroundings"),
            (
                ada,
                "adaptive bandwidth — kNN-scaled per note; crowded regions sharpen, lonely notes haze",
            ),
        ]
    ):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        fog_scatter(ax, arr[:, :3], arr[:, 3], cmap)
        fit3d(ax, arr[:, :3])
        panel_title(ax, f"{title}  ·  {len(arr)} splats", width=86)
    fig.subplots_adjust(left=MARGIN, right=1 - MARGIN, top=top, bottom=MARGIN, wspace=0.06)
    save(fig, "02-uniform-vs-adaptive.png")


def fig03(data, d, cmap):
    """Adaptive fog, final normalization."""
    splats = np.asarray(data["all"]["fog"]["splats"])
    xyz, den = splats[:, :3], splats[:, 3]
    fils = data["all"]["web"]["filaments"]
    fig, top = figure(
        12.6,
        13.1,
        3,
        "adaptive fog, corrected",
        "The same cloud once the display normalization stops lying",
        f"{len(splats)} splats  ·  median density {np.median(den):.2f}  ·  scaled to the splats' "
        f"own 99th percentile, not the peak at the data points",
    )
    for k, (level, title) in enumerate(
        [(0.0, "full fog"), (0.25, "level 0.25 — haze gone"), (0.5, "level 0.5 — cores nucleate")]
    ):
        ax = fig.add_subplot(2, 2, k + 1, projection="3d")
        mask = den >= level
        fog_scatter(ax, xyz[mask], den[mask], cmap)
        fit3d(ax, xyz)
        panel_title(ax, f"{title}  ·  {int(mask.sum())} splats")
    ax = fig.add_subplot(2, 2, 4, projection="3d")
    mask = den >= 0.15
    fog_scatter(ax, xyz[mask], den[mask], cmap, alpha=0.26)
    strand_plot(ax, fils)
    fit3d(ax, xyz)
    panel_title(ax, f"fog + filament web  ·  {len(fils)} strands")
    fig.subplots_adjust(
        left=MARGIN, right=1 - MARGIN, top=top, bottom=MARGIN, wspace=0.05, hspace=0.16
    )
    save(fig, "03-adaptive-fog-panels.png")


def fig04(data, d, cmap):
    """The scale-space verdict."""
    splats = np.asarray(data["all"]["fog"]["splats"])
    keep = splats[:, 3] >= 0.12
    uni = data["all"]["web"]["filaments"]
    ada = d["adaptive_strands"]
    fig, top = figure(
        15,
        9.1,
        4,
        "the scale-space verdict",
        "Sharper is not better: adaptive bandwidth shatters the strands",
        "the estimator must match the question — fog asks a local question, "
        "the web asks a connectivity question",
    )
    for k, (fils, title) in enumerate(
        [
            (uni, "uniform h — connectivity survives; long spines hold together"),
            (ada, "adaptive h_i — sharper local density, fragmented crests"),
        ]
    ):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        fog_scatter(ax, splats[keep, :3], splats[keep, 3], cmap, alpha=0.16)
        strand_plot(ax, fils)
        fit3d(ax, splats[:, :3])
        lens = sorted(len(f) for f in fils)
        panel_title(
            ax,
            f"{title}  ·  {len(fils)} strands, longest {lens[-1]}, median {lens[len(lens) // 2]}",
            width=86,
        )
    fig.subplots_adjust(left=MARGIN, right=1 - MARGIN, top=top, bottom=MARGIN, wspace=0.06)
    save(fig, "04-filaments-uniform-vs-adaptive.png")


def fig05(data, d, cmap):
    """Chaining vs tracing."""
    splats = np.asarray(data["all"]["fog"]["splats"])
    keep = splats[:, 3] >= 0.12
    fig, top = figure(
        15,
        9.1,
        5,
        "dashes into strands",
        "Connect-the-dots versus walking the wire",
        "nearest-neighbour chaining breaks at every gap between converged walkers; "
        "predictor-corrector tracing returns one ordered, evenly spaced strand",
    )
    for k, (fils, title, taper) in enumerate(
        [
            (d["chained"], "chained walkers — gaps render as dashes", False),
            (
                data["all"]["web"]["filaments"],
                "traced strands — ordered, uniformly spaced, density-tapered",
                True,
            ),
        ]
    ):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        fog_scatter(ax, splats[keep, :3], splats[keep, 3], cmap, alpha=0.14)
        strand_plot(ax, fils, taper=taper)
        fit3d(ax, splats[:, :3])
        lens = sorted(len(f) for f in fils)
        panel_title(
            ax,
            f"{title}  ·  {len(fils)} filaments, longest {lens[-1]}, median {lens[len(lens) // 2]}",
            width=86,
        )
    fig.subplots_adjust(left=MARGIN, right=1 - MARGIN, top=top, bottom=MARGIN, wspace=0.06)
    save(fig, "05-chained-vs-traced-filaments.png")


def fig06(data, d, cmap):
    """Note-to-strand distance."""
    z3 = np.array([p["z3"] for p in data["points"]])
    doms = np.array([p["dom"] for p in data["points"]])
    labels = [g["label"] for g in data["all"]["domains"]]
    verts = np.vstack([np.asarray(f)[:, :3] for f in data["all"]["web"]["filaments"]])
    h = data["all"]["web"]["h"]
    dist = np.sqrt(((z3[:, None, :] - verts[None, :, :]) ** 2).sum(-1).min(1)) / h

    fig, top = figure(
        16.5,
        7.4,
        6,
        "distance to the skeleton",
        "How well does a handful of strands stand in for the whole cloud?",
        f"{len(z3)} notes  ·  {len(verts)} strand vertices  ·  h = {h:.3f}  ·  "
        f"the same measure astronomy uses for galaxy distance-to-filament",
    )
    # The domain names are long; the right panel needs a wide left gutter and
    # the 3D panel's colourbar goes underneath it rather than beside it,
    # where it used to collide with those labels.
    gs = fig.add_gridspec(
        1,
        3,
        width_ratios=[1.0, 1.18, 1.02],
        left=0.058,
        right=1 - MARGIN - 0.018,
        top=top,
        bottom=0.215,
        wspace=0.42,
    )

    ax = fig.add_subplot(gs[0])
    ax.hist(dist, bins=60, color=GOLD, alpha=0.92)
    ax.axvline(float(np.median(dist)), color=CYAN, linewidth=1.3, linestyle="--")
    style_axes(ax)
    ax.set_xlabel("distance / h")
    ax.set_ylabel("notes")
    panel_title(
        ax,
        f"median {np.median(dist):.2f}h — {100 * (dist < 2).mean():.0f}% of notes "
        f"lie within 2h of a strand",
        width=86,
    )

    ax = fig.add_subplot(gs[1], projection="3d")
    sc = ax.scatter(
        z3[:, 0],
        z3[:, 1],
        z3[:, 2],
        c=np.clip(dist, 0, 3),
        cmap=cmap,
        s=6,
        alpha=0.62,
        linewidths=0,
    )
    for fil in data["all"]["web"]["filaments"]:
        f = np.asarray(fil)
        ax.plot(f[:, 0], f[:, 1], f[:, 2], color=CYAN, linewidth=1.1, alpha=0.85)
    fit3d(ax, z3, zoom=1.62)
    panel_title(ax, "notes coloured by strand distance — bright = frontier", width=86)
    box = ax.get_position()
    cax = fig.add_axes([box.x0 + 0.045, 0.105, box.width - 0.09, 0.020])
    cb = fig.colorbar(sc, cax=cax, orientation="horizontal")
    cb.set_label("distance / h (capped at 3)", color=MUTED, fontsize=TICK_SIZE)
    cb.ax.tick_params(colors=MUTED, labelsize=TICK_SIZE - 1)
    cb.outline.set_edgecolor(FRAME)
    cb.ax._is_colorbar = True

    ax = fig.add_subplot(gs[2])
    rows = [
        (labels[k], float(np.median(dist[doms == k])), int((doms == k).sum()))
        for k in range(len(labels))
        if (doms == k).sum() > 20
    ]
    rows.sort(key=lambda r: r[1])
    ax.barh([f"{n} ({c})" for n, _, c in rows], [v for _, v, _ in rows], color=GOLD, alpha=0.92)
    style_axes(ax)
    ax.set_xlim(
        0, max(v for _, v, _ in rows) * 1.12
    )  # headroom so the longest bar clears the frame
    ax.set_xlabel("median distance / h")
    panel_title(ax, "by domain — low = hugs its highway, high = sprawls", width=86)

    save(fig, "06-strand-distance.png")


def fig07(data, d, cmap):
    """Trim forensics."""
    splats = np.asarray(data["all"]["fog"]["splats"])
    keep = splats[:, 3] >= 0.15
    fig, top = figure(
        15,
        9.1,
        7,
        "trim forensics",
        "Did trimming lose any threads, or only duplicate ink?",
        "same crest points and the same coverage on both sides — the trim removes stretches "
        "already drawn by a longer strand, then reattaches branches at their junction",
    )
    for k, (fils, title) in enumerate(
        [
            (
                d["pretrim"],
                "pre-trim — every seed's full walk, strands redrawn on top of each other",
            ),
            (
                data["all"]["web"]["filaments"],
                "trimmed — covered stretches removed, branches reattached",
            ),
        ]
    ):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        fog_scatter(ax, splats[keep, :3], splats[keep, 3], cmap, alpha=0.10)
        strand_plot(ax, fils, taper=False)
        fit3d(ax, splats[:, :3])
        verts = sum(len(f) for f in fils)
        panel_title(ax, f"{title}  ·  {len(fils)} strands, {verts} vertices", width=86)
    fig.subplots_adjust(left=MARGIN, right=1 - MARGIN, top=top, bottom=MARGIN, wspace=0.06)
    save(fig, "07-trim-forensics.png")


def fig08(data, d, cmap):
    """Junctions."""
    splats = np.asarray(data["all"]["fog"]["splats"])
    keep = splats[:, 3] >= 0.12
    fils = data["all"]["web"]["filaments"]
    junc = np.asarray(data["all"]["web"].get("junctions", []), float)
    # Landscape frame: the embedding is far wider than it is tall, so a
    # near-square canvas leaves bands of dead space above and below.
    fig, top = figure(
        11.5,
        11.0,
        8,
        "the crossroads",
        "Where one strand's endpoint lands on another's trunk",
        f"{len(junc)} junctions across {len(fils)} strands  ·  candidate anchors for the "
        f"planets of issue #78",
    )
    ax = fig.add_subplot(1, 1, 1, projection="3d")
    fog_scatter(ax, splats[keep, :3], splats[keep, 3], cmap, alpha=0.20)
    strand_plot(ax, fils)
    if len(junc):
        ax.scatter(
            junc[:, 0],
            junc[:, 1],
            junc[:, 2],
            s=240,
            facecolors="none",
            edgecolors=CYAN,
            linewidths=1.8,
            alpha=0.95,
            zorder=6,
        )
        ax.scatter(junc[:, 0], junc[:, 1], junc[:, 2], s=30, color="#fff6e0", alpha=1.0, zorder=7)
    fit3d(ax, splats[:, :3], zoom=1.6)
    fig.subplots_adjust(left=MARGIN, right=1 - MARGIN, top=top, bottom=MARGIN)
    save(fig, "08-junctions.png")


def fig09(data, d, cmap):
    """Shell bands."""
    splats = np.asarray(data["all"]["fog"]["splats"])
    xyz, den = splats[:, :3], splats[:, 3]
    eps, level = 0.06, 0.35
    fig, top = figure(
        12.6,
        13.1,
        9,
        "shells and onions",
        "Swap the slider's >= for an absolute value and the fog goes hollow",
        f"|f - c| < {0.06} is the Monte-Carlo preview of a marching-cubes isosurface  ·  "
        f"band thickness ~ 2eps / |grad f|, so shells hug steep peaks and puff over saddles",
    )

    ax = fig.add_subplot(2, 2, 1, projection="3d")
    mask = den >= level
    fog_scatter(ax, xyz[mask], den[mask], cmap)
    fit3d(ax, xyz)
    panel_title(ax, f"fill: density >= {level}  ·  {int(mask.sum())} splats")

    ax = fig.add_subplot(2, 2, 2, projection="3d")
    mask = np.abs(den - level) < eps
    fog_scatter(ax, xyz[mask], den[mask], cmap, alpha=0.55)
    fit3d(ax, xyz)
    panel_title(ax, f"shell: |density - {level}| < {eps}  ·  {int(mask.sum())} splats — hollow")

    ax = fig.add_subplot(2, 2, 3, projection="3d")
    for lvl, color in [(0.15, BLUE), (0.35, GOLD), (0.6, RED)]:
        m = np.abs(den - lvl) < eps
        ax.scatter(
            xyz[m, 0],
            xyz[m, 1],
            xyz[m, 2],
            color=color,
            s=7,
            alpha=0.34,
            linewidths=0,
            label=f"level {lvl}",
        )
    fit3d(ax, xyz)
    panel_title(ax, "nested shells — the onion")
    leg = ax.legend(loc="upper left", fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT)
    leg.set_zorder(20)

    ax = fig.add_subplot(2, 2, 4)
    slab = np.abs(xyz[:, 2]) < 0.12
    ring = slab & (np.abs(den - level) < eps)
    core = slab & (den >= level + eps)
    ax.scatter(xyz[slab, 0], xyz[slab, 1], color=DIM, s=4, alpha=0.35, linewidths=0)
    ax.scatter(
        xyz[core, 0], xyz[core, 1], color=PURPLE, s=7, alpha=0.6, linewidths=0, label="interior"
    )
    ax.scatter(
        xyz[ring, 0], xyz[ring, 1], color=GOLD, s=10, alpha=0.85, linewidths=0, label="shell band"
    )
    ax.set_aspect("equal")
    style_axes(ax)
    ax.set_xticks([])
    ax.set_yticks([])
    panel_title(ax, "cross-section |z| < 0.12 — shells ring the cores")
    ax.legend(loc="upper left", fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT)

    fig.subplots_adjust(
        left=MARGIN, right=1 - MARGIN, top=top, bottom=MARGIN, wspace=0.07, hspace=0.16
    )
    save(fig, "09-shell-band.png")


FIGS = {1: fig01, 2: fig02, 3: fig03, 4: fig04, 5: fig05, 6: fig06, 7: fig07, 8: fig08, 9: fig09}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, choices=sorted(FIGS), default=None)
    ap.add_argument("--refresh", action="store_true", help="recompute cached geometry")
    args = ap.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    cmap = saturated_magma()
    data = load()
    d = derived(data, refresh=args.refresh)
    for k in [args.only] if args.only else sorted(FIGS):
        FIGS[k](data, d, cmap)


if __name__ == "__main__":
    main()
