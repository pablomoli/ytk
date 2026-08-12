"""Organic-coast primitives and the per-planet texture bake, ported verbatim
from the experiment scripts (`scripts/e30b_fbm.py`, `scripts/e30b_organic_coast.py`,
`scripts/e30_coastlines.py`) into this module's production home — same
precedent as `spread()` landing in `ytk/spheremap.py`. The numerics are
experimentally validated there and are not reworked here.

Texel contract (the shader reads this): 0.5 is the shoreline, > 0.5 is land
(1.0 = deepest inland at 2.5 * coast_deg), < 0.5 is ocean.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from ytk.spheremap import fibonacci, radial, spread

N_PROBES = 8192


def _perlin3(p: NDArray[Any], n: int, rng: np.random.Generator) -> NDArray[Any]:
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


def fbm(
    xyz: NDArray[Any],
    seed: int,
    octaves: int = 6,
    base: int = 4,
    lacunarity: float = 2.0,
    gain: float = 0.5,
) -> NDArray[Any]:
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


def softmin_field(xyz: NDArray[Any], pos: NDArray[Any], beta: float) -> NDArray[Any]:
    """-1/beta * log(sum exp(-beta*d_i)): the metaball union of all notes.
    beta -> inf recovers the hard min (circles)."""
    flat = xyz.reshape(-1, 3)
    acc = np.zeros(len(flat))
    for i in range(0, len(flat), 20000):
        d = np.degrees(np.arccos(np.clip(flat[i : i + 20000] @ pos.T, -1.0, 1.0)))
        acc[i : i + 20000] = -np.log(np.exp(-beta * d).sum(axis=1)) / beta
    return acc.reshape(xyz.shape[:2])


def level_for_area(field: NDArray[Any], tt: NDArray[Any], target: float) -> float:
    """Contour level such that cos-weighted land area equals target."""
    w = np.cos(tt).ravel()
    f = field.ravel()
    order = np.argsort(f)
    cum = np.cumsum(w[order]) / w.sum()
    return float(f[order][np.searchsorted(cum, target)])


def ocean_radius(lattice: NDArray[Any]) -> float:
    """Same calibration as E29: the uniform pole defines zero ocean. p99 of
    fibonacci-probe gaps."""
    probes = fibonacci(N_PROBES)
    dots = np.clip(probes @ lattice.T, -1.0, 1.0)
    gaps: NDArray[Any] = np.degrees(np.arccos(dots.max(axis=1)))
    return float(np.quantile(gaps, 0.99))


def grid(nlon: int = 512, nlat: int = 256) -> tuple[NDArray[Any], NDArray[Any], NDArray[Any]]:
    """Lon/lat mesh (radians) and its unit vectors. Lon spans -pi..pi
    inclusive so column 0 and column -1 are the same direction."""
    lon = np.linspace(-np.pi, np.pi, nlon)
    lat = np.linspace(-np.pi / 2, np.pi / 2, nlat)
    ll, tt = np.meshgrid(lon, lat)
    xyz = np.stack([np.cos(tt) * np.cos(ll), np.cos(tt) * np.sin(ll), np.sin(tt)], axis=-1)
    return ll, tt, xyz


def organic_sd(
    pos: NDArray[Any], xyz: NDArray[Any], tt: NDArray[Any], coast_deg: float
) -> NDArray[Any]:
    """Signed distance in degrees: softmin metaballs over a domain warped by
    3-octave vector fBm plus 6-octave fBm roughness, shifted so land area
    equals the hard-rule area at coast_deg. Composition and seeds (30/31)
    copied from `organic_field()` + `main()`'s `sd = field - level_for_area(...)`
    in scripts/e30_coastlines.py."""
    beta = 3.0 / coast_deg
    warp_vec = np.stack(
        [fbm(xyz, seed=31 + k, octaves=3) for k in range(3)],
        axis=-1,
    )
    warped = xyz + 0.10 * warp_vec
    warped /= np.linalg.norm(warped, axis=-1, keepdims=True)
    field = softmin_field(warped, pos, beta) + fbm(xyz, seed=30) * (0.8 * coast_deg)
    dist = np.degrees(np.arccos(np.clip(xyz @ pos.T, -1.0, 1.0))).min(axis=-1)
    target = float((np.cos(tt) * (dist < coast_deg)).sum() / np.cos(tt).sum())
    return field - level_for_area(field, tt, target)


def bake_planet(member_c3: NDArray[Any], out_path: Path) -> dict[str, float]:
    from PIL import Image

    pos = spread(radial(np.asarray(member_c3, dtype=float)))
    coast_deg = ocean_radius(fibonacci(len(pos)))
    _, tt, xyz = grid()
    sd = organic_sd(pos, xyz, tt, coast_deg)
    texel = np.clip(0.5 - sd / (5.0 * coast_deg), 0.0, 1.0)
    texel[:, -1] = texel[:, 0]  # identical directions; guard float drift
    Image.fromarray((texel * 255).astype(np.uint8), mode="L").save(out_path)
    w = np.cos(tt)
    return {
        "coast_deg": float(coast_deg),
        "land_frac": float((w * (sd < 0)).sum() / w.sum()),
    }


def bake_superplanet(
    radial_pos: NDArray[Any], lattice_pos: NDArray[Any], out_path: Path
) -> dict[str, float]:
    """radial_pos is the already-spread layout (map.json's sp["radial"], the
    output of spread(radial(c3))) — spread() is not reapplied here."""
    from PIL import Image

    pos = np.asarray(radial_pos, dtype=float)
    pos /= np.linalg.norm(pos, axis=1, keepdims=True)
    coast_deg = ocean_radius(np.asarray(lattice_pos, dtype=float))
    _, tt, xyz = grid(1024, 512)
    sd = organic_sd(pos, xyz, tt, coast_deg)
    texel = np.clip(0.5 - sd / (5.0 * coast_deg), 0.0, 1.0)
    texel[:, -1] = texel[:, 0]  # identical directions; guard float drift
    Image.fromarray((texel * 255).astype(np.uint8), mode="L").save(out_path)
    w = np.cos(tt)
    return {
        "coast_deg": float(coast_deg),
        "land_frac": float((w * (sd < 0)).sum() / w.sum()),
    }
