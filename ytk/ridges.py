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

import numpy as np

_CHUNK = 256  # query rows per block; bounds the (m, n, 2) intermediates


def silverman_bandwidth(pts: np.ndarray) -> float:
    """Rule of thumb in d dims: h = sigma * n^(-1/(d+4)), sigma averaged
    across axes (d=2 gives the familiar n^(-1/6))."""
    pts = np.asarray(pts, float)
    d = pts.shape[1]
    sigma = float(pts.std(axis=0, ddof=1).mean())
    return sigma * len(pts) ** (-1 / (d + 4))


def kde(pts: np.ndarray, h: float, query: np.ndarray) -> np.ndarray:
    """f(x) = (1/n) sum_i N(x; x_i, h^2 I) evaluated at query rows.
    Dimension-agnostic: the kernel normalization is (2 pi h^2)^(d/2)."""
    pts = np.asarray(pts, float)
    query = np.asarray(query, float)
    out = np.empty(len(query))
    norm = len(pts) * (2 * np.pi * h * h) ** (pts.shape[1] / 2)
    for s in range(0, len(query), _CHUNK):
        q = query[s : s + _CHUNK]
        d2 = ((q[:, None, :] - pts[None, :, :]) ** 2).sum(-1)
        out[s : s + _CHUNK] = np.exp(-d2 / (2 * h * h)).sum(1) / norm
    return out


def kde_grid(pts: np.ndarray, h: float, gx: np.ndarray, gy: np.ndarray) -> np.ndarray:
    """Density on a regular grid; grid[j, i] = f(gx[i], gy[j])."""
    out = np.empty((len(gy), len(gx)))
    for j, y in enumerate(gy):
        q = np.column_stack([gx, np.full(len(gx), y)])
        out[j] = kde(pts, h, q)
    return out


