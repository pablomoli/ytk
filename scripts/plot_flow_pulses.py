"""Preview the flow pulses before writing the shader (feature A, epic #107).

The pulse is one line of arithmetic:

    brightness = BASE + AMP * sin(arclen * FREQ - time * SPEED)

`arclen` is how far along its own strand a vertex sits, measured by walking
the strand rather than straight across. This script computes exactly that
from the real filament payload and paints it with matplotlib, so FREQ and
SPEED can be chosen by eye on the real geometry instead of by guessing in
GLSL and rebuilding to look.

The brief proposes FREQ 38, SPEED 2.2. Whether those are right is a question
about wavelength against strand length, which is measurable — see rung 01.

Usage: uv run --with matplotlib --with numpy python scripts/plot_flow_pulses.py
Figures land in docs/assets/flow-pulses/.
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
    RED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    saturated_magma,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "flow-pulses"
MAP = Path.home() / ".ytk" / "map.json"

BASE, AMP = 0.78, 0.22  # from the handoff brief
FREQ, SPEED = 38.0, 2.2  # rad per layout unit, rad per second


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
    """Filaments as (xyz, arclen, density) — arclen measured along the strand.

    This is the one new quantity the shader needs, and it is why the tracer
    mattered: predictor-corrector strands are ordered and near-uniformly
    spaced, so a running sum of segment lengths is a trustworthy ruler.
    """
    data = json.loads(MAP.read_text())
    out = []
    for fil in data["all"]["web"]["filaments"]:
        f = np.asarray(fil, float)
        xyz = f[:, :3]
        den = f[:, 4] if f.shape[1] > 4 else np.ones(len(f))
        step = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
        alen = np.concatenate([[0.0], np.cumsum(step)])
        out.append((xyz, alen, den))
    return out


def brightness(alen, t, freq=FREQ, speed=SPEED):
    return BASE + AMP * np.sin(alen * freq - t * speed)


def draw_strand(ax, xyz, alen, den, t, cmap, freq=FREQ, speed=SPEED, lw=2.4):
    """One strand as coloured segments, brightness following the travelling wave."""
    b = brightness(alen, t, freq, speed)
    seg_b = 0.5 * (b[:-1] + b[1:])
    seg_d = 0.5 * (den[:-1] + den[1:])
    for i in range(len(xyz) - 1):
        ax.plot(
            xyz[i : i + 2, 0],
            xyz[i : i + 2, 1],
            color=cmap(np.clip(seg_b[i], 0, 1)),
            lw=lw * (0.45 + 0.55 * min(seg_d[i] * 1.6, 1.0)),
            solid_capstyle="round",
        )


def fig01_wavelength(strands):
    """Is FREQ 38 sensible? A wavelength question, answered against real lengths."""
    lengths = np.array([a[-1] for _, a, _ in strands])
    wl = 2 * np.pi / FREQ
    cycles = lengths / wl

    fig, top = figure(
        13.0,
        6.2,
        1,
        "choosing the wavelength",
        "How many pulses fit on a strand at the proposed frequency?",
        f"FREQ {FREQ:g} rad/unit  ->  wavelength {wl:.3f} layout units  ·  "
        f"{len(strands)} strands, {lengths.min():.2f}-{lengths.max():.2f} units long",
    )
    gs = fig.add_gridspec(
        1, 2, width_ratios=[1.0, 1.0], left=0.07, right=1 - MARGIN - 0.02, top=top, bottom=0.145
    )

    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    panel_title(ax, "strand length, in layout units")
    order = np.argsort(lengths)
    ax.barh(np.arange(len(lengths)), lengths[order], color=GOLD, height=0.72)
    ax.axvline(wl, color=RED, ls="--", lw=1.6, label=f"one wavelength ({wl:.3f})")
    ax.set_yticks([])
    ax.set_xlabel("arc length / layout units")
    legend(ax, loc="lower right")

    ax = fig.add_subplot(gs[1])
    style_axes(ax)
    panel_title(ax, "pulses visible on each strand at once")
    ax.barh(np.arange(len(cycles)), cycles[order], color=GOLD, height=0.72)
    ax.axvline(1, color=DIM, ls=":", lw=1.4)
    ax.axvline(
        np.median(cycles), color=RED, ls="--", lw=1.6, label=f"median {np.median(cycles):.1f}"
    )
    ax.set_yticks([])
    ax.set_xlabel("wavelengths per strand")
    legend(ax, loc="lower right")
    save(fig, "01-wavelength-choice.png")
    return lengths, cycles


def fig02_still(strands):
    """The pulse on a still frame — four instants of the same geometry."""
    cmap = saturated_magma()
    times = [0.0, 0.30, 0.60, 0.90]

    fig, top = figure(
        16.0,
        5.6,
        2,
        "the pulse on a still frame",
        "Four instants of the same web, 0.3s apart",
        f"brightness = {BASE:g} + {AMP:g}·sin(arclen·{FREQ:g} − time·{SPEED:g})  ·  "
        f"the geometry never moves; only the brightness travels",
    )
    gs = fig.add_gridspec(
        1, 4, left=0.02, right=1 - MARGIN - 0.01, top=top, bottom=0.06, wspace=0.06
    )
    for k, t in enumerate(times):
        ax = fig.add_subplot(gs[k])
        style_axes(ax)
        ax.set_facecolor("#000000")
        panel_title(ax, f"t = {t:.2f}s")
        for xyz, alen, den in strands:
            draw_strand(ax, xyz, alen, den, t, cmap)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    save(fig, "02-pulse-still.png")


def fig03_speed(strands):
    """Speed and frequency are separate dials. Show what each one does."""
    cmap = saturated_magma()
    longest = max(strands, key=lambda s: s[1][-1])

    fig, top = figure(
        15.0,
        6.6,
        3,
        "the two dials",
        "Frequency sets how close the pulses are; speed sets how fast they run",
        "the longest strand — the epicmap spine — at one instant, under three "
        "frequencies and three speeds",
    )
    gs = fig.add_gridspec(
        2, 3, left=0.045, right=1 - MARGIN - 0.02, top=top, bottom=0.075, hspace=0.32, wspace=0.08
    )
    xyz, alen, den = longest
    for i, f in enumerate([18.0, 38.0, 76.0]):
        ax = fig.add_subplot(gs[0, i])
        style_axes(ax)
        ax.set_facecolor("#000000")
        panel_title(ax, f"FREQ {f:g}" + ("  (proposed)" if f == FREQ else ""))
        draw_strand(ax, xyz, alen, den, 0.0, cmap, freq=f, lw=3.0)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    # Speed cannot be seen in a still, so show the phase it reaches after a
    # fixed 0.5s — a faster dial has simply travelled further by then.
    for i, s in enumerate([1.1, 2.2, 4.4]):
        ax = fig.add_subplot(gs[1, i])
        style_axes(ax)
        ax.set_facecolor("#000000")
        panel_title(ax, f"SPEED {s:g} after 0.5s" + ("  (proposed)" if s == SPEED else ""))
        draw_strand(ax, xyz, alen, den, 0.5, cmap, speed=s, lw=3.0)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    save(fig, "03-two-dials.png")


def main():
    strands = load_strands()
    lengths, cycles = fig01_wavelength(strands)
    fig02_still(strands)
    fig03_speed(strands)
    print()
    print(f"  strands            {len(strands)}")
    print(
        f"  arc length         {lengths.min():.3f}-{lengths.max():.3f} (median {np.median(lengths):.3f})"
    )
    print(f"  wavelength @ {FREQ:g}   {2 * np.pi / FREQ:.4f}")
    print(
        f"  pulses per strand  {cycles.min():.1f}-{cycles.max():.1f} (median {np.median(cycles):.1f})"
    )
    print(f"  pulse travels      {SPEED / FREQ:.4f} units/s")


if __name__ == "__main__":
    main()
