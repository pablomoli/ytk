"""Preview the flow pulses before writing the shader (feature A, epic #107).

The pulse is one line of arithmetic:

    brightness = BASE + AMP * sin(arclen * FREQ - time * SPEED)

`arclen` is how far along its own strand a vertex sits, measured by walking
the strand rather than straight across. Computed here exactly as the buffer
build will compute it, so preview and shader cannot disagree about the ruler.

Rungs:
  01  wavelength — how many pulses fit on each strand, and how long one takes
  02  still frame — four instants of the same web, geometry fixed
  03  the two dials — frequency and speed varied independently
  04  shortlist — the settings worth choosing between, side by side

Usage: uv run --with matplotlib --with numpy python scripts/plot_flow_pulses.py
Figures land in docs/assets/flow-pulses/.
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import BG as FIG_BG
from plot_assets import (
    DIM,
    DPI,
    GOLD,
    MARGIN,
    RED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "flow-pulses"
MAP = Path.home() / ".ytk" / "map.json"

BASE, AMP = 0.78, 0.22  # the shader's actual brightness envelope
FREQ, SPEED = 18.0, 4.5  # recommended; see fig04 for how these were chosen

# The settings worth choosing between. Speed is held near 0.25 layout units/s
# across all three, so what you are judging between them is pulse *density*
# rather than pace — a pulse crosses a typical strand in about 3s in each.
CANDIDATES = [
    ("calm", 12.0, 3.0),
    ("recommended", 18.0, 4.5),
    ("energetic", 26.0, 6.5),
]


def neon():
    """magma with the top end pushed to white-hot.

    The shader's brightness only swings between 0.56 and 1.0, and plain magma
    spends that whole span in orange — the travelling wave is real but nearly
    invisible. Ending the ramp in white makes a crest read as light rather
    than as a slightly different orange.
    """
    base = plt.get_cmap("magma")(np.linspace(0, 1, 256))
    hsv = mcolors.rgb_to_hsv(base[:, :3])
    hsv[:, 1] = np.clip(hsv[:, 1] * 1.45, 0, 1)
    hsv[:, 2] = np.clip(hsv[:, 2] * 1.10, 0, 1)
    base[:, :3] = mcolors.hsv_to_rgb(hsv)
    tail = np.linspace(0, 1, 32)[:, None]
    base[224:, :3] = base[224:, :3] * (1 - tail) + np.array([1.0, 0.97, 0.90]) * tail
    return mcolors.ListedColormap(base, name="magma_neon")


def save(fig, name: str) -> None:
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=FIG_BG)
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def legend(ax, **kw):
    return ax.legend(fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT, **kw)


def load_strands():
    """Filaments as (xyz, arclen, density), arclen measured along the strand."""
    data = json.loads(MAP.read_text())
    out = []
    for fil in data["all"]["web"]["filaments"]:
        f = np.asarray(fil, float)
        xyz = f[:, :3]
        den = f[:, 4] if f.shape[1] > 4 else np.ones(len(f))
        step = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
        out.append((xyz, np.concatenate([[0.0], np.cumsum(step)]), den))
    return out


def draw_strand(ax, xyz, alen, den, t, cmap, freq=FREQ, speed=SPEED, lw=2.6):
    """One strand, with bloom.

    Real bloom is a render-to-texture blur — that is feature C. Here it is
    faked the cheap way, the same polyline drawn several times widest and
    faintest first, which is enough to show what a crest will feel like once
    C lands. Glow follows brightness, so troughs stay tight and only crests
    bleed light.
    """
    b = BASE + AMP * np.sin(alen * freq - t * speed)
    # The shader swings 0.56..1.0; stretching that across the full ramp is the
    # same signal in wider paint, and it is the difference between seeing the
    # wave and taking its existence on trust.
    shade = (b - (BASE - AMP)) / (2 * AMP)
    seg_s = 0.5 * (shade[:-1] + shade[1:])
    seg_d = 0.5 * (den[:-1] + den[1:])
    taper = 0.45 + 0.55 * np.minimum(seg_d * 1.6, 1.0)

    for width_mul, alpha_mul in ((5.5, 0.05), (3.2, 0.10), (1.9, 0.22)):
        for i in range(len(xyz) - 1):
            g = seg_s[i] ** 2.2  # only crests bloom
            if g < 0.06:
                continue
            ax.plot(
                xyz[i : i + 2, 0],
                xyz[i : i + 2, 1],
                color=cmap(float(np.clip(seg_s[i], 0, 1))),
                lw=lw * taper[i] * width_mul,
                alpha=alpha_mul * g,
                solid_capstyle="round",
                zorder=2,
            )
    for i in range(len(xyz) - 1):
        ax.plot(
            xyz[i : i + 2, 0],
            xyz[i : i + 2, 1],
            color=cmap(float(np.clip(seg_s[i], 0, 1))),
            lw=lw * taper[i],
            solid_capstyle="round",
            zorder=3,
        )


def dark_panel(ax, title):
    style_axes(ax)
    ax.set_facecolor("#000000")
    panel_title(ax, title, width=52)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def fig01(strands):
    """Wavelength and traversal time — the two questions the dials answer."""
    lengths = np.array([a[-1] for _, a, _ in strands])
    wl = 2 * np.pi / FREQ
    cycles = lengths / wl
    v = SPEED / FREQ

    fig, top = figure(
        13.5,
        6.4,
        1,
        "choosing the dials",
        "How many pulses fit on a strand, and how long does one take to cross?",
        f"FREQ {FREQ:g} -> wavelength {wl:.3f} units  ·  SPEED {SPEED:g} -> {v:.3f} units/s  ·  "
        f"{len(strands)} strands, {lengths.min():.2f}-{lengths.max():.2f} units",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1.0, 1.0], left=0.075, right=1 - MARGIN - 0.02, top=top, bottom=0.15
    )
    order = np.argsort(lengths)

    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "pulses visible on each strand at once")
    ax.barh(np.arange(len(cycles)), cycles[order], color=GOLD, height=0.72)
    ax.axvline(
        float(np.median(cycles)),
        color=RED,
        ls="--",
        lw=1.6,
        label=f"median {np.median(cycles):.1f}",
    )
    ax.set_yticks([])
    ax.set_xlabel("wavelengths per strand")
    legend(ax, loc="lower right")

    ax = fig.add_subplot(gs[1])
    style_axes(ax)
    panel_title(ax, "seconds for one pulse to cross the strand")
    ax.barh(np.arange(len(lengths)), lengths[order] / v, color=GOLD, height=0.72)
    ax.axvline(3.0, color=DIM, ls=":", lw=1.4)
    ax.axvline(
        float(np.median(lengths) / v),
        color=RED,
        ls="--",
        lw=1.6,
        label=f"median {np.median(lengths) / v:.1f}s",
    )
    ax.set_yticks([])
    ax.set_xlabel("seconds end to end")
    legend(ax, loc="lower right")
    save(fig, "01-wavelength-choice.png")
    return lengths, cycles


def fig02(strands):
    """The pulse on a still frame — four instants of identical geometry."""
    cmap = neon()
    fig, top = figure(
        16.0,
        6.4,
        2,
        "the pulse on a still frame",
        "Four instants of the same web, 0.25s apart",
        f"brightness = {BASE:g} + {AMP:g}·sin(arclen·{FREQ:g} − time·{SPEED:g})  ·  "
        f"the geometry never moves; only the light travels",
    )
    gs = fig.add_gridspec(
        1, 4, left=0.015, right=1 - MARGIN - 0.005, top=top, bottom=0.03, wspace=0.04
    )
    for k, t in enumerate([0.0, 0.25, 0.50, 0.75]):
        ax = fig.add_subplot(gs[k])
        dark_panel(ax, f"t = {t:.2f}s")
        for xyz, alen, den in strands:
            draw_strand(ax, xyz, alen, den, t, cmap)
    save(fig, "02-pulse-still.png")


def fig03(strands):
    """Frequency and speed are separate dials."""
    cmap = neon()
    xyz, alen, den = max(strands, key=lambda s: s[1][-1])

    fig, top = figure(
        15.0,
        7.0,
        3,
        "the two dials",
        "Frequency sets how close the pulses are; speed sets how fast they run",
        "the epicmap spine — the longest strand, 4.76 units — under three of each",
    )
    gs = fig.add_gridspec(
        2, 3, left=0.03, right=1 - MARGIN - 0.01, top=top, bottom=0.04, hspace=0.30, wspace=0.05
    )
    for i, f in enumerate([12.0, 18.0, 26.0]):
        ax = fig.add_subplot(gs[0, i])
        dark_panel(ax, f"FREQ {f:g}" + ("  (recommended)" if f == FREQ else ""))
        draw_strand(ax, xyz, alen, den, 0.0, cmap, freq=f, lw=3.2)
    # Speed cannot be seen in a still, so show how far each has carried its
    # crests by the same moment.
    for i, s in enumerate([2.0, 4.5, 8.0]):
        ax = fig.add_subplot(gs[1, i])
        dark_panel(ax, f"SPEED {s:g}, at t = 0.5s" + ("  (recommended)" if s == SPEED else ""))
        draw_strand(ax, xyz, alen, den, 0.5, cmap, speed=s, lw=3.2)
    save(fig, "03-two-dials.png")


def fig04(strands):
    """The three settings worth choosing between, on the whole web."""
    cmap = neon()
    lengths = np.array([a[-1] for _, a, _ in strands])
    med = float(np.median(lengths))

    fig, top = figure(
        15.0,
        6.8,
        4,
        "the shortlist",
        "Three settings, same web, same instant — pick one",
        "speed is held near 0.25 units/s in all three, so what differs between "
        "them is pulse density, not pace",
    )
    gs = fig.add_gridspec(
        1, 3, left=0.02, right=1 - MARGIN - 0.005, top=top, bottom=0.04, wspace=0.04
    )
    for i, (name, f, s) in enumerate(CANDIDATES):
        v = s / f
        ax = fig.add_subplot(gs[i])
        dark_panel(
            ax,
            f"{name} — FREQ {f:g}, SPEED {s:g}   ·   "
            f"{med / (2 * np.pi / f):.1f} pulses on a typical strand, "
            f"{med / v:.1f}s to cross it",
        )
        for xyz, alen, den in strands:
            draw_strand(ax, xyz, alen, den, 0.0, cmap, freq=f, speed=s)
    save(fig, "04-shortlist.png")


def main():
    strands = load_strands()
    lengths, cycles = fig01(strands)
    fig02(strands)
    fig03(strands)
    fig04(strands)
    v = SPEED / FREQ
    print()
    print(f"  strands            {len(strands)}")
    print(
        f"  arc length         {lengths.min():.2f}-{lengths.max():.2f} "
        f"(median {np.median(lengths):.2f})"
    )
    print(f"  wavelength @ {FREQ:g}   {2 * np.pi / FREQ:.3f}")
    print(
        f"  pulses per strand  {cycles.min():.1f}-{cycles.max():.1f} (median {np.median(cycles):.1f})"
    )
    print(f"  pulse speed        {v:.3f} units/s")
    print(
        f"  crossing time      median {np.median(lengths) / v:.1f}s, spine {lengths.max() / v:.1f}s"
    )


if __name__ == "__main__":
    main()
