"""Sphere layouts for the /orb gallery: three candidate projections of the
content embedding onto the unit sphere, scored on fidelity (trustworthiness,
same metric as map.json's trustworthiness_3d) and legibility (angular
overlap at the render threshold). All layouts index the content points in
map.json order."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

GOLDEN = np.pi * (3.0 - np.sqrt(5.0))

# Must match TILE_HALF in web/src/lib/orb/scene.ts — the rendered tile's
# half-extent at radius 1. Nearer than one half-width, a neighbour hides more
# than half the tile (E29, docs/assets/29-planet-continents/).
TILE_HALF = 0.055
OCCL = float(np.arctan(TILE_HALF))
OCCL_DEG = float(np.degrees(OCCL))


def radial(c3: NDArray[Any]) -> NDArray[Any]:
    """Unit directions from the layout centroid; radius discarded."""
    v = np.asarray(c3, dtype=float) - np.asarray(c3, dtype=float).mean(axis=0)
    n = np.linalg.norm(v, axis=1, keepdims=True)
    # centroid-coincident rows get an arbitrary fixed direction, not NaN
    v = np.where(n < 1e-12, np.array([1.0, 0.0, 0.0]), v / np.maximum(n, 1e-12))
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def spread(
    pos: NDArray[Any],
    iters: int = 40,
    target: float = 1.15 * OCCL,
    step: float = 0.35,
    seed: int = 29,
) -> NDArray[Any]:
    """E29's winning de-overlap: fixed-iteration tangent repulsion. Converges
    by ~40 iterations (the force is zero once no pair is nearer than target);
    the seeded jitter only breaks exactly-coincident bearings, where the
    tangent is undefined."""
    rng = np.random.default_rng(seed)
    p = np.asarray(pos, dtype=float) + rng.normal(0.0, 1e-4, pos.shape)
    p /= np.linalg.norm(p, axis=1, keepdims=True)
    for _ in range(iters):
        dots = np.clip(p @ p.T, -1.0, 1.0)
        ang = np.arccos(dots)
        w = np.where(ang < target, (target - ang) / target, 0.0)
        np.fill_diagonal(w, 0.0)
        if not w.any():
            break
        t = p[:, None, :] * dots[:, :, None] - p[None, :, :]
        t /= np.maximum(np.sqrt(1.0 - dots * dots), 1e-9)[:, :, None]
        p = p + step * OCCL * (w[:, :, None] * t).sum(axis=1)
        p /= np.linalg.norm(p, axis=1, keepdims=True)
    return p


def fibonacci(n: int) -> NDArray[Any]:
    i = np.arange(n, dtype=float)
    z = 1.0 - 2.0 * (i + 0.5) / n
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = GOLDEN * i
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


def lattice(themes: list[int], radial_dirs: NDArray[Any]) -> NDArray[Any]:
    """Fibonacci slots assigned theme-block first: theme runs are contiguous
    along the spiral, sequenced by a greedy nearest-neighbour walk over theme
    centroid directions; within a theme, members follow their radial azimuth
    so local neighbours stay related."""
    themes_arr = np.asarray(themes)
    slots = fibonacci(len(themes))
    ids = sorted(set(themes))
    cents = {t: radial_dirs[themes_arr == t].mean(axis=0) for t in ids}
    for t in ids:
        n = np.linalg.norm(cents[t])
        cents[t] = cents[t] / n if n > 1e-12 else np.array([1.0, 0.0, 0.0])
    # greedy walk from the largest theme through nearest centroids
    order = [max(ids, key=lambda t: int((themes_arr == t).sum()))]
    rest = [t for t in ids if t != order[0]]
    while rest:
        last = cents[order[-1]]
        nxt = max(rest, key=lambda t: float(cents[t] @ last))
        order.append(nxt)
        rest.remove(nxt)
    out = np.zeros((len(themes), 3))
    cursor = 0
    for t in order:
        members = np.flatnonzero(themes_arr == t)
        c = cents[t]
        # azimuth around the theme centroid axis orders members in-run
        ref = np.array([0.0, 0.0, 1.0]) if abs(c[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        e1 = np.cross(c, ref)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(c, e1)  # type: ignore[assignment]
        az = np.arctan2(radial_dirs[members] @ e2, radial_dirs[members] @ e1)  # type: ignore[arg-type]
        for k, m in enumerate(members[np.argsort(az)]):
            out[m] = slots[cursor + k]
        cursor += len(members)
    return out


def haversine(vecs: NDArray[Any], n_neighbors: int, min_dist: float) -> NDArray[Any] | None:
    """UMAP fitted directly on the 2-sphere; None on failure (recorded, not
    raised — the caller ships the surviving layouts)."""
    import umap  # type: ignore[import-not-found]

    try:
        emb = umap.UMAP(  # type: ignore[attr-defined]
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            n_components=2,
            metric="cosine",
            output_metric="haversine",
            random_state=42,
        ).fit_transform(np.asarray(vecs, dtype=float))
        xyz = np.stack(
            [
                np.sin(emb[:, 0]) * np.cos(emb[:, 1]),  # type: ignore[index]
                np.sin(emb[:, 0]) * np.sin(emb[:, 1]),  # type: ignore[index]
                np.cos(emb[:, 0]),  # type: ignore[index]
            ],
            axis=1,
        )
        if np.isnan(xyz).any():
            return None
        return xyz
    except Exception as exc:  # any UMAP failure is a data point
        print(f"haversine layout failed: {exc!r}")
        return None


def score(vecs: NDArray[Any], pos: NDArray[Any]) -> dict[str, Any]:
    from sklearn.manifold import trustworthiness  # type: ignore[reportMissingTypeStubs]

    n = len(pos)
    dots = np.clip(pos @ pos.T, -1.0, 1.0)
    np.fill_diagonal(dots, -1.0)
    nn_deg = np.degrees(np.arccos(dots.max(axis=1)))
    # the render threshold, not an equal-area cell: E29 measured the old
    # n-derived theta (4.19 deg at n=587) judging separations the renderer
    # never draws — TILE_HALF is what the screen actually shows
    theta_deg = OCCL_DEG
    overlap = int((nn_deg < theta_deg).sum())
    # sklearn requires n_neighbors < n_samples / 2
    nn = min(15, max(1, n // 2 - 1))
    return {
        "trustworthiness": float(trustworthiness(vecs, pos, n_neighbors=nn, metric="cosine")),  # type: ignore[arg-type]
        "mean_nn_deg": float(nn_deg.mean()),
        "overlap": overlap,
        "overlap_frac": float(overlap / n),
    }


def choose(scores: dict[str, dict[str, Any]], max_overlap_frac: float = 0.05) -> str:
    ok = {k: v for k, v in scores.items() if v["overlap_frac"] <= max_overlap_frac}
    pool = ok or scores  # nothing legible: fall back to raw fidelity
    return max(pool, key=lambda k: pool[k]["trustworthiness"])


def _round(a: NDArray[Any]) -> list[list[float]]:
    return [[round(float(x), 4) for x in row] for row in a]


def sphere_block(
    vecs: NDArray[Any],
    c3: NDArray[Any],
    themes: list[int],
    n_neighbors: int = 30,
    min_dist: float = 0.05,
    run_haversine: bool = True,
) -> dict[str, Any]:
    rad = radial(c3)
    # lattice orders members by the true bearings; the shipped radial layout
    # is those bearings spread to visibility (E29: anchor 1.000, trust -0.002)
    lat = lattice(themes, rad)
    layouts: dict[str, NDArray[Any] | None] = {"radial": spread(rad), "lattice": lat}
    layouts["haversine"] = haversine(vecs, n_neighbors, min_dist) if run_haversine else None
    scores = {k: score(vecs, v) for k, v in layouts.items() if v is not None}
    return {
        "radial": _round(rad),
        "haversine": _round(layouts["haversine"]) if layouts["haversine"] is not None else None,
        "lattice": _round(lat),
        "scores": scores,
        "chosen": choose(scores),
    }
