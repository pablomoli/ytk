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


def _blob3(n, center, sd, seed):
    rng = np.random.default_rng(seed)
    return rng.normal(center, sd, size=(n, 3))


def test_kde_3d_matches_naive_sum():
    pts = _blob3(30, (0.1, -0.2, 0.3), 0.5, 11)
    h = 0.3
    query = np.array([[0.0, 0.0, 0.0], [0.4, -0.4, 0.2]])
    f = ridges.kde(pts, h, query)
    for k, q in enumerate(query):
        naive = np.exp(-((pts - q) ** 2).sum(1) / (2 * h * h)).sum()
        naive /= len(pts) * (2 * np.pi * h * h) ** 1.5
        assert f[k] == pytest.approx(naive, rel=1e-10)


def test_grad_hess_3d_match_finite_differences():
    pts = _blob3(50, (0.1, 0.2, -0.1), 0.6, 12)
    h = 0.35
    eps = 1e-5
    queries = np.array([[0.0, 0.0, 0.0], [0.4, -0.3, 0.5], [-0.5, 0.2, -0.4]])
    _, grad, hess = ridges.log_density_grad_hess(pts, h, queries)

    def logf(q):
        return float(np.log(ridges.kde(pts, h, q[None, :])[0]))

    for k, q in enumerate(queries):
        for a in range(3):
            e = np.zeros(3)
            e[a] = eps
            fd = (logf(q + e) - logf(q - e)) / (2 * eps)
            assert grad[k, a] == pytest.approx(fd, rel=1e-4, abs=1e-6)
            for b in range(3):
                e2 = np.zeros(3)
                e2[b] = eps
                fd2 = (
                    logf(q + e + e2) - logf(q + e - e2)
                    - logf(q - e + e2) + logf(q - e - e2)
                ) / (4 * eps * eps)
                assert hess[k, a, b] == pytest.approx(fd2, rel=1e-3, abs=1e-4)


def test_eigh3_matches_numpy():
    rng = np.random.default_rng(13)
    m = rng.normal(size=(60, 3, 3))
    sym = (m + m.transpose(0, 2, 1)) / 2
    sym[5] = np.diag([3.0, -1.0, 0.5])   # diagonal branch
    sym[6] = np.eye(3) * -0.7            # isotropic branch
    vals, v1 = ridges.eigh3(sym)
    for k in range(len(sym)):
        ref_vals, ref_vecs = np.linalg.eigh(sym[k])
        assert vals[k] == pytest.approx(ref_vals, abs=1e-8)  # ascending
        if ref_vals[2] - ref_vals[1] > 1e-6:  # top eigenvector well-defined
            assert abs(float(v1[k] @ ref_vecs[:, 2])) == pytest.approx(1.0, abs=1e-6)


def test_scms3_finds_axis_filament():
    # Points strung along the x-axis in 3D: the filament IS the x-axis.
    rng = np.random.default_rng(14)
    pts = np.column_stack(
        [rng.uniform(-1, 1, 900), rng.normal(0, 0.08, 900), rng.normal(0, 0.08, 900)]
    )
    h = ridges.silverman_bandwidth(pts)
    seeds = pts[::3]
    out = ridges.scms3(pts, h, seeds)
    assert len(out) > 40
    assert np.hypot(out[:, 1], out[:, 2]).max() < 3 * h  # on the wire
    assert np.ptp(out[:, 0]) > 1.0                       # spread along it


def test_web_payload_shape():
    xyz = np.vstack(
        [_blob3(250, (-0.4, 0.0, 0.1), 0.15, 15), _blob3(250, (0.4, 0.1, -0.2), 0.15, 16)]
    )
    labels = [0] * 250 + [1] * 250
    t = ridges.web(xyz, labels, 2)
    assert set(t) == {"h", "filaments"}
    for fil in t["filaments"]:
        arr = np.asarray(fil)
        assert len(arr) >= 4
        assert arr.shape[1] == 4                     # x, y, z, label
        assert np.all((arr[:, 3] >= -1) & (arr[:, 3] < 2))
    import json

    json.dumps(t)


def test_knn_bandwidths_widen_in_sparse_regions():
    rng = np.random.default_rng(20)
    dense = _blob3(400, (0, 0, 0), 0.08, 21)
    sparse = rng.uniform(0.5, 1.0, size=(40, 3))
    pts = np.vstack([dense, sparse])
    h = ridges.silverman_bandwidth(pts)
    hi = ridges.knn_bandwidths(pts)
    assert hi.shape == (len(pts),)
    assert np.median(hi[400:]) > 2 * np.median(hi[:400])  # lonely notes cast wide fog
    assert hi.min() >= 0.5 * h - 1e-12 and hi.max() <= 3.0 * h + 1e-12  # clamped
    assert np.median(hi) == pytest.approx(h, rel=0.35)     # anchored near Silverman


def test_kde_accepts_per_point_bandwidths():
    pts = _blob3(30, (0, 0, 0), 0.4, 22)
    rng = np.random.default_rng(23)
    hi = rng.uniform(0.2, 0.5, len(pts))
    query = np.array([[0.1, -0.1, 0.2], [0.5, 0.5, -0.3]])
    f = ridges.kde(pts, hi, query)
    for j, q in enumerate(query):
        d2 = ((pts - q) ** 2).sum(1)
        naive = (np.exp(-d2 / (2 * hi * hi)) / (2 * np.pi * hi * hi) ** 1.5).sum() / len(pts)
        assert f[j] == pytest.approx(naive, rel=1e-10)
    scalar = ridges.kde(pts, 0.3, query)
    uniform = ridges.kde(pts, np.full(len(pts), 0.3), query)
    assert scalar == pytest.approx(uniform)  # scalar path unchanged


