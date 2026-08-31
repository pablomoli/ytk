"""The grader's deterministic layer (#197 P4): code only, every draft,
spends no model call, bounces with the failing check named."""

import pytest

from ytk import grader
from ytk.enricher import EnrichmentV2, NewTag
from ytk.evidence import EvidenceBundle


def _bundle(**overrides) -> EvidenceBundle:
    base = {
        "source": "youtube",
        "url": "https://y/1",
        "title": "T",
        "transcript": [
            {"start": 0, "duration": 3, "text": "we built a three-file loop for agents"},
            {"start": 3, "duration": 3, "text": "the grader cannot edit the work script"},
            {"start": 400, "duration": 3, "text": "ripgrep scans the rules markdown fast"},
        ],
        "transcript_origin": "api-manual",
        "transcript_language": "en",
        "transcript_status": "ok",
        "description": "Video about claude-agent-sdk loops.",
        "duration": 613,
    }
    base.update(overrides)
    return EvidenceBundle(**base)


def _draft(**overrides) -> EnrichmentV2:
    base = {
        "thesis": "He builds a three-file agent loop whose grader the agent cannot edit.",
        "summary": "Work script, grader, rules markdown; ripgrep scans the rules.",
        "key_concepts": [
            "three-file loop: work script, grader, rules markdown",
            "ripgrep: scans the rules markdown on every tick",
        ],
        "insights": ["Keep the grader outside the worker."],
        "interest_tags": ["ai-agents"],
        "key_moments": [
            {"timestamp": "0:03", "description": "grader cannot edit the work script"},
            {"timestamp": "6:40", "description": "ripgrep scans the rules markdown"},
        ],
        "recommendations": [],
        "evidence_gaps": [],
        "take_response": "Agreed; cron cannot carry blame.",
        "new_tags": [],
    }
    base.update(overrides)
    return EnrichmentV2.model_validate(base)


VOCAB = ["ai-agents", "creative-coding"]


def _check(draft, bundle=None, **kw):
    kw.setdefault("vocab", VOCAB)
    kw.setdefault("take_kind", "intent")
    kw.setdefault("take_text", "why loops beat cron")
    return grader.deterministic_checks(draft, bundle or _bundle(), **kw)


def test_clean_draft_passes():
    assert _check(_draft()) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("thesis", "This talk delves into the landscape of agent loops."),
        ("summary", "The video explores a journey through agent tooling."),
    ],
)
def test_banned_phrasing_bounces(field, value):
    bounces = _check(_draft(**{field: value}))
    assert any(b.check == "banned phrasing" for b in bounces)


def test_timestamp_beyond_duration_bounces():
    d = _draft(key_moments=[{"timestamp": "12:00", "description": "grader cannot edit"}])
    bounces = _check(d)
    assert any(b.check == "key moment timestamp" for b in bounces)


def test_timestamp_with_no_matching_transcript_bounces():
    d = _draft(key_moments=[{"timestamp": "0:03", "description": "quantum kubernetes espresso"}])
    bounces = _check(d)
    assert any(b.check == "key moment adjacency" for b in bounces)


def test_moment_checks_skip_without_duration_or_transcript():
    b = _bundle(duration=None, transcript=[], transcript_status="none")
    d = _draft(key_moments=[{"timestamp": "12:00", "description": "anything"}])
    assert not any("key moment" in x.check for x in _check(d, b))


def test_unfindable_concept_bounces():
    d = _draft(
        key_concepts=["three-file loop: work script", "borrow checker: never mentioned here"]
    )
    bounces = _check(d)
    assert any(b.check == "concept grounding" for b in bounces)
    assert "borrow checker" in next(b for b in bounces if b.check == "concept grounding").detail


def test_no_concepts_bounces():
    bounces = _check(_draft(key_concepts=[]))
    assert any(b.check == "concept count" for b in bounces)


def test_unvocabulary_tag_without_reason_bounces():
    d = _draft(interest_tags=["ai-agents", "loop-engineering"])
    bounces = _check(d)
    assert any(b.check == "tag vocabulary" for b in bounces)


def test_new_tag_with_reason_passes():
    d = _draft(
        interest_tags=["ai-agents", "loop-engineering"],
        new_tags=[NewTag(tag="loop-engineering", reason="no existing tag covers loop design")],
    )
    assert not any(b.check == "tag vocabulary" for b in _check(d))


def test_derived_rec_tags_are_exempt():
    d = _draft(
        interest_tags=["ai-agents", "book-rec"],
        recommendations=[{"kind": "book", "title": "X"}],
    )
    assert not any(b.check == "tag vocabulary" for b in _check(d))


def test_missing_take_response_bounces_only_when_take_exists():
    d = _draft(take_response=None)
    assert any(b.check == "take response" for b in _check(d))
    assert not any(b.check == "take response" for b in _check(d, take_kind=None, take_text=None))
    # reflex takes ("just want it") omit the section, not fake it
    assert not any(
        b.check == "take response" for b in _check(d, take_kind="reflex", take_text="$$")
    )


def test_near_duplicate_bounces_above_baseline():
    high = _check(_draft(), neighbor_cosine=grader.NEAR_DUP_BASELINE + 0.01)
    assert any(b.check == "near duplicate" for b in high)
    low = _check(_draft(), neighbor_cosine=grader.NEAR_DUP_BASELINE - 0.05)
    assert not any(b.check == "near duplicate" for b in low)
    assert not any(b.check == "near duplicate" for b in _check(_draft(), neighbor_cosine=None))


def test_grade_model_reads_rubric_and_returns_verdict(monkeypatch):
    from ytk import rubric as rubric_mod
    from ytk import sdk

    calls = []

    def fake(system, user, schema, *, add_dirs=None, max_turns=20, model=None):
        calls.append({"system": system, "user": user, "model": model})
        return sdk.StructuredResult(
            data={
                "passed": False,
                "bounces": [
                    {"check": "Thesis", "detail": "could attach to any video", "where": "thesis"}
                ],
                "spot_checks": [
                    {"claim": "ripgrep scans rules", "grounded": True, "where": "transcript"}
                ],
            },
            model=model,
            tokens=900,
            duration_ms=3000,
            usage=None,
        )

    monkeypatch.setattr(sdk, "call_structured", fake)
    verdict, res = grader.grade_model(
        _draft(), _bundle(), rubric_mod.load().text, take_text="why loops beat cron"
    )
    assert not verdict.passed
    assert verdict.bounces[0].check == "Thesis"
    assert res.tokens == 900
    # the conftest stub rubric reaches the grader's prompt — and only the grader's
    assert "No filler" in calls[0]["system"]
    assert "why loops beat cron" in calls[0]["user"]
    assert calls[0]["model"] == grader.GRADER_MODEL


def test_grader_and_enricher_share_no_prompt():
    from ytk import enricher as e

    assert grader.GRADER_PROMPT_VERSION != e.PROMPT_VERSION
    assert "research assistant" not in grader._GRADE_SYSTEM
