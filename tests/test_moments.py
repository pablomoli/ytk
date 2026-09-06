"""Key-moment snap: a mis-stamped moment moves to the line that says it,
in code, before any grader call."""

from __future__ import annotations

from ytk.enricher import EnrichmentV2
from ytk.moments import snap_key_moments


def _draft(moments):
    return EnrichmentV2.model_validate(
        {
            "thesis": "t",
            "summary": "s",
            "key_concepts": ["c"],
            "insights": [],
            "interest_tags": ["x"],
            "key_moments": moments,
        }
    )


TRANSCRIPT = [
    {"start": 2093, "duration": 3, "text": "you think that we're panspermic?"},
    {"start": 2096, "duration": 3, "text": "I do think we are"},
    {"start": 3246, "duration": 3, "text": "horseshoe crabs did fine"},
    {
        "start": 3254,
        "duration": 3,
        "text": "trilobites laid their eggs deeper, why do we not have them",
    },
]


def test_moment_far_from_its_line_moves_to_it():
    d, moves = snap_key_moments(
        _draft(
            [
                {
                    "timestamp": "34:53",
                    "description": "trilobites died out while horseshoe crabs survived",
                }
            ]
        ),
        TRANSCRIPT,
    )
    assert d.key_moments[0].timestamp == "54:06"
    assert moves[0].before == "34:53" and moves[0].after == "54:06"


def test_moment_already_next_to_its_line_stays():
    d, moves = snap_key_moments(
        _draft([{"timestamp": "34:50", "description": "Moore answers panspermia"}]), TRANSCRIPT
    )
    assert d.key_moments[0].timestamp == "34:50" and moves == []


def test_moment_with_no_matching_line_stays():
    d, moves = snap_key_moments(
        _draft([{"timestamp": "10:00", "description": "the mitochondria endosymbiosis"}]),
        TRANSCRIPT,
    )
    assert d.key_moments[0].timestamp == "10:00" and moves == []


def test_one_shared_word_is_coincidence_not_a_move():
    d, moves = snap_key_moments(
        _draft([{"timestamp": "10:00", "description": "crabs in the kitchen"}]), TRANSCRIPT
    )
    assert moves == []
