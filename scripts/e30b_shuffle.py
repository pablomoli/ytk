"""Checkpoint: the shuffle parameter — seeded tangent jitter of the notes
inside the field computation only. Rendered tiles never move; the coastline
rerolls per seed while the clusters stay put. Invariance is measured, not
asserted: land-mask agreement across seeds vs the unjittered baseline."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e30_coastlines as e30
from e30b_fbm import fbm, ortho_sample, richardson_dimension
from e30b_organic_coast import level_for_area, softmin_field
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


def jitter(pos, sigma_rad, seed):
    """Seeded tangent displacement, renormalized: notes wander almost in
    place. Only the coast field sees these; the rendered tiles never move."""
    rng = np.random.default_rng(seed)
    v = rng.normal(size=pos.shape)
    v -= (v * pos).sum(axis=1, keepdims=True) * pos  # project to tangent
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    amp = rng.rayleigh(sigma_rad, size=(len(pos), 1))
    out = pos * np.cos(amp) + v * np.sin(amp)
    return out / np.linalg.norm(out, axis=1, keepdims=True)


def field_e(pos, xyz, beta, r_deg, warp_seed=31):
    wv = np.stack([fbm(xyz, seed=warp_seed + k, octaves=3) for k in range(3)], axis=-1)
    warped = xyz + 0.10 * wv
    warped /= np.linalg.norm(warped, axis=-1, keepdims=True)
    return softmin_field(warped, pos, beta) + fbm(xyz, seed=30) * (0.8 * r_deg)


def main():
    d = e30.load()
    r_deg = e30.ocean_radius(d["lattice"])
    ll, tt, xyz = e30.grid()
    hard, _ = e30.fields(xyz, d["pos"], np.zeros(len(d["pos"]), dtype=int))
    target = float((np.cos(tt) * (hard < r_deg)).sum() / np.cos(tt).sum())
    beta = 3.0 / r_deg
    sigma = np.radians(0.6 * r_deg)

    base_field = field_e(d["pos"], xyz, beta, r_deg)
    base_land = base_field < level_for_area(base_field, tt, target)
    w = np.cos(tt)

    panels = []
    for seed in (41, 42, 43):
        pos_j = jitter(d["pos"], sigma, seed)
        f = field_e(pos_j, xyz, beta, r_deg)
        level = level_for_area(f, tt, target)
        land = f < level
        agree = float((w * (land == base_land)).sum() / w.sum())
        dim = richardson_dimension(ll, tt, f, level)
        panels.append((seed, f, level, agree, dim))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    cmap = saturated_magma()
    view_lon, view_lat = np.radians(-35), np.radians(12)
    fig, top = figure(
        16.4,
        6.8,
        7,
        "E30b · organic coastlines",
        "The shuffle knob: three seeds, same clusters, rerolled shorelines",
        meta=(
            f"rule E (warp + fBm) · field-only tangent jitter, sigma {0.6 * r_deg:.1f}° "
            f"(0.6 coast), Rayleigh amplitudes · rendered tiles never move · land "
            f"{target:.0%} every seed · agreement vs unjittered baseline in panel titles"
        ),
    )
    gs = fig.add_gridspec(1, 3, left=0.025, right=0.975, top=top, bottom=0.05, wspace=0.04)
    for i, (seed, field, level, agree, dim) in enumerate(panels):
        img, mask, z = ortho_sample(field, view_lon, view_lat)
        near = punch(np.clip(1.0 - (img - level + r_deg) / (2.5 * r_deg), 0, 1))
        shade = 0.55 + 0.45 * z
        rgba = cmap(near)
        rgba[..., :3] *= shade[..., None]
        rgba[~mask] = mcolors.to_rgba(PANEL)
        ax = fig.add_subplot(gs[0, i], facecolor=PANEL)
        ax.imshow(rgba, origin="lower", interpolation="bilinear")
        signed = np.where(mask, img - level, np.nan)
        ax.contour(signed, levels=[0.0], colors=[CYAN], linewidths=1.4, linestyles="solid")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
        panel_title(ax, f"seed {seed} · land agreement {agree:.0%} · coast D={dim:.2f}", width=40)
    verdict(
        fig,
        f"the landmasses hold ({min(p[3] for p in panels):.0%}+ agreement); the shoreline rerolls",
    )
    frame_panels(fig)
    out = OUT / "07-the-shuffle-knob.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
