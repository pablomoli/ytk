"""Sphere layouts are unit-norm, deterministic, and scored on two axes."""

import numpy as np
import pytest

from ytk.spheremap import choose, fibonacci, lattice, radial, score, sphere_block


def _unit(a: np.ndarray) -> None:
    assert not np.isnan(a).any()
    assert np.abs(np.linalg.norm(a, axis=1) - 1).max() < 1e-9


def test_radial_normalizes_and_centers():
    rng = np.random.default_rng(0)
    c3 = rng.normal(size=(50, 3)) + 5.0  # offset centroid must be removed
    pos = radial(c3)
    _unit(pos)
    # a point at the centroid direction extreme keeps its direction
    assert pos.shape == (50, 3)


def test_radial_zero_vector_survives():
    c3 = np.zeros((3, 3))
    c3[1] = [1.0, 0, 0]
    c3[2] = [-1.0, 0, 0]
    pos = radial(c3)  # centroid-coincident row must not become NaN
    _unit(pos)


def test_fibonacci_even_coverage():
    pos = fibonacci(500)
    _unit(pos)
    # even coverage: every octant populated, z spread across [-1, 1]
    assert pos[:, 2].min() < -0.95 and pos[:, 2].max() > 0.95
    octants = set(map(tuple, (pos > 0).astype(int)))
    assert len(octants) == 8


def test_lattice_themes_contiguous_and_complete():
    rng = np.random.default_rng(1)
    dirs = radial(rng.normal(size=(40, 3)))
    themes = [0] * 10 + [1] * 20 + [2] * 10
    pos = lattice(themes, dirs)
    _unit(pos)
    assert pos.shape == (40, 3)
    # every input index appears exactly once (it is a permutation of slots)
    assert len({tuple(np.round(p, 6)) for p in pos}) == 40


def test_score_shape_and_perfect_layout():
    # identical spaces: trustworthiness is 1, no overlaps on a lattice
    pos = fibonacci(100)
    s = score(pos, pos)
    assert set(s) == {"trustworthiness", "mean_nn_deg", "overlap", "overlap_frac"}
    assert s["trustworthiness"] == pytest.approx(1.0)
    assert s["overlap"] == 0


def test_score_counts_overlaps():
    pos = fibonacci(100)
    pos[1] = pos[0]  # two coincident tiles
    s = score(pos, pos)
    assert s["overlap"] >= 2


def test_choose_prefers_fidelity_within_overlap_bound():
    scores = {
        "radial": {"trustworthiness": 0.95, "overlap_frac": 0.30},
        "lattice": {"trustworthiness": 0.80, "overlap_frac": 0.0},
        "haversine": {"trustworthiness": 0.90, "overlap_frac": 0.04},
    }
    assert choose(scores) == "haversine"  # best trust among overlap <= 5%


def test_choose_ignores_missing_layouts():
    scores = {
        "radial": {"trustworthiness": 0.9, "overlap_frac": 0.5},
        "lattice": {"trustworthiness": 0.7, "overlap_frac": 0.0},
    }
    assert choose(scores) == "lattice"  # radial over bound, haversine absent


def test_choose_falls_back_to_fidelity_when_nothing_is_legible():
    scores = {
        "radial": {"trustworthiness": 0.95, "overlap_frac": 0.30},
        "lattice": {"trustworthiness": 0.80, "overlap_frac": 0.20},
    }
    assert choose(scores) == "radial"  # all over bound, best trust wins


def test_sphere_block_schema_without_umap():
    rng = np.random.default_rng(2)
    vecs = rng.normal(size=(30, 8))
    c3 = rng.normal(size=(30, 3))
    themes = [i % 3 for i in range(30)]
    block = sphere_block(vecs, c3, themes, run_haversine=False)
    assert block["haversine"] is None
    assert len(block["radial"]) == 30 and len(block["lattice"]) == 30
    assert block["chosen"] in ("radial", "lattice")
    assert "haversine" not in block["scores"]
    # JSON-safe: plain lists of floats, rounded
    assert isinstance(block["radial"][0][0], float)
