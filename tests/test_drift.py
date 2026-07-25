"""Snapshot diffing (issue #16, E4): greedy one-to-one centroid matching with
a similarity floor; unmatched themes are births/deaths, never forced matches."""

from __future__ import annotations

import pytest

from ytk import synthesis
from ytk.interest import InterestSnapshot, Theme
from ytk.synthesis import diff_snapshots, render_drift


def _snap(themes, at="2026-07-01T00:00:00"):
    return InterestSnapshot(generated_at=at, note_count=10, themes=themes, profile_markdown="p")


def _theme(label, weight, centroid, note_ids=None):
    return Theme(
        id=label,
        label=label,
        summary="",
        weight=weight,
        note_ids=note_ids or [],
        exemplar_titles=[],
        centroid=centroid,
    )


@pytest.fixture(autouse=True)
def _no_chroma(monkeypatch):
    monkeypatch.setattr(synthesis, "_embeddings_by_id", dict)


def test_match_birth_death():
    old = _snap([_theme("ai", 0.6, [1, 0, 0]), _theme("css", 0.4, [0, 1, 0])])
    new = _snap(
        [_theme("ai-coding", 0.5, [0.98, 0.02, 0]), _theme("lifting", 0.5, [0, 0, 1])],
        at="2026-07-05T00:00:00",
    )
    d = diff_snapshots(old, new)
    assert [(m.old_label, m.new_label) for m in d.matched] == [("ai", "ai-coding")]
    assert d.born == ["lifting"] and d.died == ["css"]


def test_floor_prevents_forced_marriage():
    old = _snap([_theme("ai", 1.0, [1, 0, 0])])
    new = _snap([_theme("cooking", 1.0, [0.5, 0.5, 0.707])])
    d = diff_snapshots(old, new, floor=0.75)
    assert d.matched == []
    assert d.born == ["cooking"] and d.died == ["ai"]


def test_greedy_one_to_one():
    # both new themes are near old "ai"; only the closest may claim it
    old = _snap([_theme("ai", 1.0, [1, 0, 0])])
    new = _snap([_theme("a", 0.5, [0.99, 0.01, 0]), _theme("b", 0.5, [0.97, 0.03, 0])])
    d = diff_snapshots(old, new)
    assert len(d.matched) == 1 and d.matched[0].new_label == "a"
    assert d.born == ["b"]


def test_backfill_from_note_ids(monkeypatch):
    monkeypatch.setattr(
        synthesis, "_embeddings_by_id", lambda: {"n1": [1.0, 0.0], "n2": [1.0, 0.0]}
    )
    old = _snap([_theme("ai", 1.0, None, note_ids=["n1", "n2"])])  # pre-v2, no centroid
    new = _snap([_theme("ai", 1.0, [1.0, 0.0])])
    d = diff_snapshots(old, new)
    assert len(d.matched) == 1 and d.matched[0].similarity == 1.0


def test_render_drift_mentions_movement():
    old = _snap([_theme("ai", 0.2, [1, 0, 0]), _theme("css", 0.5, [0, 1, 0])])
    new = _snap(
        [
            _theme("ai", 0.5, [1, 0, 0]),
            _theme("css", 0.2, [0, 1, 0]),
            _theme("lifting", 0.3, [0, 0, 1]),
        ]
    )
    text = render_drift(diff_snapshots(old, new))
    assert "emerging:" in text and "lifting" in text
    assert "growing:" in text and "fading:" in text
