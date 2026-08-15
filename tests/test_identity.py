"""Stable theme identity (#83 phase 1): membership-first matching, lifecycle
events persisted at synthesis time, centroid cosine only as a restated fallback."""

from __future__ import annotations

import numpy as np

from ytk.identity import as_diff, reconcile
from ytk.interest import InterestSnapshot, Theme


def _theme(label, note_ids, theme_id=None, weight=0.5, centroid=None):
    return Theme(
        id=label,
        label=label,
        summary="",
        weight=weight,
        note_ids=note_ids,
        exemplar_titles=[],
        centroid=centroid,
        theme_id=theme_id,
    )


def _snap(themes, at="2026-08-01T00:00:00"):
    return InterestSnapshot(generated_at=at, note_count=20, themes=themes, profile_markdown="p")


def _kinds(snapshot):
    return sorted(e.kind for e in snapshot.events)


def test_first_snapshot_mints_ids_and_births():
    snap = _snap([_theme("ai", ["a"]), _theme("css", ["b"])])
    pairs = reconcile(None, snap)
    assert pairs == []
    assert [t.theme_id for t in snap.themes] == ["T001", "T002"]
    assert _kinds(snap) == ["birth", "birth"]
    assert snap.reconciled_from is None


def test_identical_membership_keeps_ids_and_no_events():
    old = _snap([_theme("ai", ["a", "b"], "T001"), _theme("css", ["c", "d"], "T002")])
    new = _snap([_theme("css renamed", ["c", "d"]), _theme("ai", ["a", "b"])])
    reconcile(old, new)
    assert new.themes[0].theme_id == "T002"  # id follows membership, not label
    assert new.themes[1].theme_id == "T001"
    assert new.events == []
    assert new.reconciled_from == old.generated_at


def test_growth_is_continuation_not_drift():
    # 2 old notes inside a 6-note new theme: Jaccard 0.33 would call this
    # churn; containment 1.0 correctly reads growth.
    old = _snap([_theme("ai", ["a", "b"], "T001")])
    new = _snap([_theme("ai", ["a", "b", "c", "d", "e", "f"])])
    pairs = reconcile(old, new)
    assert new.themes[0].theme_id == "T001"
    assert pairs == [(0, 0, 1.0)] and new.events == []


def test_birth_and_death():
    old = _snap([_theme("ai", ["a", "b"], "T001"), _theme("css", ["c", "d"], "T002")])
    new = _snap([_theme("ai", ["a", "b"]), _theme("lifting", ["x", "y"])])
    reconcile(old, new)
    assert new.themes[0].theme_id == "T001"
    assert new.themes[1].theme_id == "T003"  # counter continues past dead T002
    assert _kinds(new) == ["birth", "death"]


def test_merge_absorbs_instead_of_killing():
    old = _snap(
        [
            _theme("ai", ["a1", "a2", "a3", "a4"], "T001"),
            _theme("agents", ["b1", "b2"], "T002"),
        ]
    )
    new = _snap([_theme("ai and agents", ["a1", "a2", "a3", "a4", "b1", "b2"])])
    reconcile(old, new)
    assert new.themes[0].theme_id == "T001"  # larger overlap wins the id
    merge = [e for e in new.events if e.kind == "merge"]
    assert len(merge) == 1
    assert merge[0].theme_id == "T001" and merge[0].others == ["T002"]
    assert not [e for e in new.events if e.kind == "death"]


def test_split_largest_fragment_inherits():
    old = _snap([_theme("graphics", ["a", "b", "c", "d", "e"], "T001")])
    new = _snap(
        [
            _theme("shaders", ["a", "b", "c"]),
            _theme("generative art", ["d", "e"]),
        ]
    )
    reconcile(old, new)
    assert new.themes[0].theme_id == "T001"
    assert new.themes[1].theme_id == "T002"
    split = [e for e in new.events if e.kind == "split"]
    assert len(split) == 1
    assert split[0].theme_id == "T001" and split[0].others == ["T002"]
    assert not [e for e in new.events if e.kind in ("birth", "death")]


def test_centroid_fallback_restates():
    # No surviving member ids (indexer id-scheme churn) but same direction.
    old = _snap([_theme("ai", ["old-1", "old-2"], "T001")])
    new = _snap([_theme("ai", ["new-1", "new-2"])])
    v = np.array([1.0, 0.0])
    pairs = reconcile(old, new, old_centroids=[v], new_centroids=[v])
    assert new.themes[0].theme_id == "T001"
    assert pairs and pairs[0][2] == 1.0
    assert _kinds(new) == ["restated"]


def test_cross_encoder_centroids_are_incomparable():
    old = _snap([_theme("ai", ["old-1"], "T001")])
    new = _snap([_theme("ai", ["new-1"])])
    pairs = reconcile(old, new, old_centroids=[np.ones(384)], new_centroids=[np.ones(1024)])
    assert pairs == []
    assert _kinds(new) == ["birth", "death"]


def test_pre_identity_previous_gets_minted_in_order():
    old = _snap([_theme("ai", ["a", "b"]), _theme("css", ["c", "d"])])
    new = _snap([_theme("css", ["c", "d"]), _theme("ai", ["a", "b"])])
    reconcile(old, new)
    assert [t.theme_id for t in old.themes] == ["T001", "T002"]
    assert [t.theme_id for t in new.themes] == ["T002", "T001"]


def test_as_diff_agrees_with_events():
    old = _snap([_theme("ai", ["a", "b"], "T001"), _theme("css", ["c", "d"], "T002")])
    new = _snap([_theme("ai", ["a", "b"]), _theme("lifting", ["x", "y"])])
    pairs = reconcile(old, new)
    d = as_diff(old, new, pairs)
    assert [(m.old_label, m.new_label) for m in d.matched] == [("ai", "ai")]
    assert d.born == ["lifting"] and d.died == ["css"]
