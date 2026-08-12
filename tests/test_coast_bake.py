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


def test_bake_superplanet_writes_texture(tmp_path: Path):
    out = tmp_path / "super.png"
    # small synthetic layout: exercises the path, not real scale
    meta = coast.bake_superplanet(fibonacci(40), fibonacci(40), out)
    from PIL import Image

    img = np.asarray(Image.open(out))
    assert img.shape == (512, 1024)
    assert img.dtype == np.uint8
    np.testing.assert_array_equal(img[:, 0], img[:, -1])
    assert 0 < meta["land_frac"] < 1 and meta["coast_deg"] > 0


def test_saturated_magma_lut_shape_and_ends():
    lut = coast.saturated_magma_lut()
    assert lut.shape == (256, 3)
    assert lut.dtype == np.uint8
    assert lut[0].max() < 16  # low end is near-black
    r, g, b = lut[-1]
    assert r > 240 and g > 240 and b > 140  # high end is the cream-yellow tip


def test_saturated_magma_lut_matches_plot_assets():
    """Sync contract: the embedded ramp is plot_assets.saturated_magma(), not a
    lookalike. Skipped where matplotlib is absent (it is a dev-only dep)."""
    pytest.importorskip("matplotlib")
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from plot_assets import saturated_magma

    want = (np.asarray(saturated_magma()(np.linspace(0, 1, 256)))[:, :3] * 255).round()
    assert np.abs(coast.saturated_magma_lut().astype(float) - want).max() <= 1


def test_bake_ramp_writes_256x1_rgb(tmp_path: Path):
    from PIL import Image

    out = tmp_path / "ramp.png"
    coast.bake_ramp(out)
    img = np.asarray(Image.open(out))
    assert img.shape == (1, 256, 3)
    np.testing.assert_array_equal(img[0], coast.saturated_magma_lut())
