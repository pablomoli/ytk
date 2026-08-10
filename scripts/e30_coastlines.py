"""E30 — coastlines: draw the land/sea boundary of the /orb planet.

E29's ocean definition induces the coastline for free: land is everything
within the calibrated ocean radius of a tile, sea is everything beyond it,
and the coast is the iso-distance contour between them — no bandwidth knob,
no density estimate. Continents are wrap-aware connected land components,
named by the themes of the tiles they contain.

    uv run --with matplotlib,scipy python scripts/e30_coastlines.py field
    ...                                                             continents
    ...                                                             assets
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DIM,
    DPI,
    FRAME,
    GOLD,
    PANEL,
    PURPLE,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    punch,
    saturated_magma,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from ytk.spheremap import OCCL_DEG, fibonacci

MAP = Path(os.path.expanduser("~/.ytk/map.json"))
ASSETS = REPO / "docs" / "assets" / "30-coastlines"

# 0.5 deg grid: fine enough that the coast contour is smooth at print size
NLON, NLAT = 721, 361
N_PROBES = 8192


def sha() -> str:
    r = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    )
    return r.stdout.strip() or "unknown"


def load() -> dict:
    data = json.loads(MAP.read_text())
    sp = data["content"]["sphere"]
    cpts = [p for p in data["points"] if "c3" in p]
    pos = np.asarray(sp["radial"], dtype=float)
    pos /= np.linalg.norm(pos, axis=1, keepdims=True)
    lat_pos = np.asarray(sp["lattice"], dtype=float)
    lat_pos /= np.linalg.norm(lat_pos, axis=1, keepdims=True)
    return {
        "pos": pos,
        "lattice": lat_pos,
        "themes": np.asarray([p.get("th", -1) for p in cpts]),
        "labels": [g["label"] for g in data["content"]["groups"]],
        "chosen": sp["chosen"],
    }


def ocean_radius(lattice: np.ndarray) -> float:
    """Same calibration as E29: the uniform pole defines zero ocean."""
    probes = fibonacci(N_PROBES)
    dots = np.clip(probes @ lattice.T, -1.0, 1.0)
    return float(np.quantile(np.degrees(np.arccos(dots.max(axis=1))), 0.99))


def grid() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Lon/lat mesh (radians, Mollweide-ready) and its unit vectors."""
    lon = np.linspace(-np.pi, np.pi, NLON)
    lat = np.linspace(-np.pi / 2, np.pi / 2, NLAT)
    ll, tt = np.meshgrid(lon, lat)
    xyz = np.stack([np.cos(tt) * np.cos(ll), np.cos(tt) * np.sin(ll), np.sin(tt)], axis=-1)
    return ll, tt, xyz


