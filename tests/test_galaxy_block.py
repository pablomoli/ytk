import datetime

import numpy as np
import pytest

from ytk import galaxy


def _fixture():
    rng = np.random.default_rng(3)
    c3 = np.concatenate([rng.normal([2, 0, 0], 0.2, (8, 3)), rng.normal([-2, 1, 0], 0.2, (5, 3))])
    vecs = np.concatenate([rng.normal(0, 1, (8, 16)), rng.normal(3, 1, (5, 16))])
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    themes = np.array([0] * 8 + [1] * 5)
    dates = ["2026-08-01"] * 8 + ["2024-01-01"] * 4 + [None]
    paths = [f"n{i}.md" for i in range(13)]
    return vecs, c3, themes, dates, ["alpha", "beta"], paths


def test_block_positions_and_radii():
    vecs, c3, themes, dates, labels, paths = _fixture()
    today = datetime.date(2026, 8, 12)
    block = galaxy.galaxy_block(vecs, c3, themes, dates, labels, paths, today=today)
    assert [p["theme"] for p in block] == [0, 1]
    a = block[0]
    np.testing.assert_allclose(np.linalg.norm(a["pos"]), 1.0, atol=1e-6)
    assert a["radius_deg"] == pytest.approx(galaxy.GALAXY_K * 8 ** (1 / 3))
    # theme 0 all dated within 90d -> class V; theme 1 all old -> class I
    assert a["cls"] == "V" and block[1]["cls"] == "I"
    assert block[1]["date_coverage"] == pytest.approx(4 / 5)
    assert a["median_age_days"] == pytest.approx(11)


def test_member_hash_stable_and_sensitive():
    h1 = galaxy.member_hash(["b.md", "a.md"], "v2")
    assert h1 == galaxy.member_hash(["a.md", "b.md"], "v2")
    assert h1 != galaxy.member_hash(["a.md"], "v2")
    assert h1 != galaxy.member_hash(["a.md", "b.md"], "v3")
