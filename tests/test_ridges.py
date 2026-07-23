"""Math-core tests for the density terrain (ytk/ridges.py).

The analytic gradient/Hessian are checked against central finite
differences — the ground truth for the hand-derived calculus. SCMS is
checked on synthetic data with known ridge geometry.
"""

import numpy as np
import pytest

from ytk import ridges


def _blob(n, center, sd, seed):
    rng = np.random.default_rng(seed)
    return rng.normal(center, sd, size=(n, 2))


def test_silverman_bandwidth_scales_down_with_n():
    small = ridges.silverman_bandwidth(_blob(50, (0, 0), 1.0, 1))
    large = ridges.silverman_bandwidth(_blob(5000, (0, 0), 1.0, 1))
    assert 0 < large < small


def test_kde_matches_naive_sum():
    pts = _blob(40, (0.2, -0.1), 0.5, 2)
    h = 0.3
    query = np.array([[0.0, 0.0], [0.4, 0.4], [-1.0, 2.0]])
    f = ridges.kde(pts, h, query)
    for k, q in enumerate(query):
        naive = np.exp(-((pts - q) ** 2).sum(1) / (2 * h * h)).sum()
        naive /= len(pts) * 2 * np.pi * h * h
        assert f[k] == pytest.approx(naive, rel=1e-10)


def test_kde_integrates_to_one():
    pts = _blob(120, (0, 0), 0.4, 3)
    h = 0.25
    gx = np.linspace(-3, 3, 241)
    gy = np.linspace(-3, 3, 241)
    grid = ridges.kde_grid(pts, h, gx, gy)
    step = gx[1] - gx[0]
    assert grid.sum() * step * step == pytest.approx(1.0, abs=1e-3)


def test_grad_hess_match_finite_differences():
    pts = _blob(60, (0.1, 0.3), 0.6, 4)
    h = 0.35
    eps = 1e-5
    queries = np.array([[0.0, 0.0], [0.5, -0.2], [-0.4, 0.6], [0.9, 0.9]])
    _, grad, hess = ridges.log_density_grad_hess(pts, h, queries)

    def logf(q):
        return float(np.log(ridges.kde(pts, h, q[None, :])[0]))

    for k, q in enumerate(queries):
        for a in range(2):
            e = np.zeros(2)
            e[a] = eps
            fd = (logf(q + e) - logf(q - e)) / (2 * eps)
            assert grad[k, a] == pytest.approx(fd, rel=1e-4, abs=1e-6)
            for b in range(2):
                e2 = np.zeros(2)
                e2[b] = eps
                fd2 = (
                    logf(q + e + e2) - logf(q + e - e2)
                    - logf(q - e + e2) + logf(q - e - e2)
                ) / (4 * eps * eps)
                assert hess[k, a, b] == pytest.approx(fd2, rel=1e-3, abs=1e-4)


def test_gradient_points_toward_lone_blob():
    pts = _blob(200, (1.0, 0.0), 0.2, 5)
    h = 0.3
    _, grad, _ = ridges.log_density_grad_hess(pts, h, np.array([[0.0, 0.0]]))
    direction = grad[0] / np.linalg.norm(grad[0])
    assert direction[0] == pytest.approx(1.0, abs=0.1)


def test_eigh2_matches_numpy():
    rng = np.random.default_rng(6)
    m = rng.normal(size=(50, 2, 2))
    sym = (m + m.transpose(0, 2, 1)) / 2
    sym[7] = np.diag([2.0, -1.0])  # b == 0 branch
    sym[8] = np.eye(2) * 0.5       # isotropic branch
    vals, vecs = ridges.eigh2(sym)
    for k in range(len(sym)):
        ref_vals, ref_vecs = np.linalg.eigh(sym[k])
        assert vals[k] == pytest.approx(ref_vals, abs=1e-10)  # ascending
        for j in range(2):
            v, r = vecs[k, :, j], ref_vecs[:, j]
            assert abs(float(v @ r)) == pytest.approx(1.0, abs=1e-8)


def test_scms_finds_axis_ridge():
    # Points stretched along the x-axis: the density crest IS the x-axis.
    rng = np.random.default_rng(7)
    pts = np.column_stack([rng.uniform(-1, 1, 900), rng.normal(0, 0.08, 900)])
    h = ridges.silverman_bandwidth(pts)
    seeds = np.column_stack(
        [rng.uniform(-0.8, 0.8, 200), rng.uniform(-0.25, 0.25, 200)]
    )
    out = ridges.scms(pts, h, seeds)
    assert len(out) > 50
    assert np.abs(out[:, 1]).max() < 3 * h  # on the crest, not the slopes
    assert np.ptp(out[:, 0]) > 1.0         # spread along it, not at a mode


def test_marching_squares_circle():
    # Analytic isotropic Gaussian: the level set of f is an exact circle.
    h = 0.5
    gx = np.linspace(-2, 2, 201)
    gy = np.linspace(-2, 2, 201)
    xs, ys = np.meshgrid(gx, gy)
    grid = np.exp(-(xs**2 + ys**2) / (2 * h * h)) / (2 * np.pi * h * h)
    level = float(grid.max()) * 0.5
    radius = h * np.sqrt(2 * np.log(2))  # f(r) = f(0)/2
    paths = ridges.marching_squares(grid, gx, gy, level)
    verts = np.vstack(paths)
    assert len(paths) >= 1
    assert np.hypot(verts[:, 0], verts[:, 1]) == pytest.approx(
        np.full(len(verts), radius), abs=0.03
    )


def test_terrain_payload_shape_and_bounds():
    rng = np.random.default_rng(8)
    xy = np.vstack(
        [_blob(300, (-0.4, -0.3), 0.15, 9), _blob(300, (0.4, 0.35), 0.18, 10)]
    )
    xy = np.clip(xy, -1, 1)
    t = ridges.terrain(xy)
    assert set(t) == {"h", "levels", "contours", "ridges"}
    assert len(t["levels"]) == len(set(c["lv"] for c in t["contours"])) or t["contours"] == []
    for c in t["contours"]:
        assert 0 <= c["lv"] < len(t["levels"])
        arr = np.asarray(c["path"])
        assert arr.ndim == 2 and arr.shape[1] == 2
        assert np.abs(arr).max() < 1.6
    for r in t["ridges"]:
        arr = np.asarray(r)
        assert len(arr) >= 4
        assert np.abs(arr).max() < 1.6
    import json

    json.dumps(t)  # payload must be plain-JSON serializable
