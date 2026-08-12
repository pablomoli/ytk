"""Arm 0 (#179): cover-hue extraction. Hue only -- value and saturation
always come from the ramp, so a theme of dark covers can pick a direction
and nothing else."""

import numpy as np
import pytest
from PIL import Image

from ytk import galaxy


def hue_err(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def write_solid(path, rgb, size=(96, 96)):
    Image.new("RGB", size, rgb).save(path)
    return path


def write_dark_with_patch(path, rgb, size=(96, 96), frac=0.1):
    """A cover that is mostly black with a small saturated region -- the shape
    the dark-covers concern is about."""
    a = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    rows = max(1, int(size[1] * frac))
    a[:rows, :, :] = np.array(rgb, dtype=np.uint8)
    Image.fromarray(a, mode="RGB").save(path)
    return path


def test_dominant_hue_pure_green(tmp_path):
    paths = [write_solid(tmp_path / f"g{i}.png", (0, 200, 0)) for i in range(4)]
    h = galaxy.dominant_hue(paths)
    assert h is not None
    assert 0.0 <= h < 360.0
    assert hue_err(h, 120.0) <= 10.0


def test_dominant_hue_ignores_dark_cover(tmp_path):
    paths = [write_dark_with_patch(tmp_path / f"d{i}.png", (220, 20, 20)) for i in range(4)]
    h = galaxy.dominant_hue(paths)
    assert h is not None, "the saturated patch must survive the near-black drop"
    assert hue_err(h, 0.0) <= 15.0


def test_dominant_hue_none_under_three_images(tmp_path):
    paths = [write_solid(tmp_path / f"g{i}.png", (0, 200, 0)) for i in range(2)]
    assert galaxy.dominant_hue(paths) is None


def test_dominant_hue_none_when_unopenable(tmp_path):
    paths = [tmp_path / f"missing{i}.png" for i in range(4)]
    assert galaxy.dominant_hue(paths) is None


def test_dominant_hue_none_when_all_gray(tmp_path):
    """Every pixel below the saturation floor: no survivors, no direction."""
    paths = [write_solid(tmp_path / f"n{i}.png", (90, 92, 91)) for i in range(4)]
    assert galaxy.dominant_hue(paths) is None


def test_dominant_hue_is_deterministic(tmp_path):
    paths = [
        write_dark_with_patch(tmp_path / f"m{i}.png", rgb, frac=0.4)
        for i, rgb in enumerate([(220, 20, 20), (20, 20, 220), (220, 20, 20), (10, 200, 30)])
    ]
    first = galaxy.dominant_hue(paths)
    assert first == galaxy.dominant_hue(paths)


def test_ramp_anchor_is_the_land_midtone(tmp_path):
    from ytk.coast import saturated_magma_lut

    anchor = galaxy.ramp_anchor_deg()
    tmp = tmp_path / "one.png"
    Image.fromarray(saturated_magma_lut()[192].reshape(1, 1, 3), mode="RGB").save(tmp)
    # same pixel, same hue: the anchor is exactly LUT[192]'s hue angle
    rgb = np.asarray(Image.open(tmp).convert("RGB"), dtype=float).reshape(-1, 3) / 255.0
    hsv = galaxy._rgb_to_hsv(rgb)
    assert hue_err(anchor, float(hsv[0, 0]) * 360.0) < 0.5


def test_spread_shift_opens_the_wedge_without_moving_the_anchor(tmp_path):
    anchor = galaxy.ramp_anchor_deg()
    # covers that already match the ramp leave the canonical magma alone
    assert galaxy.spread_shift(anchor) == 0.0
    # a 10 deg cover difference becomes a GAIN x 10 deg rotation difference
    a = galaxy.spread_shift(anchor + 5.0)
    b = galaxy.spread_shift(anchor - 5.0)
    sep = abs((a - b + 180) % 360 - 180)
    assert abs(sep - 10.0 * galaxy.HUE_SPREAD_GAIN) < 0.5
    # signed first: just below the anchor goes just below 360, not the long way
    assert galaxy.spread_shift(anchor - 1.0) > 350.0


def test_spread_shift_depends_only_on_this_planet(tmp_path):
    """No corpus statistic and no ranking against siblings: the same measured
    hue must give the same rotation whatever else the galaxy contains, which
    is what keeps an unchanged member set an unchanged colour."""
    assert galaxy.spread_shift(37.0) == galaxy.spread_shift(37.0)
    assert galaxy.spread_shift(37.0, gain=1.0) != galaxy.spread_shift(37.0, gain=5.0)


def test_hue_cached_skips_recompute(tmp_path, monkeypatch):
    paths = [write_solid(tmp_path / f"g{i}.png", (0, 200, 0)) for i in range(4)]
    cache_path = tmp_path / "cache.json"
    calls = {"n": 0}
    real = galaxy.dominant_hue

    def counted(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(galaxy, "dominant_hue", counted)
    first = galaxy.hue_cached(paths, "abc123", cache_path)
    assert calls["n"] == 1
    second = galaxy.hue_cached(paths, "abc123", cache_path)
    assert calls["n"] == 1, "a cached hue must not re-open the thumbnails"
    assert second == first
    # a different member set is a different key -- must extract again
    galaxy.hue_cached(paths, "def456", cache_path)
    assert calls["n"] == 2


def test_hue_cached_caches_the_none(tmp_path, monkeypatch):
    """A thumb-poor theme must not re-scan its (still too few) covers on
    every build just because the answer was None."""
    paths = [write_solid(tmp_path / "g0.png", (0, 200, 0))]
    cache_path = tmp_path / "cache.json"
    calls = {"n": 0}
    real = galaxy.dominant_hue

    def counted(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(galaxy, "dominant_hue", counted)
    assert galaxy.hue_cached(paths, "abc123", cache_path) is None
    assert galaxy.hue_cached(paths, "abc123", cache_path) is None
    assert calls["n"] == 1


@pytest.mark.parametrize(
    ("rgb", "expect"),
    [((220, 20, 20), 0.0), ((20, 200, 20), 120.0), ((30, 30, 210), 240.0)],
)
def test_dominant_hue_tracks_the_patch_colour(tmp_path, rgb, expect):
    paths = [write_dark_with_patch(tmp_path / f"p{i}.png", rgb) for i in range(3)]
    h = galaxy.dominant_hue(paths)
    assert h is not None and hue_err(h, expect) <= 15.0
