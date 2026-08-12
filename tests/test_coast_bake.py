from pathlib import Path

import numpy as np
import pytest

from ytk import coast
from ytk.spheremap import fibonacci


def _cluster(n: int, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal([1.0, 0.2, -0.1], 0.3, (n, 3))


def test_grid_shapes_and_seam():
    ll, tt, xyz = coast.grid()
    assert ll.shape == tt.shape == (256, 512)
    assert xyz.shape == (256, 512, 3)
    # lon endpoints are the same direction: the baked seam must be continuous
    np.testing.assert_allclose(xyz[:, 0, :], xyz[:, -1, :], atol=1e-9)


def test_organic_sd_pins_land_area():
    ll, tt, xyz = coast.grid()
    pos = fibonacci(40)
    coast_deg = coast.ocean_radius(fibonacci(40))
    sd = coast.organic_sd(pos, xyz, tt, coast_deg)
    w = np.cos(tt)
    land = (w * (sd < 0)).sum() / w.sum()
    dist = np.degrees(np.arccos(np.clip(xyz @ pos.T, -1, 1))).min(axis=-1)
    target = (w * (dist < coast_deg)).sum() / w.sum()
    assert land == pytest.approx(target, abs=0.02)


def test_bake_planet_writes_texture(tmp_path: Path):
    out = tmp_path / "5.png"
    meta = coast.bake_planet(_cluster(30), out)
    from PIL import Image

    img = np.asarray(Image.open(out))
    assert img.shape == (256, 512)
    assert img.dtype == np.uint8
    # both land and sea present, and the seam columns agree
    assert (img > 140).any() and (img < 110).any()
    np.testing.assert_array_equal(img[:, 0], img[:, -1])
    assert 0 < meta["land_frac"] < 1 and meta["coast_deg"] > 0
