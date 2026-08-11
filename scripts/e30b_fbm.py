"""Checkpoint: the noise step done properly — Perlin-gradient fBm and domain
warping (Perlin 1985/2002, Musgrave 1989, Quilez) vs the 2-octave value-noise
wobble, with measured coastline fractal dimension vs Mandelbrot's ~1.25."""

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
RES = 1000


# --- Perlin gradient noise + fBm -------------------------------------------


def _perlin3(p, n, rng):
    """Seeded 3D gradient noise on an n^3 lattice, evaluated at points p
    (unit-cube coords scaled to lattice). Classic Perlin: dot(gradient,
    offset) at 8 corners, smootherstep blend."""
    g = rng.normal(size=(n + 1, n + 1, n + 1, 3))
    g /= np.linalg.norm(g, axis=-1, keepdims=True)
    u = np.clip(p, 0, 1) * (n - 1e-6)
    i0 = u.astype(int)
    f = u - i0
    t = f * f * f * (f * (f * 6 - 15) + 10)  # smootherstep
    out = np.zeros(p.shape[:-1])
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                corner = g[i0[..., 0] + dx, i0[..., 1] + dy, i0[..., 2] + dz]
                off = f - np.array([dx, dy, dz])
                dot = (corner * off).sum(-1)
                w = (
                    (t[..., 0] if dx else 1 - t[..., 0])
                    * (t[..., 1] if dy else 1 - t[..., 1])
                    * (t[..., 2] if dz else 1 - t[..., 2])
                )
                out += w * dot
    return out


def fbm(xyz, seed, octaves=6, base=4, lacunarity=2.0, gain=0.5):
    """Fractional Brownian motion over seeded Perlin octaves, sampled on the
    sphere via 3D position (seam-free by construction)."""
    rng = np.random.default_rng(seed)
    p = (xyz + 1) / 2
    out = np.zeros(xyz.shape[:-1])
    amp, freq, norm = 1.0, 1, 0.0
    for _ in range(octaves):
        n = int(base * freq)
        out += amp * _perlin3((p * freq) % 1.0, n, rng)
        norm += amp
        amp *= gain
        freq = int(freq * lacunarity)
    return out / norm


def richardson_dimension(ll, tt, field, level):
    """Mandelbrot's divider method on the longest single coastline: walk the
    contour with rulers of decreasing arc length; L(r) ~ r^(1-D). Box
    counting is wrong here — the archipelago's disconnected islands collapse
    to lone boxes at coarse scale and drag the slope below 1."""
    import matplotlib.pyplot as plt

    f = plt.figure()
    cs = plt.contour(ll, tt, field, levels=[level])
    paths = max(cs.allsegs[0], key=len)
    plt.close(f)
    lon, lat = paths[:, 0], paths[:, 1]
    pts = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=1)
    rulers = np.radians([1.5, 3.0, 6.0, 12.0])
    lengths = []
    for r in rulers:
        anchor = pts[0]
        steps = 0
        for p in pts[1:]:
            if np.arccos(np.clip(anchor @ p, -1, 1)) >= r:
                steps += 1
                anchor = p
        lengths.append(max(steps, 1) * r)
    slope = np.polyfit(np.log(rulers), np.log(lengths), 1)[0]
    return float(1 - slope)


def ortho_sample(field, view_lon, view_lat):
    y, x = np.mgrid[-1 : 1 : RES * 1j, -1 : 1 : RES * 1j]
    r2 = x * x + y * y
    mask = r2 <= 1.0
    z = np.sqrt(np.clip(1.0 - r2, 0, 1))
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

    # C (previous checkpoint): 2-octave value noise, additive
    c_field = soft + value_noise(xyz, seed=30) * (0.55 * r_deg)

    # D: additive Perlin fBm — fractal detail at every octave
    d_field = soft + fbm(xyz, seed=30) * (1.1 * r_deg)

    # E: Quilez domain warp — the geography itself is displaced by a smooth
    # vector field, then fBm roughens the shoreline
    warp_vec = np.stack(
        [fbm(xyz, seed=31, octaves=3), fbm(xyz, seed=32, octaves=3), fbm(xyz, seed=33, octaves=3)],
        axis=-1,
    )
    warped = xyz + 0.10 * warp_vec
    warped /= np.linalg.norm(warped, axis=-1, keepdims=True)
    e_field = softmin_field(warped, d["pos"], beta) + fbm(xyz, seed=30) * (0.8 * r_deg)

    panels = []
    for title, field in [
        ("C — value noise, 2 octaves (previous)", c_field),
        ("D — Perlin fBm, 6 octaves, additive", d_field),
        ("E — domain warp + fBm (Quilez composite)", e_field),
    ]:
        level = level_for_area(field, tt, target)
        dim = richardson_dimension(ll, tt, field, level)
        panels.append((title, field, level, dim))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cmap = saturated_magma()
    view_lon, view_lat = np.radians(-35), np.radians(12)
    fig, top = figure(
        16.4,
        6.8,
        6,
        "E30b · organic coastlines",
        "The noise step done properly: fBm octaves and a warped domain",
        meta=(
            f"n={len(d['pos'])} · land {target:.0%} everywhere · Perlin-gradient fBm, "
            f"6 octaves, lacunarity 2, gain 0.5 · warp 0.10 rad (3-octave vector fBm) · "
            f"D = Richardson divider on the longest coast, rulers 1.5-12° · "
            f"Britain ~1.25 (Mandelbrot 1967) · seeds 30-33"
        ),
    )
    gs = fig.add_gridspec(1, 3, left=0.025, right=0.975, top=top, bottom=0.05, wspace=0.04)
    for i, (title, field, level, dim) in enumerate(panels):
        img, mask, z = ortho_sample(field, view_lon, view_lat)
        near = punch(np.clip(1.0 - (img - level + r_deg) / (2.5 * r_deg), 0, 1))
        shade = 0.55 + 0.45 * z
        rgba = cmap(near)
        rgba[..., :3] *= shade[..., None]
        import matplotlib.colors as mcolors

        rgba[~mask] = mcolors.to_rgba(PANEL)
        ax = fig.add_subplot(gs[0, i], facecolor=PANEL)
        ax.imshow(rgba, origin="lower", interpolation="bilinear")
        signed = np.where(mask, img - level, np.nan)
        ax.contour(signed, levels=[0.0], colors=[CYAN], linewidths=1.4, linestyles="solid")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
        panel_title(ax, f"{title} · coast D={dim:.2f}", width=40)
    verdict(
        fig,
        f"octaves buy dimension: D {panels[0][3]:.2f} vs {panels[1][3]:.2f} vs {panels[2][3]:.2f}",
    )
    frame_panels(fig)
    out = OUT / "06-fbm-and-domain-warp.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
