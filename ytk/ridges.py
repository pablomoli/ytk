# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Density terrain for the 2D map layouts: KDE contours + SCMS ridges.

The math core is hand-rolled (numpy only) on purpose — this module doubles
as the worked exercise for the retention project (see
docs/math/terrain-derivation.md for the full derivation):

- Gaussian KDE with Silverman's rule-of-thumb bandwidth,
- analytic gradient and Hessian of the log-density,
- subspace-constrained mean shift (Ozertem & Erdogmus 2011) tracing the
  ridge set {x : v2^T grad f = 0, lambda2 < 0},
- marching squares for contour polylines.

All coordinates are in the map's normalized layout space (roughly [-1, 1]).
"""

from __future__ import annotations

from typing import Literal, overload

import numpy as np

# A bandwidth is either a scalar (classic fixed-bandwidth KDE) or one value
# per data point (sample-point adaptive KDE). Every kernel routine here
# broadcasts it to (n,), so the two forms are interchangeable at call sites.
Bandwidth = float | np.ndarray

# A 2D point in layout space. Contour code passes these as plain tuples so
# they stay hashable for the endpoint-matching dict in _chain_segments.
Point = tuple[float, float]

_CHUNK = 256  # query rows per block; bounds the (m, n, 2) intermediates


def silverman_bandwidth(pts: np.ndarray) -> float:
    """Rule of thumb in d dims: h = sigma * n^(-1/(d+4)), sigma averaged
    across axes (d=2 gives the familiar n^(-1/6))."""
    pts = np.asarray(pts, float)
    d = pts.shape[1]
    sigma = float(pts.std(axis=0, ddof=1).mean())
    return sigma * len(pts) ** (-1 / (d + 4))


def kde(pts: np.ndarray, h: Bandwidth, query: np.ndarray) -> np.ndarray:
    """f(x) = (1/n) sum_i N(x; x_i, h_i^2 I) evaluated at query rows.

    Dimension-agnostic, and h may be a scalar (classic fixed-bandwidth KDE)
    or a per-data-point array (sample-point adaptive KDE: each point casts
    a bump of its own width, so each kernel carries its own normalization
    (2 pi h_i^2)^(d/2))."""
    pts = np.asarray(pts, float)
    query = np.asarray(query, float)
    d = pts.shape[1]
    hs = np.broadcast_to(np.asarray(h, float), (len(pts),))
    inv2h2 = 1.0 / (2 * hs * hs)
    knorm = (2 * np.pi * hs * hs) ** (d / 2)
    out = np.empty(len(query))
    for s in range(0, len(query), _CHUNK):
        q = query[s : s + _CHUNK]
        d2 = ((q[:, None, :] - pts[None, :, :]) ** 2).sum(-1)
        out[s : s + _CHUNK] = (np.exp(-d2 * inv2h2) / knorm).sum(1) / len(pts)
    return out


def knn_bandwidths(pts: np.ndarray, k: int = 8) -> np.ndarray:
    """Per-point adaptive bandwidths: h_i scales with the distance to the
    k-th nearest neighbor (lonely points cast wide fog, crowded points stay
    crisp), normalized so the median equals Silverman's global h and
    clamped to [0.5h, 3h] so no hermit point fogs the whole room."""
    pts = np.asarray(pts, float)
    h = silverman_bandwidth(pts)
    dk = np.empty(len(pts))
    for s in range(0, len(pts), _CHUNK):
        d2 = ((pts[s : s + _CHUNK, None, :] - pts[None, :, :]) ** 2).sum(-1)
        dk[s : s + _CHUNK] = np.sqrt(np.partition(d2, k, axis=1)[:, k])
    hi = h * dk / np.median(dk)
    return np.clip(hi, 0.5 * h, 3.0 * h)


def kde_grid(pts: np.ndarray, h: Bandwidth, gx: np.ndarray, gy: np.ndarray) -> np.ndarray:
    """Density on a regular grid; grid[j, i] = f(gx[i], gy[j])."""
    out = np.empty((len(gy), len(gx)))
    for j, y in enumerate(gy):
        q = np.column_stack([gx, np.full(len(gx), y)])
        out[j] = kde(pts, h, q)
    return out


@overload
def log_density_grad_hess(
    pts: np.ndarray, h: Bandwidth, x: np.ndarray, return_scale: Literal[False] = False
) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...


@overload
def log_density_grad_hess(
    pts: np.ndarray, h: Bandwidth, x: np.ndarray, return_scale: Literal[True]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]: ...


def log_density_grad_hess(
    pts: np.ndarray, h: Bandwidth, x: np.ndarray, return_scale: bool = False
) -> tuple[np.ndarray, ...]:
    """Density f, gradient and Hessian of log f, batched over query rows.
    h may be a scalar or a per-data-point array (adaptive KDE).

    With per-kernel normalization c_i = (2 pi h_i^2)^(-d/2), weights
    w_i = c_i exp(-|d_i|^2 / 2h_i^2) (d_i = x_i - x), W = sum w_i and the
    "pull weights" u_i = w_i / h_i^2, U = sum u_i:

        grad log f = sum u_i d_i / W
        hess log f = sum (w_i/h_i^4) d_i d_i^T / W - (U/W) I
                     - (grad log f)(grad log f)^T

    Uniform h collapses these to the classic m/h^2 and (S - m m^T)/h^4
    - I/h^2 forms. With return_scale the natural mean-shift step size
    W/U (= h^2 when uniform; Comaniciu's variable-bandwidth step) is
    returned as a fourth array. Verified against finite differences.
    """
    pts = np.asarray(pts, float)
    x = np.asarray(x, float)
    n, d = pts.shape
    hs = np.broadcast_to(np.asarray(h, float), (n,))
    inv_h2 = 1.0 / (hs * hs)
    knorm = (2 * np.pi * hs * hs) ** (d / 2)
    f = np.empty(len(x))
    grad = np.empty((len(x), d))
    hess = np.empty((len(x), d, d))
    scale = np.empty(len(x))
    eye = np.eye(d)
    for s in range(0, len(x), _CHUNK):
        q = x[s : s + _CHUNK]
        diff = pts[None, :, :] - q[:, None, :]  # (m, n, d) = x_i - x
        w = np.exp(-(diff**2).sum(-1) * inv_h2 / 2) / knorm  # (m, n)
        W = w.sum(1).clip(1e-300)
        u = w * inv_h2
        U = u.sum(1).clip(1e-300)
        g = (u[:, :, None] * diff).sum(1) / W[:, None]
        V = np.einsum("mn,mna,mnb->mab", u * inv_h2, diff, diff) / W[:, None, None]
        f[s : s + _CHUNK] = W / n
        grad[s : s + _CHUNK] = g
        hess[s : s + _CHUNK] = V - (U / W)[:, None, None] * eye - g[:, :, None] * g[:, None, :]
        scale[s : s + _CHUNK] = W / U
    return (f, grad, hess, scale) if return_scale else (f, grad, hess)


def eigh2(mats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Closed-form eigendecomposition of symmetric 2x2 matrices, batched.

    For [[a, b], [b, c]]: lambda = (a+c)/2 +- sqrt(((a-c)/2)^2 + b^2).
    Returns (vals, vecs) with vals ascending and eigenvectors in columns,
    matching np.linalg.eigh. Being symmetric, the two eigenvectors are
    orthogonal, so the second is the 90-degree rotation of the first.
    """
    mats = np.asarray(mats, float)
    a, b, c = mats[..., 0, 0], mats[..., 0, 1], mats[..., 1, 1]
    mean = (a + c) / 2
    disc = np.sqrt(((a - c) / 2) ** 2 + b**2)
    vals = np.stack([mean - disc, mean + disc], axis=-1)
    # (A - lambda I) v = 0 admits v = (b, lambda - a) and v = (lambda - c, b);
    # take whichever is nondegenerate, identity for the isotropic case.
    lo = vals[..., 0]
    cand1 = np.stack([b, lo - a], axis=-1)
    cand2 = np.stack([lo - c, b], axis=-1)
    pick2 = np.linalg.norm(cand2, axis=-1) > np.linalg.norm(cand1, axis=-1)
    v = np.where(pick2[..., None], cand2, cand1)
    norm = np.linalg.norm(v, axis=-1, keepdims=True)
    tiny = norm[..., 0] < 1e-12
    v = np.where(tiny[..., None], np.array([1.0, 0.0]), v / norm.clip(1e-300))
    v_perp = np.stack([-v[..., 1], v[..., 0]], axis=-1)
    return vals, np.stack([v, v_perp], axis=-1)


def scms(
    pts: np.ndarray,
    h: Bandwidth,
    seeds: np.ndarray,
    max_iter: int = 120,
    tol: float = 1e-4,
    floor_frac: float = 0.05,
) -> np.ndarray:
    """Subspace-constrained mean shift: walkers climb only along the
    cross-ridge direction (eigenvector of the smallest log-density Hessian
    eigenvalue) until the gradient has no component there — i.e. they stand
    on a crest. Returns the deduplicated converged ridge points."""
    pts = np.asarray(pts, float)
    x = np.array(seeds, float, copy=True)
    href = float(np.max(np.broadcast_to(np.asarray(h, float), (len(pts),))))
    lo = pts.min(0) - 3 * href
    hi = pts.max(0) + 3 * href
    floor = floor_frac * kde(pts, h, pts).max()
    keep = np.ones(len(x), bool)
    active = np.ones(len(x), bool)
    for _ in range(max_iter):
        idx = np.flatnonzero(active)
        if not len(idx):
            break
        f, grad, hess, scale = log_density_grad_hess(pts, h, x[idx], return_scale=True)
        _, vecs = eigh2(hess)
        v2 = vecs[:, :, 0]
        ms = grad * scale[:, None]  # natural mean-shift step (h^2 when uniform)
        step = (ms * v2).sum(1, keepdims=True) * v2
        x[idx] = np.clip(x[idx] + step, lo, hi)
        low = f < floor
        keep[idx[low]] = False
        done = (np.linalg.norm(step, axis=1) < tol) | low
        active[idx[done]] = False
    keep &= ~active  # never-converged walkers are not ridge points
    idx = np.flatnonzero(keep)
    if not len(idx):
        return np.empty((0, 2))
    f, _, hess = log_density_grad_hess(pts, h, x[idx])
    vals, _ = eigh2(hess)
    ok = (vals[:, 0] < 0) & (f >= floor)  # negative cross-ridge curvature
    out = x[idx[ok]]
    if not len(out):
        return out
    # Thin to ~0.01 cells, averaging walkers per cell: converged walkers pile
    # up unevenly along crests, and chaining needs even spacing more than it
    # needs raw density.
    _, inverse = np.unique(np.round(out, 2), axis=0, return_inverse=True)
    thin = np.empty((inverse.max() + 1, 2))
    for a in range(2):
        thin[:, a] = np.bincount(inverse, weights=out[:, a]) / np.bincount(inverse)
    return thin


def _interp(p1: Point, v1: float, p2: Point, v2: float, level: float) -> Point:
    t = 0.5 if v2 == v1 else (level - v1) / (v2 - v1)
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


def marching_squares(
    grid: np.ndarray, gx: np.ndarray, gy: np.ndarray, level: float
) -> list[np.ndarray]:
    """Contour polylines of grid[j, i] = f(gx[i], gy[j]) at one level.

    Classic 16-case cell walk with linear interpolation on crossing edges;
    saddle cells are disambiguated by the cell-center value. Segments are
    chained into polylines by matching endpoints.
    """
    segs: list[tuple[Point, Point]] = []
    for j in range(grid.shape[0] - 1):
        y0, y1 = gy[j], gy[j + 1]
        for i in range(grid.shape[1] - 1):
            v00, v10 = grid[j, i], grid[j, i + 1]
            v01, v11 = grid[j + 1, i], grid[j + 1, i + 1]
            case = (v00 >= level) | (v10 >= level) << 1 | (v11 >= level) << 2 | (v01 >= level) << 3
            if case in (0, 15):
                continue
            x0, x1 = gx[i], gx[i + 1]
            S = _interp((x0, y0), v00, (x1, y0), v10, level)
            N = _interp((x0, y1), v01, (x1, y1), v11, level)
            W = _interp((x0, y0), v00, (x0, y1), v01, level)
            E = _interp((x1, y0), v10, (x1, y1), v11, level)
            table = {
                1: [(W, S)],
                2: [(S, E)],
                3: [(W, E)],
                4: [(E, N)],
                6: [(S, N)],
                7: [(W, N)],
                8: [(N, W)],
                9: [(S, N)],
                11: [(E, N)],
                12: [(W, E)],
                13: [(S, E)],
                14: [(W, S)],
            }
            if case in (5, 10):
                center = (v00 + v10 + v01 + v11) / 4 >= level
                if case == 5:
                    pairs = [(W, N), (S, E)] if center else [(W, S), (E, N)]
                else:
                    pairs = [(W, S), (E, N)] if center else [(S, E), (N, W)]
            else:
                pairs = table[case]
            segs.extend(pairs)
    return _chain_segments(segs)


def _chain_segments(segs: list[tuple[Point, Point]]) -> list[np.ndarray]:
    key = lambda p: (round(p[0], 7), round(p[1], 7))
    adj: dict[Point, list[int]] = {}
    for k, (p, q) in enumerate(segs):
        adj.setdefault(key(p), []).append(k)
        adj.setdefault(key(q), []).append(k)
    used = np.zeros(len(segs), bool)
    paths = []
    for start in range(len(segs)):
        if used[start]:
            continue
        used[start] = True
        path = list(segs[start])
        for end in (1, 0):  # extend tail, then head
            while True:
                tip = path[-1] if end else path[0]
                nxt = next((k for k in adj.get(key(tip), []) if not used[k]), None)
                if nxt is None:
                    break
                used[nxt] = True
                p, q = segs[nxt]
                point = q if key(p) == key(tip) else p
                path.append(point) if end else path.insert(0, point)
        paths.append(np.asarray(path))
    return paths


def _chain_points(points: np.ndarray, link: float | None = None) -> list[np.ndarray]:
    """Greedy nearest-neighbor chaining of unordered ridge points into
    polylines: start at low-degree points (ridge endpoints), hop to the
    nearest unvisited neighbor within the link radius."""
    if len(points) < 4:
        return []
    d2 = ((points[:, None, :] - points[None, :, :]) ** 2).sum(-1)
    np.fill_diagonal(d2, np.inf)
    if link is None:
        link = 2.5 * float(np.median(np.sqrt(d2.min(1))))
    adj = d2 <= link * link
    visited = np.zeros(len(points), bool)
    chains = []
    for s in np.argsort(adj.sum(1)):
        if visited[s]:
            continue
        visited[s] = True
        chain = [int(s)]
        for end in (1, 0):
            while True:
                tip = chain[-1] if end else chain[0]
                cands = np.flatnonzero(adj[tip] & ~visited)
                if not len(cands):
                    break
                nxt = int(cands[np.argmin(d2[tip, cands])])
                visited[nxt] = True
                chain.append(nxt) if end else chain.insert(0, nxt)
        if len(chain) >= 4:
            chains.append(points[chain])
    return chains


def _smooth(path: np.ndarray) -> np.ndarray:
    if len(path) < 3:
        return path
    out = path.copy()
    out[1:-1] = (path[:-2] + path[1:-1] + path[2:]) / 3
    return out


# Dense, evenly spaced slicing: the stacked contour rings double as the
# relief surface in 3D, so many thin slices beat few thick ones.
_LEVEL_FRACS = tuple(round(f, 3) for f in np.linspace(0.06, 0.92, 12))
_GRID_STRIDE = 2  # payload height grid downsample vs the eval grid


def terrain(xy: np.ndarray, grid_n: int = 140, max_seeds: int = 2400) -> dict:
    """Full terrain payload for one 2D layout: contour polylines at fixed
    fractions of the density peak, SCMS ridge polylines with per-vertex
    normalized height, and a downsampled normalized height grid (for the
    relief view and for lifting points onto the surface). Plain-JSON types
    only; coordinates rounded to 3 decimals."""
    pts = np.asarray(xy, float)
    h = silverman_bandwidth(pts)
    pad = 2 * h
    gx = np.linspace(pts[:, 0].min() - pad, pts[:, 0].max() + pad, grid_n)
    gy = np.linspace(pts[:, 1].min() - pad, pts[:, 1].max() + pad, grid_n)
    grid = kde_grid(pts, h, gx, gy)
    top = float(grid.max())
    levels = [top * frac for frac in _LEVEL_FRACS]

    contours = []
    for lv, level in enumerate(levels):
        for path in marching_squares(grid, gx, gy, level):
            if len(path) < 5:
                continue
            contours.append(
                {"lv": lv, "path": [[round(float(x), 3), round(float(y), 3)] for x, y in path]}
            )

    xs, ys = np.meshgrid(gx, gy)
    mask = grid >= 0.06 * top
    seeds = np.column_stack([xs[mask], ys[mask]])
    if len(seeds) > max_seeds:
        seeds = seeds[:: len(seeds) // max_seeds + 1]
    ridge_points = scms(pts, h, seeds)
    ridges = []
    for chain in _chain_points(ridge_points):
        smoothed = _smooth(chain)
        heights = kde(pts, h, smoothed) / top
        ridges.append(
            [
                [round(float(x), 3), round(float(y), 3), round(float(z), 3)]
                for (x, y), z in zip(smoothed, heights)
            ]
        )

    gz = grid[::_GRID_STRIDE, ::_GRID_STRIDE] / top
    sgx, sgy = gx[::_GRID_STRIDE], gy[::_GRID_STRIDE]
    return {
        "h": round(h, 4),
        "levels": [round(lv, 6) for lv in levels],
        "fracs": list(_LEVEL_FRACS),
        "contours": contours,
        "ridges": ridges,
        "grid": {
            "x0": round(float(sgx[0]), 4),
            "x1": round(float(sgx[-1]), 4),
            "y0": round(float(sgy[0]), 4),
            "y1": round(float(sgy[-1]), 4),
            "nx": len(sgx),
            "ny": len(sgy),
            "z": [round(float(v), 3) for v in gz.ravel()],
        },
    }


def eigh3(mats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Closed-form eigenvalues of symmetric 3x3 matrices, batched, ascending,
    plus the eigenvector of the LARGEST eigenvalue only.

    Eigenvalues come from the trigonometric form of Cardano's cubic solution:
    shift by the trace mean, scale to unit Frobenius spread, and the
    characteristic cubic collapses to 4c^3 - 3c = det(B), solved by three
    cosines. SCMS in 3D only needs the top eigenvector (the along-filament
    direction) — the projection subspace is its orthogonal complement, which
    sidesteps the degeneracy of separating the two most-negative directions.
    The eigenvector comes from cross products of rows of (A - lambda I): any
    two independent rows are both orthogonal to v, so their cross product IS v.
    """
    a = np.asarray(mats, float)
    a00, a11, a22 = a[..., 0, 0], a[..., 1, 1], a[..., 2, 2]
    a01, a02, a12 = a[..., 0, 1], a[..., 0, 2], a[..., 1, 2]
    q = (a00 + a11 + a22) / 3
    p1 = a01**2 + a02**2 + a12**2
    p2 = (a00 - q) ** 2 + (a11 - q) ** 2 + (a22 - q) ** 2 + 2 * p1
    p = np.sqrt(np.maximum(p2, 0) / 6)
    ps = np.where(p > 1e-30, p, 1.0)
    B = (a - q[..., None, None] * np.eye(3)) / ps[..., None, None]
    detB = (
        B[..., 0, 0] * (B[..., 1, 1] * B[..., 2, 2] - B[..., 1, 2] * B[..., 2, 1])
        - B[..., 0, 1] * (B[..., 1, 0] * B[..., 2, 2] - B[..., 1, 2] * B[..., 2, 0])
        + B[..., 0, 2] * (B[..., 1, 0] * B[..., 2, 1] - B[..., 1, 1] * B[..., 2, 0])
    )
    phi = np.arccos(np.clip(detB / 2, -1.0, 1.0)) / 3
    e_hi = q + 2 * p * np.cos(phi)
    e_lo = q + 2 * p * np.cos(phi + 2 * np.pi / 3)
    e_mid = 3 * q - e_hi - e_lo
    vals = np.stack([e_lo, e_mid, e_hi], axis=-1)
    C = a - e_hi[..., None, None] * np.eye(3)
    cands = np.stack(
        [
            np.cross(C[..., 0, :], C[..., 1, :]),
            np.cross(C[..., 0, :], C[..., 2, :]),
            np.cross(C[..., 1, :], C[..., 2, :]),
        ],
        axis=-2,
    )
    norms = np.linalg.norm(cands, axis=-1)
    best = norms.argmax(axis=-1)
    v = np.take_along_axis(cands, best[..., None, None], axis=-2)[..., 0, :]
    vn = np.linalg.norm(v, axis=-1, keepdims=True)
    v = np.where(vn > 1e-12, v / vn.clip(1e-300), np.array([1.0, 0.0, 0.0]))
    return vals, v


def scms3(
    pts: np.ndarray,
    h: Bandwidth,
    seeds: np.ndarray,
    max_iter: int = 100,
    tol: float = 1e-4,
    floor_frac: float = 0.05,
) -> np.ndarray:
    """SCMS in 3D: each walker deletes the along-filament component (the top
    Hessian eigenvector) from its mean-shift step, so it can only move within
    its cross-sectional disk — sliding onto the filament centerline and
    stopping there. Valid filament points have both cross-disk curvatures
    negative and density above the floor."""
    pts = np.asarray(pts, float)
    x = np.array(seeds, float, copy=True)
    href = float(np.max(np.broadcast_to(np.asarray(h, float), (len(pts),))))
    lo = pts.min(0) - 3 * href
    hi = pts.max(0) + 3 * href
    floor = floor_frac * kde(pts, h, pts).max()
    keep = np.ones(len(x), bool)
    active = np.ones(len(x), bool)
    for _ in range(max_iter):
        idx = np.flatnonzero(active)
        if not len(idx):
            break
        f, grad, hess, scale = log_density_grad_hess(pts, h, x[idx], return_scale=True)
        _, v1 = eigh3(hess)
        ms = grad * scale[:, None]  # natural mean-shift step (h^2 when uniform)
        step = ms - (ms * v1).sum(1, keepdims=True) * v1
        x[idx] = np.clip(x[idx] + step, lo, hi)
        low = f < floor
        keep[idx[low]] = False
        done = (np.linalg.norm(step, axis=1) < tol) | low
        active[idx[done]] = False
    keep &= ~active
    idx = np.flatnonzero(keep)
    if not len(idx):
        return np.empty((0, 3))
    f, _, hess = log_density_grad_hess(pts, h, x[idx])
    vals, _ = eigh3(hess)
    ok = (vals[:, 0] < 0) & (vals[:, 1] < 0) & (f >= floor)
    out = x[idx[ok]]
    if not len(out):
        return out
    _, inverse = np.unique(np.round(out, 2), axis=0, return_inverse=True)
    thin = np.empty((inverse.max() + 1, 3))
    for axis in range(3):
        thin[:, axis] = np.bincount(inverse, weights=out[:, axis]) / np.bincount(inverse)
    return thin


def _majority_label(
    pts: np.ndarray, h: Bandwidth, verts: np.ndarray, labels: np.ndarray, n_labels: int
) -> np.ndarray:
    """Kernel-weighted vote: each filament vertex takes the label whose
    points contribute the most fog at that spot (same adaptive weights as
    the density). Unlabeled points (-1) vote in their own bucket; a vertex
    they win stays -1."""
    pts = np.asarray(pts, float)
    labels = np.asarray(labels)
    hs = np.broadcast_to(np.asarray(h, float), (len(pts),))
    inv2h2 = 1.0 / (2 * hs * hs)
    knorm = (2 * np.pi * hs * hs) ** (pts.shape[1] / 2)
    slot = np.where(labels >= 0, labels, n_labels)
    onehot = np.zeros((len(labels), n_labels + 1))
    onehot[np.arange(len(labels)), slot] = 1.0
    votes = np.empty((len(verts), n_labels + 1))
    for s in range(0, len(verts), _CHUNK):
        q = verts[s : s + _CHUNK]
        d2 = ((q[:, None, :] - pts[None, :, :]) ** 2).sum(-1)
        votes[s : s + _CHUNK] = (np.exp(-d2 * inv2h2) / knorm) @ onehot
    best = votes.argmax(1)
    return np.where(best == n_labels, -1, best)


def fog(xyz: np.ndarray, n_samples: int = 6000, jitter: float = 1.6, seed: int = 7) -> dict:
    """Monte-Carlo fog: soft samples of the 3D density field for direct
    splat rendering.

    Importance sampling instead of a lattice: each sample position is a
    random data point jittered by jitter*h, so samples land where fog
    exists and empty space costs nothing. Each splat carries the exact
    density at its spot, normalized so the peak over the data is 1.0.
    The seed is fixed: rebuilding the map must not reshuffle the cloud.
    """
    pts = np.asarray(xyz, float)
    hi = knn_bandwidths(pts)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(pts), n_samples)
    # Each sample jitters by ITS center's bandwidth: lonely notes scatter
    # their samples wide, dense cores keep theirs tight — the sampling
    # cloud matches the adaptive fog it measures.
    samples = pts[idx] + rng.normal(0, 1, (n_samples, pts.shape[1])) * (jitter * hi[idx])[:, None]
    # Display normalization against the splats' own 99th percentile: the
    # brightest ~1% of drawn samples saturate at 1.0 and the rest spread
    # over the range. Normalizing against densities AT the data points
    # fails (points sit on local peaks, samples hover off-peak, everything
    # compresses into darkness — caught by the matplotlib witness).
    raw = kde(pts, hi, samples)
    dens = np.minimum(raw / np.percentile(raw, 99), 1.0)
    keep = dens >= 0.01
    return {
        "h": round(float(np.median(hi)), 4),
        "splats": [
            [
                round(float(x), 3),
                round(float(y), 3),
                round(float(z), 3),
                round(float(min(v, 1.0)), 3),
            ]
            for (x, y, z), v in zip(samples[keep], dens[keep])
        ],
    }


def trace_filaments(
    pts: np.ndarray,
    h: Bandwidth,
    ridge_points: np.ndarray,
    step_frac: float = 0.4,
    max_steps: int = 400,
    floor_frac: float = 0.05,
    min_len: int = 6,
    seed_sep_steps: float = 4.0,
    dedupe: bool = True,
) -> list[np.ndarray]:
    """Predictor-corrector ridge tracing, batched: every strand front
    advances in lockstep, one vectorized gradient/Hessian call per
    corrector iteration (the sequential version paid Python overhead per
    front per step).

    Predictor: step 0.4h along the ridge tangent (top Hessian eigenvector,
    sign-continuous so a walk never doubles back). Corrector: 8 lockstep
    sideways-only SCMS iterations snap all fronts back onto their crests.
    A front dies when its density drops below the floor, its cross-disk
    curvature stops being negative (the ridge genuinely ends), or the
    corrector pulls its step back. Seeds are density-ordered crest points
    thinned to a minimum separation; every seed walks both directions;
    afterwards a strand mostly covered by longer kept strands is dropped —
    it is the same strand traced from another doorway.

    dedupe=False returns the raw overlapping walks (what the skeleton looks
    like before trimming) so the comparison figure stays reproducible."""
    pts = np.asarray(pts, float)
    ridge_points = np.asarray(ridge_points, float)
    if not len(ridge_points):
        return []
    href = float(np.median(np.broadcast_to(np.asarray(h, float), (len(pts),))))
    step = step_frac * href
    floor = floor_frac * kde(pts, h, pts).max()

    def crest_batch(x0: np.ndarray) -> tuple[np.ndarray, ...]:
        """Batched corrector + final ridge state for every row of x0."""
        x = np.array(x0, float)
        for _ in range(8):
            _, grad, hess, scale = log_density_grad_hess(pts, h, x, return_scale=True)
            _, v1 = eigh3(hess)
            ms = grad * scale[:, None]
            x = x + ms - (ms * v1).sum(1, keepdims=True) * v1
        f, _, hess = log_density_grad_hess(pts, h, x)
        vals, v1 = eigh3(hess)
        return x, f, vals, v1

    # density-ordered greedy seed thinning: one seed per seed_sep_steps
    # worth of crest, densest first
    f_r = kde(pts, h, ridge_points)
    sep2 = (seed_sep_steps * step) ** 2
    chosen: list[np.ndarray] = []
    for si in np.argsort(-f_r):
        p = ridge_points[si]
        if not chosen or (((np.asarray(chosen) - p) ** 2).sum(1) > sep2).all():
            chosen.append(p)
    seeds, f0, vals0, v10 = crest_batch(np.asarray(chosen))
    ok = (f0 >= floor) & (vals0[:, 1] < 0)
    seeds, tangents = seeds[ok], v10[ok]
    m = len(seeds)
    if not m:
        return []

    # two fronts per seed (rows [0, m) forward, [m, 2m) backward), lockstep
    x = np.vstack([seeds, seeds])
    t = np.vstack([tangents, -tangents])
    active = np.ones(2 * m, bool)
    trails: list[list[np.ndarray]] = [[] for _ in range(2 * m)]
    for _ in range(max_steps):
        idx = np.flatnonzero(active)
        if not len(idx):
            break
        new_x, f, vals, v1 = crest_batch(x[idx] + step * t[idx])
        moved = new_x - x[idx]
        norm = np.linalg.norm(moved, axis=1)
        alive = (f >= floor) & (vals[:, 1] < 0) & (norm >= 0.25 * step)
        active[idx[~alive]] = False
        live = idx[alive]
        v_live, m_live = v1[alive], moved[alive]
        flip = (v_live * m_live).sum(1) < 0
        t[live] = np.where(flip[:, None], -v_live, v_live)
        x[live] = new_x[alive]
        for row, xi in zip(live, new_x[alive]):
            trails[row].append(xi)

    strands = []
    for i in range(m):
        walk = trails[m + i][::-1] + [seeds[i]] + trails[i]
        if len(walk) >= min_len:
            strands.append(np.asarray(walk))
    if not dedupe:
        return strands  # raw overlapping walks (forensics; see asset 07)
    # Dedupe by TRIMMING, longest first: drop only the stretches already
    # covered by kept strands and keep every uncovered contiguous run long
    # enough to stand alone. Whole-strand dropping would eat branches,
    # whose walks legitimately merge into the main strand at junctions.
    strands.sort(key=len, reverse=True)
    kept: list[np.ndarray] = []
    claim2 = (2.5 * step) ** 2
    for strand in strands:
        if kept:
            cloud = np.vstack(kept)
            d2 = ((strand[:, None, :] - cloud[None, :, :]) ** 2).sum(-1).min(1)
            uncovered = d2 > claim2
        else:
            uncovered = np.ones(len(strand), bool)
        run_start = None
        for j, u in enumerate(list(uncovered) + [False]):
            if u and run_start is None:
                run_start = j
            elif not u and run_start is not None:
                if j - run_start >= min_len:
                    # extend one vertex into covered territory on each side
                    # so a branch visually touches the strand it joins
                    kept.append(strand[max(0, run_start - 1) : min(len(strand), j + 1)])
                run_start = None
    return kept


def web(xyz: np.ndarray, labels: list, n_labels: int, max_seeds: int = 2500) -> dict:
    """Filament skeleton of a 3D embedding: SCMS curves through the point
    fog, seeded from the points themselves, each vertex tagged with the
    kernel-weighted majority label (domain or theme) of the notes holding it
    up. Plain-JSON payload; vertices are [x, y, z, label].

    Deliberately UNIFORM bandwidth, unlike the fog: measured 2026-07-24,
    adaptive h_i (even mildly clamped) fragments the long connective
    threads (longest chain 89 -> ~30) because sharper local density means
    more textured crests. The web answers a connectivity question, which
    wants more smoothing; the fog answers a local-thickness question,
    which wants adaptivity. docs/assets/01-fog/04-*.png is the record."""
    pts = np.asarray(xyz, float)
    h = silverman_bandwidth(pts)
    seeds = pts
    if len(seeds) > max_seeds:
        seeds = seeds[:: len(seeds) // max_seeds + 1]
    ridge_points = scms3(pts, h, seeds)
    top = kde(pts, h, pts).max()
    strands = trace_filaments(pts, h, ridge_points)
    # Junctions: a strand endpoint sitting on another strand's interior is,
    # by construction of the trim-dedupe, the point where a branch was cut
    # and re-extended to touch its trunk — the crossroads of the web.
    join = 2.5 * 0.4 * h
    raw_junctions = []
    for i, strand in enumerate(strands):
        others = [s for j, s in enumerate(strands) if j != i]
        if not others:
            break
        cloud = np.vstack(others)
        for end in (strand[0], strand[-1]):
            if np.sqrt(((cloud - end) ** 2).sum(1).min()) <= join:
                raw_junctions.append(end)
    junctions: list[np.ndarray] = []
    for p in raw_junctions:  # merge junction pairs found from both sides
        if not junctions or (((np.asarray(junctions) - p) ** 2).sum(1) > join * join).all():
            junctions.append(p)
    filaments = []
    for strand in strands:
        smoothed = _smooth(strand)
        labs = _majority_label(pts, h, smoothed, np.asarray(labels), n_labels)
        dens = np.minimum(kde(pts, h, smoothed) / top, 1.0)
        filaments.append(
            [
                [
                    round(float(x), 3),
                    round(float(y), 3),
                    round(float(z), 3),
                    int(lab),
                    round(float(v), 3),
                ]
                for (x, y, z), lab, v in zip(smoothed, labs, dens)
            ]
        )
    return {
        "h": round(h, 4),
        "filaments": filaments,
        "junctions": [
            [round(float(x), 3), round(float(y), 3), round(float(z), 3)] for x, y, z in junctions
        ],
    }
