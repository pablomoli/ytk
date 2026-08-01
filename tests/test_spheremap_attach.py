import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_map import _content_alignment


def _points():
    return [
        {"t": "a", "c": "youtube", "c3": [0, 0, 1]},
        {"t": "b", "c": "memory"},
        {"t": "c", "c": "instagram", "c3": [1, 0, 0]},
    ]


def _meta():
    return [
        {"title": "a", "cat": "youtube"},
        {"title": "b", "cat": "memory"},
        {"title": "c", "cat": "instagram"},
    ]


def test_alignment_returns_content_indices():
    assert _content_alignment(_points(), _meta(), {"youtube", "instagram"}) == [0, 2]


def test_alignment_rejects_count_drift():
    with pytest.raises(SystemExit):
        _content_alignment(_points()[:2], _meta(), {"youtube", "instagram"})


def test_alignment_rejects_title_drift():
    meta = _meta()
    meta[0]["title"] = "renamed since map build"
    with pytest.raises(SystemExit):
        _content_alignment(_points(), meta, {"youtube", "instagram"})
