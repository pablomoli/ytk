"""House rules (writer_rules): the text the writer reads and the lint."""

from typing import Any

from ytk.enricher import EnrichmentV2
from ytk.writer_rules import WIRED, lint

BASE: dict[str, Any] = {
    "thesis": "Gwern argues GPT-3's few-shot jump validates the scaling hypothesis.",
    "summary": "Loss keeps falling with compute. Few-shot ability appears without finetuning.",
    "key_concepts": ["Scaling hypothesis: Gwern's bet that size alone buys ability [t:12]"],
    "insights": ["Budget for compute before architecture search."],
    "interest_tags": ["machine-learning", "scaling-laws"],
    "key_moments": [],
}


def _rules(**over: Any) -> list[str]:
    return [h.rule for h in lint(EnrichmentV2.model_validate({**BASE, **over}))]


def test_clean_draft_has_no_hits():
    assert _rules() == []


def test_medium_openings_are_flagged_where_they_stand():
    for text in (
        "The reel is a build log for reaction_cam.py.",
        "The video opens on a whiteboard.",
        "A creator recaps Google's connectome map.",
        "The episode traces hibernation science.",
        "In this piece the knot cycles.",
        "This clip shows a static image fed to a tool.",
    ):
        assert _rules(summary=text) == ["open on the claim"], text
    hits = lint(EnrichmentV2.model_validate({**BASE, "insights": ["The essay argues well."]}))
    assert [(h.rule, h.where) for h in hits] == [("open on the claim", "insights[0]")]


def test_claim_openings_are_not_flagged():
    for text in (
        "Gwern argues that scale is enough.",
        "A post-training trick recovers the lost accuracy.",
        "The host's point, not the guest's, is that minds are correlated.",
        "The talking-head format hides a screen recording at 1:26.",
        "A complete wiring diagram now exists for one animal.",
    ):
        assert "open on the claim" not in _rules(summary=text), text


def test_process_leaks_are_flagged_but_a_grader_in_the_content_is_not():
    assert _rules(insights=["Tag it, which the grader flagged as needed."]) == [
        "prose only, no process"
    ]
    assert _rules(summary='Five sentences.</summary>\n<parameter name="x">') == [
        "prose only, no process"
    ]
    assert _rules(summary="OpenAI's grader only checked for a secret code.") == []


def test_near_synonym_tags_skip_derived_rec_tags():
    assert _rules(interest_tags=["education", "learning", "piano"]) == ["near-synonym tags"]
    assert _rules(interest_tags=["ai", "ai-agents"]) == ["near-synonym tags"]
    assert _rules(interest_tags=["fiction", "book-rec"]) == []


def test_running_order_and_frame_inference_are_reported():
    order = "It opens with a logo. It then pivots to patients. He closes by naming a field."
    assert "the argument, not the running order" in _rules(summary=order)
    assert _rules(key_concepts=["Venue: an outdoor night market gig [frame:001]"]) == [
        "mark inference from frames"
    ]
    assert _rules(key_concepts=["Venue: likely a street market (inferred) [frame:001]"]) == []
    assert _rules(key_concepts=["Venue: a street market, he says so [t:3] [frame:001]"]) == []


def test_only_precise_rules_are_wired():
    assert {"open on the claim", "prose only, no process"} == WIRED
