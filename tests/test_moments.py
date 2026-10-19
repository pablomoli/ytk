"""Key-moment snap: a mis-stamped moment moves to the line that says it,
in code, before any grader call."""

from __future__ import annotations

from ytk.enricher import EnrichmentV2
from ytk.moments import check_anchors, snap_key_moments


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


# --- anchor check -----------------------------------------------------------

LECTURE = [
    {"start": 340, "text": "welcome back to the channel everyone"},
    {"start": 343, "text": "the correct answer is they were all websites"},
    {"start": 348, "text": "at the center of these perks is a single json file"},
    {"start": 380, "text": "the manifest has two dozen properties"},
    {"start": 700, "text": "trilobites laid their eggs deeper in the sediment"},
]


def _concepts_draft(concepts: list[str], summary: str = "s") -> EnrichmentV2:
    return EnrichmentV2.model_validate(
        {
            "thesis": "t",
            "summary": summary,
            "key_concepts": concepts,
            "insights": [],
            "interest_tags": ["x"],
            "key_moments": [],
        }
    )


def test_cite_next_to_a_line_saying_none_of_it_moves_to_the_line_that_does():
    d = _draft([{"timestamp": "5:48", "description": "Reveal: the correct answer, all websites"}])
    rep = check_anchors(d, LECTURE)
    (a,) = rep.anchors
    assert a.verdict == "moved" and a.after == "5:43" and a.cited_shared == 0


def test_cite_whose_span_carries_the_claim_stays():
    d = _draft([{"timestamp": "5:48", "description": "single json file at the center"}])
    (a,) = check_anchors(d, LECTURE).anchors
    assert a.verdict == "ok" and a.after is None


def test_claim_with_no_span_in_the_window_is_unsupported_not_moved():
    # The trilobite line is 352 s away: past the window, the snap's job.
    d = _draft([{"timestamp": "5:48", "description": "trilobites laid eggs deeper"}])
    (a,) = check_anchors(d, LECTURE).anchors
    assert a.verdict == "unsupported" and a.after is None


def test_t_cites_are_checked_and_frame_cites_counted_not_checked():
    d = _concepts_draft(
        [
            "Manifest: two dozen properties [t:343]",
            "App icon: rounded square on the home screen [frame:002]",
            "Layout [sheet]",
        ],
        summary="Opens with a quiz. The answer: they were all websites [t:380].",
    )
    rep = check_anchors(d, LECTURE)
    assert rep.frame_cites == 2
    by_field = {a.field: a for a in rep.anchors}
    assert by_field["key_concepts"].verdict == "moved"
    assert by_field["key_concepts"].after == "t:380"
    assert by_field["summary"].claim == "The answer: they were all websites."
    assert by_field["summary"].after == "t:343"


def test_no_transcript_checks_nothing_but_still_counts_frames():
    rep = check_anchors(_concepts_draft(["x [frame:001]"]), [])
    assert rep.anchors == [] and rep.frame_cites == 1