def log_density_grad_hess(
    pts: np.ndarray, h: float, x: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Density f, gradient and Hessian of log f, batched over query rows.

    With w_i = exp(-|x - x_i|^2 / 2h^2), W = sum w_i and
    m = sum w_i (x_i - x) / W (the mean-shift vector):

        grad log f = m / h^2
        hess log f = (S - m m^T) / h^4 - I / h^2,  S = sum w_i d_i d_i^T / W

    where d_i = x_i - x. Verified against finite differences in tests.
    """
    pts = np.asarray(pts, float)
    x = np.asarray(x, float)
    n, d = pts.shape
    f = np.empty(len(x))
    grad = np.empty((len(x), d))
    hess = np.empty((len(x), d, d))
    eye = np.eye(d)
    norm = n * (2 * np.pi * h * h) ** (d / 2)
    for s in range(0, len(x), _CHUNK):
        q = x[s : s + _CHUNK]
        diff = pts[None, :, :] - q[:, None, :]  # (m, n, d) = x_i - x
        w = np.exp(-(diff**2).sum(-1) / (2 * h * h))  # (m, n)
        W = w.sum(1).clip(1e-300)
        m = (w[:, :, None] * diff).sum(1) / W[:, None]
        S = np.einsum("mn,mna,mnb->mab", w, diff, diff) / W[:, None, None]
        f[s : s + _CHUNK] = W / norm
        grad[s : s + _CHUNK] = m / h**2
        hess[s : s + _CHUNK] = (S - m[:, :, None] * m[:, None, :]) / h**4 - eye / h**2
    return f, grad, hess


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
    h: float,
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
    lo = pts.min(0) - 3 * h
    hi = pts.max(0) + 3 * h
    floor = floor_frac * kde(pts, h, pts).max()
    keep = np.ones(len(x), bool)
    active = np.ones(len(x), bool)
    for _ in range(max_iter):
        idx = np.flatnonzero(active)
        if not len(idx):
            break
        f, grad, hess = log_density_grad_hess(pts, h, x[idx])
        _, vecs = eigh2(hess)
        v2 = vecs[:, :, 0]
        ms = grad * h * h  # mean-shift vector m(x) = h^2 grad log f
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


def _interp(p1: tuple, v1: float, p2: tuple, v2: float, level: float) -> tuple:
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
    segs: list[tuple[tuple, tuple]] = []
    for j in range(grid.shape[0] - 1):
        y0, y1 = gy[j], gy[j + 1]
        for i in range(grid.shape[1] - 1):
            v00, v10 = grid[j, i], grid[j, i + 1]
            v01, v11 = grid[j + 1, i], grid[j + 1, i + 1]
            case = (
                (v00 >= level)
                | (v10 >= level) << 1
                | (v11 >= level) << 2
                | (v01 >= level) << 3
            )
            if case in (0, 15):
                continue
            x0, x1 = gx[i], gx[i + 1]
            S = _interp((x0, y0), v00, (x1, y0), v10, level)
            N = _interp((x0, y1), v01, (x1, y1), v11, level)
            W = _interp((x0, y0), v00, (x0, y1), v01, level)
            E = _interp((x1, y0), v10, (x1, y1), v11, level)
            table = {
                1: [(W, S)], 2: [(S, E)], 3: [(W, E)], 4: [(E, N)],
                6: [(S, N)], 7: [(W, N)], 8: [(N, W)], 9: [(S, N)],
                11: [(E, N)], 12: [(W, E)], 13: [(S, E)], 14: [(W, S)],
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


def _chain_segments(segs: list[tuple[tuple, tuple]]) -> list[np.ndarray]:
    key = lambda p: (round(p[0], 7), round(p[1], 7))
    adj: dict[tuple, list[int]] = {}
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
    h: float,
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
    lo = pts.min(0) - 3 * h
    hi = pts.max(0) + 3 * h
    floor = floor_frac * kde(pts, h, pts).max()
    keep = np.ones(len(x), bool)
    active = np.ones(len(x), bool)
    for _ in range(max_iter):
        idx = np.flatnonzero(active)
        if not len(idx):
            break
        f, grad, hess = log_density_grad_hess(pts, h, x[idx])
        _, v1 = eigh3(hess)
        ms = grad * h * h
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
    pts: np.ndarray, h: float, verts: np.ndarray, labels: np.ndarray, n_labels: int
) -> np.ndarray:
    """Kernel-weighted vote: each filament vertex takes the label whose
    points contribute the most fog at that spot. Unlabeled points (-1) vote
    in their own bucket; a vertex they win stays -1."""
    labels = np.asarray(labels)
    slot = np.where(labels >= 0, labels, n_labels)
    onehot = np.zeros((len(labels), n_labels + 1))
    onehot[np.arange(len(labels)), slot] = 1.0
    votes = np.empty((len(verts), n_labels + 1))
    for s in range(0, len(verts), _CHUNK):
        q = verts[s : s + _CHUNK]
        d2 = ((q[:, None, :] - pts[None, :, :]) ** 2).sum(-1)
        votes[s : s + _CHUNK] = np.exp(-d2 / (2 * h * h)) @ onehot
    best = votes.argmax(1)
    return np.where(best == n_labels, -1, best)


def web(xyz: np.ndarray, labels: list, n_labels: int, max_seeds: int = 2500) -> dict:
    """Filament skeleton of a 3D embedding: SCMS curves through the point
    fog, seeded from the points themselves, each vertex tagged with the
    kernel-weighted majority label (domain or theme) of the notes holding it
    up. Plain-JSON payload; vertices are [x, y, z, label]."""
    pts = np.asarray(xyz, float)
    h = silverman_bandwidth(pts)
    seeds = pts
    if len(seeds) > max_seeds:
        seeds = seeds[:: len(seeds) // max_seeds + 1]
    ridge_points = scms3(pts, h, seeds)
    filaments = []
    for chain in _chain_points(ridge_points):
        smoothed = _smooth(chain)
        labs = _majority_label(pts, h, smoothed, np.asarray(labels), n_labels)
        filaments.append(
            [
                [round(float(x), 3), round(float(y), 3), round(float(z), 3), int(lab)]
                for (x, y, z), lab in zip(smoothed, labs)
            ]
        )
    return {"h": round(h, 4), "filaments": filaments}
