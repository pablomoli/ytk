"""E30 figure 04 — organic coastlines: hard-min circles vs softmin metaballs
vs seeded domain warp, all at the same land area (E29 calibration preserved).
The circle critique made concrete: which coast temperament should the planet
wear? Nothing here is wired into the shipping pipeline until a rule is chosen.

    uv run --with matplotlib,scipy python scripts/e30b_organic_coast.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e30_coastlines as e30
from plot_assets import (
    BG,
    CYAN,
    DPI,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
    verdict,
)

OUT = e30.ASSETS


def softmin_field(xyz, pos, beta):
    """-1/beta * log(sum exp(-beta*d_i)): the metaball union of all notes.
    beta -> inf recovers the hard min (circles)."""
    flat = xyz.reshape(-1, 3)
    acc = np.zeros(len(flat))
    for i in range(0, len(flat), 20000):
        d = np.degrees(np.arccos(np.clip(flat[i : i + 20000] @ pos.T, -1.0, 1.0)))
        acc[i : i + 20000] = -np.log(np.exp(-beta * d).sum(axis=1)) / beta
    return acc.reshape(xyz.shape[:2])


def value_noise(xyz, seed, octaves=2, base=6):
    """Smooth seeded 3D value noise sampled on the sphere: random values on a
    coarse lattice, trilinear-interpolated, two octaves."""
    rng = np.random.default_rng(seed)
    out = np.zeros(xyz.shape[:2])
    amp = 1.0
    for o in range(octaves):
        n = base * (2**o)
        lattice = rng.normal(size=(n + 1, n + 1, n + 1))
        u = (xyz + 1) / 2 * (n - 1e-6)
        i0 = u.astype(int)
        f = u - i0
        f = f * f * (3 - 2 * f)  # smoothstep
        v = np.zeros(xyz.shape[:2])
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (
                        (f[..., 0] if dx else 1 - f[..., 0])
                        * (f[..., 1] if dy else 1 - f[..., 1])
                        * (f[..., 2] if dz else 1 - f[..., 2])
                    )
                    v += w * lattice[i0[..., 0] + dx, i0[..., 1] + dy, i0[..., 2] + dz]
        out += amp * v
        amp *= 0.5
    return out / np.abs(out).max()


def level_for_area(field, tt, target):
    """Contour level such that cos-weighted land area equals target."""
    w = np.cos(tt).ravel()
    f = field.ravel()
    order = np.argsort(f)
    cum = np.cumsum(w[order]) / w.sum()
    return float(f[order][np.searchsorted(cum, target)])


def main():
    d = e30.load()
    r_deg = e30.ocean_radius(d["lattice"])
    ll, tt, xyz = e30.grid()
    hard, _ = e30.fields(xyz, d["pos"], np.zeros(len(d["pos"]), dtype=int))
    target = float((np.cos(tt) * (hard < r_deg)).sum() / np.cos(tt).sum())

    beta = 3.0 / r_deg  # kernel scale tied to the calibrated coast radius
    soft = softmin_field(xyz, d["pos"], beta)
    warp = soft + value_noise(xyz, seed=30) * (0.55 * r_deg)

    panels = [
        ("A — hard min (shipped): every lone note is a circle", hard, r_deg),
        (
            "B — softmin metaballs: neighbours merge, necks round off",
            soft,
            level_for_area(soft, tt, target),
        ),
        (
            "C — softmin + seeded warp: eroded, fractal coasts",
            warp,
            level_for_area(warp, tt, target),
        ),
    ]
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, top = figure(
        16.4,
        5.6,
        4,
        "E30b · organic coastlines",
        "Three coast rules, one land area: from circles to geography",
        meta=(
            f"n={len(d['pos'])} · land pinned at {target:.0%} for all three · "
            f"beta = 3/coast ({beta:.2f}/deg) · warp amplitude 0.55 coast · seed 30"
        ),
    )
    gs = fig.add_gridspec(1, 3, left=0.03, right=0.97, top=top, bottom=0.10, wspace=0.08)
    for i, (title, field, level) in enumerate(panels):
        ax = e30._moll(fig, gs[0, i])
        # ramp anchored at each panel's own coast so brightness means the
        # same thing everywhere: signed distance to this rule's shoreline
        near = punch(np.clip(1.0 - (field - level + r_deg) / (2.5 * r_deg), 0, 1))
        ax.pcolormesh(
            ll, tt, near, cmap=saturated_magma(), vmin=0, vmax=1, shading="auto", rasterized=True
        )
        ax.contour(ll, tt, field, levels=[level], colors=[CYAN], linewidths=1.3, linestyles="solid")
        panel_title(ax, title, width=44)
    verdict(fig, "same land, three temperaments — pick the coast the planet deserves")
    frame_panels(fig)
    out = OUT / "04-three-coast-rules.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
