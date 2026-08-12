import json

import numpy as np

from ytk import galaxy


# n_big=26/n_small=6/std=0.08/seed=1 (brief's literal fixture) does not gate:
# verified against the unmodified scripts/e33_channels.py functions directly
# (byte-identical output to this port) that mean triplet-stability of the
# planted structure is statistically indistinguishable from the null cloud's
# mean at that imbalance (0.887 vs 0.888 over 60 seeds).
#
# A first replacement fixture (16/10, std=0.02, tight+separated) was also
# rejected on review: it only earns for 7-10/30 gate seeds at these params,
# because tight isotropic clusters collapse the covariance to ~rank-1 (one
# huge between-cluster eigenvalue), which makes null_cloud's matched-spectrum
# unimodal sample almost as triplet-stable as the real split (mean 0.98 real
# vs 0.99+ TRUE null q95 measured at n=500 — the 30% pass rate at n_null=15
# was small-sample quantile noise, not real detection: seed=18 was a lucky
# 15-draw sample, not a genuinely separated regime).
#
# Fix: give the within-cluster noise real magnitude (std=1.0 vs sep=3, ratio
# ~0.33) so the covariance spectrum is multi-directional like real vault
# embeddings (cross-checked against ~/.ytk/e33-channels.json's actual gated
# themes, whose null_hi sits 0.72-0.93, not the 0.90-0.99 this fixture's
# earlier rank-1 version produced). Measured at n_boot=10/n_null=15 over gate
# seeds 1..30: 29/30 earn (seed 23 is the sole miss, margin -0.0002); pinned
# seed=18 (margin +0.030). The genuine best-k=2 cut puts one outlier core
# point in with the moon (std=1.0 causes real overlap), so the honest split
# is core=17/moon=11, not 18/10 — asserted below as measured, not as planted.
def _two_clusters(n_big=18, n_small=10, seed=9):
    rng = np.random.default_rng(seed)
    v = np.concatenate(
        [
            rng.normal([3, 0, 0, 0], 1.0, (n_big, 4)),
            rng.normal([0, 3, 0, 0], 1.0, (n_small, 4)),
        ]
    )
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_moon_gate_finds_planted_minority(tmp_path):
    out = galaxy.moon_gate(_two_clusters(), seed=18, n_boot=10, n_null=15)
    assert out["earned"]
    assert out["core_size"] == 17
    assert len(out["moons"]) == 1 and len(out["moons"][0]["member_idx"]) == 11


def test_unimodal_earns_nothing():
    rng = np.random.default_rng(2)
    v = rng.normal([4, 0, 0, 0], 0.3, (30, 4))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    out = galaxy.moon_gate(v, seed=1, n_boot=10, n_null=15)
    assert not out["earned"] or not out["moons"]


def test_cache_hit_skips_compute(tmp_path, monkeypatch):
    vn = _two_clusters()
    paths = [f"p{i}.md" for i in range(len(vn))]
    cache = tmp_path / "cache.json"
    first = galaxy.moons_cached(vn, paths, "v2", cache, seed=1)
    calls = {"n": 0}
    real = galaxy.moon_gate
    monkeypatch.setattr(
        galaxy, "moon_gate", lambda *a, **k: calls.__setitem__("n", 1) or real(*a, **k)
    )
    second = galaxy.moons_cached(vn, paths, "v2", cache, seed=1)
    assert calls["n"] == 0 and second == first
    assert galaxy.member_hash(paths, "v2") in json.loads(cache.read_text())