def test_adaptive_grad_hess_match_finite_differences():
    # The adaptive Hessian is the easiest place to silently drop a term:
    # every kernel carries its own width AND normalization, so the clean
    # m/h^2 identities pick up per-point weights. Finite differences are
    # the referee, exactly as for the uniform case.
    pts = _blob3(40, (0.1, 0.0, -0.2), 0.5, 24)
    rng = np.random.default_rng(25)
    hi = rng.uniform(0.2, 0.5, len(pts))
    eps = 1e-5
    queries = np.array([[0.0, 0.0, 0.0], [0.4, -0.2, 0.3], [-0.3, 0.5, -0.4]])
    _, grad, hess = ridges.log_density_grad_hess(pts, hi, queries)

    def logf(q):
        return float(np.log(ridges.kde(pts, hi, q[None, :])[0]))

    for k, q in enumerate(queries):
        for a in range(3):
            e = np.zeros(3)
            e[a] = eps
            fd = (logf(q + e) - logf(q - e)) / (2 * eps)
            assert grad[k, a] == pytest.approx(fd, rel=1e-4, abs=1e-6)
            for b in range(3):
                e2 = np.zeros(3)
                e2[b] = eps
                fd2 = (
                    logf(q + e + e2) - logf(q + e - e2)
                    - logf(q - e + e2) + logf(q - e - e2)
                ) / (4 * eps * eps)
                assert hess[k, a, b] == pytest.approx(fd2, rel=1e-3, abs=1e-4)


def test_adaptive_grad_hess_reduce_to_uniform():
    pts = _blob3(50, (0, 0, 0), 0.4, 26)
    x = np.array([[0.2, -0.1, 0.3], [0.5, 0.5, -0.5]])
    f_s, g_s, h_s = ridges.log_density_grad_hess(pts, 0.3, x)
    f_v, g_v, h_v = ridges.log_density_grad_hess(pts, np.full(len(pts), 0.3), x)
    assert f_s == pytest.approx(f_v)
    assert g_s == pytest.approx(g_v)
    assert h_s == pytest.approx(h_v)


def test_scms3_adaptive_finds_axis_filament():
    # Density varies along the wire (points thin out toward +x) — the
    # regime adaptive bandwidths exist for. The crest must still be found.
    rng = np.random.default_rng(27)
    xs = -1 + 2 * rng.power(2.0, 900)  # denser near +1, sparse near -1
    pts = np.column_stack([xs, rng.normal(0, 0.08, 900), rng.normal(0, 0.08, 900)])
    hi = ridges.knn_bandwidths(pts)
    seeds = pts[::3]
    out = ridges.scms3(pts, hi, seeds)
    assert len(out) > 40
    assert np.hypot(out[:, 1], out[:, 2]).max() < 3 * ridges.silverman_bandwidth(pts)
    assert np.ptp(out[:, 0]) > 1.0


def test_fog_payload_samples_where_density_is():
    xyz = np.vstack(
        [_blob3(300, (-0.5, 0.0, 0.0), 0.12, 17), _blob3(300, (0.5, 0.0, 0.0), 0.12, 18)]
    )
    t = ridges.fog(xyz, n_samples=2000)
    assert set(t) == {"h", "splats"}
    arr = np.asarray(t["splats"])
    assert len(arr) > 500                       # importance sampling keeps most
    assert arr.shape[1] == 4                    # x, y, z, normalized density
    assert 0.0 < arr[:, 3].min() and arr[:, 3].max() <= 1.0
    # splats concentrate around the two blobs, not in the gap or outside
    near = np.minimum(
        np.abs(arr[:, 0] - -0.5), np.abs(arr[:, 0] - 0.5)
    )
    assert np.median(near) < 0.3
    dense = arr[arr[:, 3] > 0.5]
    assert len(dense) > 50                      # cores are represented
    import json

    json.dumps(t)


def test_fog_is_deterministic():
    xyz = _blob3(200, (0, 0, 0), 0.3, 19)
    a = ridges.fog(xyz, n_samples=500)
    b = ridges.fog(xyz, n_samples=500)
    assert a == b  # fixed seed: rebuilds must not reshuffle the cloud


def test_terrain_payload_shape_and_bounds():
    rng = np.random.default_rng(8)
    xy = np.vstack(
        [_blob(300, (-0.4, -0.3), 0.15, 9), _blob(300, (0.4, 0.35), 0.18, 10)]
    )
    xy = np.clip(xy, -1, 1)
    t = ridges.terrain(xy)
    assert set(t) == {"h", "levels", "fracs", "contours", "ridges", "grid"}
    assert len(t["levels"]) == len(t["fracs"]) == 12
    for c in t["contours"]:
        assert 0 <= c["lv"] < len(t["levels"])
        arr = np.asarray(c["path"])
        assert arr.ndim == 2 and arr.shape[1] == 2
        assert np.abs(arr).max() < 1.6
    for r in t["ridges"]:
        arr = np.asarray(r)
        assert len(arr) >= 4
        assert arr.shape[1] == 3               # x, y, normalized height
        assert 0.0 <= arr[:, 2].min() and arr[:, 2].max() <= 1.0
        assert np.abs(arr[:, :2]).max() < 1.6
    g = t["grid"]
    assert g["nx"] * g["ny"] == len(g["z"])
    assert 0.0 <= min(g["z"]) and max(g["z"]) <= 1.0
    import json

    json.dumps(t)  # payload must be plain-JSON serializable
