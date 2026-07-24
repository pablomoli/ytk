import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_map import anchor_names


def _meta(titles):
    return [{"title": t} for t in titles]


def test_anchor_reuses_name_within_same_domain():
    meta = _meta(["a", "b", "c", "d"])
    prev = [("County GIS", {"a", "b", "c"}, "epicmap")]
    anchored = anchor_names([0, 0, 0, -1], meta, 1, prev, new_domains=["epicmap"])
    assert anchored == {0: "County GIS"}


def test_anchor_never_crosses_domains():
    meta = _meta(["a", "b", "c", "d"])
    prev = [("County GIS", {"a", "b", "c"}, "epicmap")]
    anchored = anchor_names([0, 0, 0, -1], meta, 1, prev, new_domains=["other"])
    assert anchored == {}


def test_anchor_allows_pre_v2_names_without_domain():
    meta = _meta(["a", "b", "c", "d"])
    prev = [("County GIS", {"a", "b", "c"}, None)]
    anchored = anchor_names([0, 0, 0, -1], meta, 1, prev, new_domains=["other"])
    assert anchored == {0: "County GIS"}
