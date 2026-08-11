"""Checkpoint: the three coast rules on the globe — orthographic hemisphere
views computed per-pixel (no 3D mesh, so the coast stays a smooth line)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e30_coastlines as e30
from e30b_organic_coast import level_for_area, softmin_field, value_noise
from plot_assets import (
    BG,
    CYAN,
    DPI,
    PANEL,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
    verdict,
)

OUT = e30.ASSETS
RES = 1000  # pixels across each globe


def ortho_sample(field, view_lon, view_lat):
    """Sample a lon/lat field over the visible hemisphere of an orthographic
    view centred on (view_lon, view_lat). Returns image + mask + view depth."""
    y, x = np.mgrid[-1 : 1 : RES * 1j, -1 : 1 : RES * 1j]
    r2 = x * x + y * y
    mask = r2 <= 1.0
    z = np.sqrt(np.clip(1.0 - r2, 0, 1))
    # camera basis: e_z toward viewer, e_x east, e_y north
    cl, sl = np.cos(view_lat), np.sin(view_lat)
    co, so = np.cos(view_lon), np.sin(view_lon)
    ez = np.array([cl * co, cl * so, sl])
    ex = np.array([-so, co, 0.0])
    ey = np.cross(ez, ex)
    p = x[..., None] * ex + y[..., None] * ey + z[..., None] * ez
    lon = np.arctan2(p[..., 1], p[..., 0])
    lat = np.arcsin(np.clip(p[..., 2], -1, 1))
    i = np.clip(
        ((lat + np.pi / 2) / np.pi * (field.shape[0] - 1)).astype(int), 0, field.shape[0] - 1
    )
    j = np.clip(
        ((lon + np.pi) / (2 * np.pi) * (field.shape[1] - 1)).astype(int), 0, field.shape[1] - 1
    )
    return field[i, j], mask, z


def main():
    d = e30.load()
    r_deg = e30.ocean_radius(d["lattice"])
    ll, tt, xyz = e30.grid()
    hard, _ = e30.fields(xyz, d["pos"], np.zeros(len(d["pos"]), dtype=int))
    target = float((np.cos(tt) * (hard < r_deg)).sum() / np.cos(tt).sum())
    beta = 3.0 / r_deg
    soft = softmin_field(xyz, d["pos"], beta)
    warp = soft + value_noise(xyz, seed=30) * (0.55 * r_deg)

    panels = [
        ("A — hard min (shipped)", hard, r_deg),
        ("B — softmin metaballs", soft, level_for_area(soft, tt, target)),
        ("C — softmin + seeded warp", warp, level_for_area(warp, tt, target)),
    ]

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    cmap = saturated_magma()
    view_lon, view_lat = np.radians(-35), np.radians(12)
    fig, top = figure(
        16.4,
        6.8,
        5,
        "E30b · organic coastlines",
        "The three coast rules on the globe, one camera",
        meta=(
            f"n={d['pos'].shape[0]} · land {target:.0%} under every rule · orthographic "
            f"hemisphere, per-pixel sampling at {RES}px · limb-shaded · seed 30"
        ),
    )
    gs = fig.add_gridspec(1, 3, left=0.025, right=0.975, top=top, bottom=0.05, wspace=0.04)
    for i, (title, field, level) in enumerate(panels):
        img, mask, z = ortho_sample(field, view_lon, view_lat)
        near = punch(np.clip(1.0 - (img - level + r_deg) / (2.5 * r_deg), 0, 1))
        shade = 0.55 + 0.45 * z  # limb falloff sells the sphere
        rgba = cmap(near)
        rgba[..., :3] *= shade[..., None]
        rgba[~mask] = mcolors.to_rgba(PANEL)
        ax = fig.add_subplot(gs[0, i], facecolor=PANEL)
        ax.imshow(rgba, origin="lower", interpolation="bilinear")
        signed = np.where(mask, img - level, np.nan)
        ax.contour(signed, levels=[0.0], colors=[CYAN], linewidths=1.5, linestyles="solid")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
        panel_title(ax, title, width=30)
    verdict(fig, "the same planet, three shorelines")
    frame_panels(fig)
    out = OUT / "05-globes-three-rules.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
