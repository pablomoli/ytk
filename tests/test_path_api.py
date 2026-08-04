"""Tests for the path view backend (hub.compute_path) — no network, no Chroma."""

from __future__ import annotations

import numpy as np
import pytest

from ytk.ui import hub


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def _fake_corpus():
    # endpoints 60 degrees apart; one note sits exactly on the midpoint
    # direction; one note duplicates endpoint A's video_id under another title
    a = _unit([1, 0, 0, 0])
    b = _unit([0.5, np.sqrt(3) / 2, 0, 0])
    mid = _unit(a + b)
    off = _unit([0, 0, 1, 0])
    dup_a = _unit([0.99, 0.1, 0, 0])
    X = np.stack([a, b, mid, off, dup_a])
    metas = [
        {"title": "Alpha lecture", "url": "u/a", "video_id": "vidA"},
        {"title": "Beta essay", "url": "u/b", "video_id": "vidB"},
        {"title": "The bridge note", "url": "u/m", "video_id": "vidM"},
        {"title": "Unrelated", "url": "u/o", "video_id": "vidO"},
        {"title": "Alpha repost", "url": "u/a2", "video_id": "vidA"},
    ]
    return metas, X


def _fetch():
    return _fake_corpus()


def test_path_resolves_titles_and_walks_monotonically():
    out = hub.compute_path("alpha lecture", "beta", stops=5, fetch=_fetch)
    assert out["a"]["video_id"] == "vidA"
    assert out["b"]["video_id"] == "vidB"
    assert len(out["stops"]) == 5
    assert out["angle_deg"] == pytest.approx(60.0, abs=0.5)
    # endpoints and the video_id duplicate never appear among retrieved notes
    seen = {n["video_id"] for s in out["stops"] for n in s["notes"]}
    assert "vidA" not in seen and "vidB" not in seen
    # the midpoint stop retrieves the bridge note first
    mid_stop = out["stops"][2]
    assert mid_stop["notes"][0]["video_id"] == "vidM"
    # weights are sorted descending within each stop
    for s in out["stops"]:
        ws = [n["weight"] for n in s["notes"]]
        assert ws == sorted(ws, reverse=True)


def test_path_endpoint_errors():
    with pytest.raises(LookupError):
        hub.compute_path("nonexistent", "beta", fetch=_fetch)
    with pytest.raises(ValueError):
        hub.compute_path("alpha", "beta", fetch=_fetch)  # ambiguous: lecture + repost
    with pytest.raises(ValueError):
        hub.compute_path("vidA", "vidA", fetch=_fetch)


def test_path_exact_id_beats_substring():
    out = hub.compute_path("vidA", "u/b", stops=3, fetch=_fetch)
    assert out["a"]["title"] == "Alpha lecture"
    assert out["b"]["video_id"] == "vidB"


def _fetch_with_instagram():
    # memories-sourced content notes carry no video_id (#169): exclusion must
    # work by index, not by the shared None
    metas, X = _fake_corpus()
    metas = [*metas]
    metas[0] = {"title": "Fibonacci fruits sequencer", "url": "ig/a", "video_id": None}
    metas[3] = {"title": "Alien HUD reference", "url": "ig/o", "video_id": None}
    return metas, X


def test_path_instagram_endpoints_without_video_id():
    out = hub.compute_path("ig/a", "beta", stops=5, fetch=_fetch_with_instagram)
    assert out["a"]["title"] == "Fibonacci fruits sequencer"
    assert out["a"]["video_id"] is None
    urls = {n["url"] for s in out["stops"] for n in s["notes"]}
    # endpoint A itself never appears as a stop, and the other url-less
    # instagram note is still retrievable
    assert "ig/a" not in urls and "u/b" not in urls
    assert out["stops"][2]["notes"][0]["url"] == "u/m"
