"""`ytk lsd` sampler on a synthetic cone: a random cloud plus one shared
direction, so raw cosines float and centred ones straddle zero."""

from __future__ import annotations

import numpy as np
import pytest

from ytk import lsd


@pytest.fixture(scope="module")
def cone():
    rng = np.random.default_rng(0)
    cloud = rng.normal(size=(300, 64)).astype(np.float32)
    cloud /= np.linalg.norm(cloud, axis=1, keepdims=True)
    shared = rng.normal(size=64).astype(np.float32)
    shared /= np.linalg.norm(shared)
    X = cloud + 0.6 * shared
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    Xc, mean_norm = lsd.centre(X)
    return X, Xc, mean_norm


def test_centre_removes_the_shared_direction(cone):
    X, Xc, mean_norm = cone
    assert mean_norm > 0.4
    assert abs(float(np.linalg.norm(Xc.mean(axis=0)))) < 0.05
    assert np.allclose(np.linalg.norm(Xc, axis=1), 1.0, atol=1e-5)


def test_tilt_acceptance_is_one_at_the_floor_and_decays():
    a = lsd.tilt_acceptance(np.array([-0.2, -0.1, 0.0]), floor=-0.2, temperature=0.1)
    assert a[0] == 1.0
    assert abs(a[1] - np.exp(-1)) < 1e-6
    assert a[2] < a[1]


def test_ortho_stays_under_the_tail_and_below_rand(cone):
    X, Xc, _ = cone
    rng = np.random.default_rng(1)
    tail = float(np.percentile(lsd.background_cosines(Xc, rng, 20_000), lsd.TAIL_PCT))
    pairs = lsd.sample_pairs(X, Xc, "ortho", 80, rng, tail)
    assert len(pairs) == 80
    assert all(p.cos_c <= tail for p in pairs)
    rand = lsd.sample_pairs(X, Xc, "rand", 80, rng, tail)
    assert np.median([p.cos_c for p in pairs]) < np.median([p.cos_c for p in rand])


def test_near_pairs_are_neighbours(cone):
    X, Xc, _ = cone
    rng = np.random.default_rng(2)
    pairs = lsd.sample_pairs(X, Xc, "near", 50, rng, tail=1.0, k_near=5)
    S = Xc @ Xc.T
    np.fill_diagonal(S, -np.inf)
    for p in pairs:
        rank = int((S[p.i] > S[p.i, p.j]).sum())
        assert rank < 5


def test_pairs_are_distinct_and_never_self(cone):
    X, Xc, _ = cone
    rng = np.random.default_rng(3)
    pairs = lsd.sample_pairs(X, Xc, "rand", 120, rng, tail=1.0)
    keys = {(min(p.i, p.j), max(p.i, p.j)) for p in pairs}
    assert len(keys) == 120
    assert all(p.i != p.j for p in pairs)


def test_note_text_prefers_thesis_and_insights():
    md = "---\ntitle: A Note\n---\n\n## Thesis\nOne claim.\n\n## Summary\nLong.\n\n## Insights\n- a\n- b\n"
    title, text = lsd.note_text_from_markdown(md)
    assert title == "A Note"
    assert text == "One claim.\n- a\n- b"
    _, fallback = lsd.note_text_from_markdown("---\ntitle: x\n---\n## Summary\nOnly this.\n")
    assert fallback == "Only this."