def fields(xyz: np.ndarray, pos: np.ndarray, themes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per grid cell: geodesic distance to the nearest tile (deg) and that
    tile's theme. Chunked so the (cells x tiles) dot matrix stays small."""
    flat = xyz.reshape(-1, 3)
    dist = np.empty(len(flat))
    theme = np.empty(len(flat), dtype=int)
    for i in range(0, len(flat), 20000):
        dots = np.clip(flat[i : i + 20000] @ pos.T, -1.0, 1.0)
        nearest = dots.argmax(axis=1)
        dist[i : i + 20000] = np.degrees(np.arccos(dots.max(axis=1)))
        theme[i : i + 20000] = themes[nearest]
    return dist.reshape(xyz.shape[:2]), theme.reshape(xyz.shape[:2])


def continents(land: np.ndarray) -> np.ndarray:
    """Wrap-aware connected components of the land mask. The lon seam is a
    grid artifact, not a coast: labels touching across it are merged."""
    from scipy import ndimage

    comp, n = ndimage.label(land)
    for row in range(land.shape[0]):
        a, b = comp[row, 0], comp[row, -1]
        if a and b and a != b:
            comp[comp == b] = a
    # compact the label ids after merging
    ids = [i for i in np.unique(comp) if i != 0]
    out = np.zeros_like(comp)
    for k, i in enumerate(ids, start=1):
        out[comp == i] = k
    return out


def continent_stats(
    comp: np.ndarray, tt: np.ndarray, theme_grid: np.ndarray, labels: list[str]
) -> list[dict]:
    """Area-weighted stats per continent; named by dominant tile themes."""
    cell_w = np.cos(tt)
    total = cell_w.sum()
    out = []
    for i in np.unique(comp):
        if i == 0:
            continue
        mask = comp == i
        area = float(cell_w[mask].sum() / total)
        th, counts = np.unique(theme_grid[mask & (theme_grid >= 0)], return_counts=True)
        order = counts.argsort()[::-1]
        names = [labels[t] for t in th[order][:2] if 0 <= t < len(labels)]
        out.append({"id": int(i), "area": area, "names": names})
    out.sort(key=lambda c: -c["area"])
    return out


# --- figures ---------------------------------------------------------------


def _moll(fig, cell):
    ax = fig.add_subplot(cell, projection="mollweide", facecolor=PANEL)
    ax.grid(color=FRAME, lw=0.4, alpha=0.6)
    ax.tick_params(colors=BG, labelsize=1)  # hide graticule labels, keep lines
    for spine in ax.spines.values():
        spine.set_color(FRAME)
    return ax


def _tiles_lonlat(pos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.arctan2(pos[:, 1], pos[:, 0]), np.arcsin(np.clip(pos[:, 2], -1, 1))


def fig_field(d: dict, ll, tt, dist, r_deg: float, out: Path, number: int = 1) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    land_frac = float((np.cos(tt) * (dist < r_deg)).sum() / np.cos(tt).sum())
    fig, top = figure(
        16.0,
        8.6,
        number,
        "E30 · coastlines",
        "The planet unrolled: the ocean-radius contour is the coast",
        meta=(
            f"n={len(d['pos'])} tiles (spread radial, chosen={d['chosen']}) · "
            f"coast at {r_deg:.1f}° (E29 ocean calibration) · land {land_frac:.0%} of the sphere · "
            f"grid 0.5° · commit {sha()}"
        ),
    )
    gs = fig.add_gridspec(1, 1, left=0.05, right=0.95, top=top, bottom=0.06)
    ax = _moll(fig, gs[0, 0])
    # nearness ramp: bright = close to content, the sea falls into the dark end
    near = punch(np.clip(1.0 - dist / (2.5 * r_deg), 0, 1))
    ax.pcolormesh(
        ll, tt, near, cmap=saturated_magma(), vmin=0, vmax=1, shading="auto", rasterized=True
    )
    ax.contour(ll, tt, dist, levels=[r_deg], colors=[CYAN], linewidths=1.6)
    lon, lat = _tiles_lonlat(d["pos"])
    ax.scatter(lon, lat, s=2.5, c=TEXT, alpha=0.5, linewidths=0)
    panel_title(
        ax,
        "geodesic distance to the nearest note, coast drawn at the calibrated ocean radius",
        width=90,
    )
    verdict(fig, f"land {land_frac:.0%} · sea {1 - land_frac:.0%}")
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


CONTINENT_TINTS = [GOLD, BLUE, CYAN, PURPLE, "#d98a5f", "#7fbf7f", "#c66fd1", "#8a93ff"]


def fig_continents(
    d: dict, ll, tt, dist, theme_grid, comp, stats, r_deg, out: Path, number: int = 2
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    fig, top = figure(
        16.0,
        8.6,
        number,
        "E30 · coastlines",
        "The named continents: land components labeled by their dominant themes",
        meta=(
            f"{len(stats)} continents at coast {r_deg:.1f}° · largest "
            f"{stats[0]['area']:.0%} of the sphere · named by tile themes · commit {sha()}"
        ),
    )
    gs = fig.add_gridspec(1, 1, left=0.05, right=0.95, top=top, bottom=0.06)
    ax = _moll(fig, gs[0, 0])
    # projection-safe paint: one colormap slot per (continent, shade level),
    # composed through pcolormesh — imshow cannot ride the Mollweide transform
    levels = 14
    shade_lo = 0.40
    palette = [mcolors.to_rgb(DIM)]
    for k in range(len(stats)):
        base = np.asarray(mcolors.to_rgb(CONTINENT_TINTS[k % len(CONTINENT_TINTS)]))
        for s in range(levels):
            palette.append(tuple(base * (shade_lo + (1 - shade_lo) * (s + 0.5) / levels)))
    cmap = mcolors.ListedColormap(palette)
    paint = np.zeros(comp.shape)
    for k, c in enumerate(stats):
        mask = comp == c["id"]
        shade = punch(np.clip(1.0 - dist[mask] / r_deg, 0, 1))
        paint[mask] = 1 + k * levels + np.clip((shade * levels).astype(int), 0, levels - 1)
    ax.pcolormesh(
        ll,
        tt,
        paint,
        cmap=cmap,
        vmin=-0.5,
        vmax=len(palette) - 0.5,
        shading="auto",
        rasterized=True,
    )
    ax.contour(ll, tt, dist, levels=[r_deg], colors=[TEXT], linewidths=1.0, alpha=0.8)
    # labels sit at each continent's interior pole (deepest inland cell),
    # never its centroid — a sprawling landmass centres over someone else
    from matplotlib import patheffects as pe
    from scipy import ndimage

    # cos(lat) deflates the polar rows, which the grid-space transform
    # inflates (a Mollweide pole row is one real point stretched wide)
    inland = ndimage.distance_transform_edt(dist < r_deg) * np.cos(tt)
    for k, c in enumerate(stats[:6]):
        masked = np.where(comp == c["id"], inland, -1.0)
        r, cc = np.unravel_index(int(masked.argmax()), masked.shape)
        names = c["names"] if c["area"] >= 0.02 else c["names"][:1]
        name = "\n".join(names) if names else "unthemed"
        ax.annotate(
            name,
            (ll[r, cc], tt[r, cc]),
            color=TEXT,
            fontsize=8.5,
            ha="center",
            va="center",
            path_effects=[pe.withStroke(linewidth=2.4, foreground=BG)],
        )
    panel_title(
        ax,
        "each continent tinted, shaded by nearness to its notes, labeled by its top themes",
        width=90,
    )
    verdict(
        fig, f"{len(stats)} continents; largest carries {' + '.join(stats[0]['names'][:1]) or '?'}"
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


# --- stages ----------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["field", "continents", "assets"])
    ap.add_argument("--out", default=os.environ.get("CLAUDE_JOB_DIR", "/tmp") + "/tmp")
    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    d = load()
    r_deg = ocean_radius(d["lattice"])
    ll, tt, xyz = grid()
    dist, theme_grid = fields(xyz, d["pos"], d["themes"])
    land = dist < r_deg
    print(
        f"{len(d['pos'])} tiles · coast {r_deg:.2f}° · render occl bound {OCCL_DEG:.2f}° · "
        f"land {(np.cos(tt) * land).sum() / np.cos(tt).sum():.1%}"
    )

    if args.stage == "field":
        fig_field(d, ll, tt, dist, r_deg, outdir / "e30-cp1-field.png")
        return

    comp = continents(land)
    stats = continent_stats(comp, tt, theme_grid, d["labels"])
    for c in stats[:10]:
        print(f"  continent {c['id']}: {c['area']:.1%} — {', '.join(c['names']) or 'unthemed'}")

    if args.stage == "continents":
        fig_continents(
            d, ll, tt, dist, theme_grid, comp, stats, r_deg, outdir / "e30-cp2-continents.png"
        )
        return

    if args.stage == "assets":
        ASSETS.mkdir(parents=True, exist_ok=True)
        fig_field(d, ll, tt, dist, r_deg, ASSETS / "01-the-planet-unrolled.png", number=1)
        fig_continents(
            d,
            ll,
            tt,
            dist,
            theme_grid,
            comp,
            stats,
            r_deg,
            ASSETS / "02-the-named-continents.png",
            number=2,
        )
        (ASSETS / "continents.json").write_text(
            json.dumps({"coast_deg": r_deg, "continents": stats}, indent=1)
        )
        print(f"wrote {ASSETS / 'continents.json'}")


if __name__ == "__main__":
    main()
