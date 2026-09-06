"""The grader's deterministic layer (#197 P4): code only, every draft,
spends no model call, bounces with the failing check named."""

import json
from dataclasses import asdict

import pytest

from ytk import attempt as A
from ytk import grader
from ytk import view as V
from ytk.enricher import EnrichmentV2, NewTag
from ytk.evidence import EvidenceBundle, evidence_dir


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


def _view(bundle=None, budget=V.DEFAULT_BUDGET) -> V.View:
    out = evidence_dir() / "7.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(bundle or _bundle())))
    return V.build_view(7, out, budget)


def _attempt(view, take_text="why loops beat cron", n=1, findings=None, previous=None):
    take = {"id": 1, "kind": "intent", "text": take_text} if take_text else None
    return A.open_attempt(7, n, view, take=take, previous=previous, findings_in=findings or [])


def _check(draft, bundle=None, **kw):
    kw.setdefault("vocab", VOCAB)
    kw.setdefault("take_kind", "intent")
    kw.setdefault("take_text", "why loops beat cron")
    return grader.deterministic_checks(draft, _view(bundle), **kw)


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
    v = _view()
    verdict, res = grader.grade_model(_draft(), v, _attempt(v), rubric_mod.load().text)
    assert not verdict.passed
    assert verdict.bounces[0].check == "Thesis"
    assert res.tokens == 900
    # the conftest stub rubric reaches the grader's prompt — and only the grader's
    assert "No filler" in calls[0]["system"]
    assert "why loops beat cron" in calls[0]["user"]
    assert v.rendered in calls[0]["user"]
    assert calls[0]["model"] == grader.GRADER_MODEL


def test_grader_and_enricher_share_no_prompt():
    from ytk import enricher as e

    assert grader.GRADER_PROMPT_VERSION != e.PROMPT_VERSION
    assert "research assistant" not in grader._GRADE_SYSTEM
    assert "EVERY section that" in grader._GRADE_SYSTEM


class TestGroundingNormalization:
    """#201: a hyphenated near-verbatim coinage must ground; smuggled world
    knowledge must still bounce. Reproduced live on item 755."""

    def test_hyphenated_concept_grounds_against_unhyphenated_transcript(self):
        b = _bundle(
            transcript=[
                {"start": 0, "duration": 4, "text": "deep learning is a very empirical field"},
                {"start": 4, "duration": 4, "text": "things are flat-out wrong and janky"},
            ]
        )
        d = _draft(
            key_concepts=["Empirical-field framing: why the papers read like lab notes"],
            key_moments=[],
        )
        assert [x for x in _check(d, b) if x.check == "concept grounding"] == []

    def test_transcript_hyphen_grounds_unhyphenated_concept(self):
        b = _bundle(
            transcript=[
                {"start": 0, "duration": 4, "text": "the flat-out claim ships anyway"},
            ]
        )
        d = _draft(key_concepts=["flat out: shipped without review"], key_moments=[])
        assert [x for x in _check(d, b) if x.check == "concept grounding"] == []

    def test_accented_transcript_grounds_unaccented_concept(self):
        """Item 758: Whisper wrote "omertà", the draft wrote "omerta", and
        the ASCII word regex bounced a concept spoken on the record."""
        b = _bundle(
            transcript=[
                {"start": 0, "duration": 4, "text": "the mafia would be jealous of this omertà"},
            ]
        )
        d = _draft(key_concepts=["omerta: the agents' collective silence"], key_moments=[])
        assert [x for x in _check(d, b) if x.check == "concept grounding"] == []

    def test_smuggled_world_knowledge_still_bounces(self):
        d = _draft(
            key_concepts=["Jawed Karim: uploaded the first video"],
            key_moments=[],
        )
        bounces = [x for x in _check(d) if x.check == "concept grounding"]
        assert len(bounces) == 1
        assert "Jawed Karim" in bounces[0].detail


class TestGraderEvidence:
    """The judge reads the packet the writer read: same rendered bytes, same
    shown frames, same mounts. Half of item 756's objections were the
    grader's own blindness quoting the rubric (2026-08-31)."""

    def test_rendered_transcript_carries_timestamps(self):
        v = _view(
            _bundle(
                transcript=[
                    {"start": 0, "duration": 3, "text": "we built a three-file loop for agents"},
                    {"start": 400, "duration": 3, "text": "ripgrep scans the rules markdown fast"},
                ]
            )
        )
        assert "[0:00] we built a three-file loop for agents" in v.rendered
        assert "[6:40] ripgrep scans the rules markdown fast" in v.rendered

    def test_grade_model_shows_the_views_frames_and_mounts(self, tmp_path, monkeypatch):
        from ytk import sdk

        frames = []
        for i in range(4):
            f = tmp_path / f"frame-{i}.jpg"
            f.write_bytes(b"jpeg")
            frames.append(str(f))
        v = _view(_bundle(frames=frames))
        seen = {}

        def fake(system, user, schema, *, add_dirs=None, max_turns=20, model=None):
            seen["user"] = user
            seen["add_dirs"] = add_dirs
            return sdk.StructuredResult(
                data={"passed": True, "bounces": [], "spot_checks": []},
                model=model,
                tokens=10,
                duration_ms=5,
                usage=None,
            )

        monkeypatch.setattr(sdk, "call_structured", fake)
        grader.grade_model(_draft(), v, _attempt(v), "rubric text")
        listed = [ln for ln in seen["user"].splitlines() if "frame-" in ln]
        assert len(listed) == v.budget["frames_shown"] == 2
        assert seen["add_dirs"] == v.mounts == [str(tmp_path)]

    def test_grade_model_without_frames_grants_no_dirs(self, monkeypatch):
        from ytk import sdk

        seen = {}

        def fake(system, user, schema, *, add_dirs=None, max_turns=20, model=None):
            seen["add_dirs"] = add_dirs
            return sdk.StructuredResult(
                data={"passed": True, "bounces": [], "spot_checks": []},
                model=model,
                tokens=10,
                duration_ms=5,
                usage=None,
            )

        monkeypatch.setattr(sdk, "call_structured", fake)
        v = _view()
        grader.grade_model(_draft(), v, _attempt(v), "rubric text")
        assert not seen["add_dirs"]

    def test_teacher_is_told_what_it_asked_for_last_round(self, monkeypatch):
        """Item 759: the teacher asked for an insight, then bounced it as a
        duplicate. The attempt header carries its own findings back."""
        from ytk import sdk

        seen = {}

        def fake(system, user, schema, *, add_dirs=None, max_turns=20, model=None):
            seen["system"] = system
            seen["user"] = user
            return sdk.StructuredResult(
                data={"passed": True, "bounces": [], "spot_checks": []},
                model=model,
                tokens=10,
                duration_ms=5,
                usage=None,
            )

        monkeypatch.setattr(sdk, "call_structured", fake)
        v = _view()
        a = _attempt(
            v, n=2, findings=[{"check": "Insights", "detail": "add the service-worker gotcha"}]
        )
        grader.grade_model(_draft(), v, a, "rubric text")
        assert "not a new objection" in seen["system"]
        assert "Insights: add the service-worker gotcha" in seen["user"]


class TestPacketUnits:
    """Claims cite packet units; the spell-checker reads the id set and the
    grounding text, nothing else (#212)."""

    def test_concept_read_off_a_shown_frame_is_not_ungrounded(self, tmp_path):
        """Items 489 and 534 (2026-09-06): names read off the screen bounced
        at the deterministic layer because it only had the transcript."""
        f = tmp_path / "frame-0.jpg"
        f.write_bytes(b"jpeg")
        d = _draft(key_concepts=["Armature rigging: bones drawn over the puppet [frame:001]"])
        assert [x for x in _check(d, _bundle(frames=[str(f)])) if "concept" in x.check] == []

    def test_concept_citing_a_unit_outside_the_packet_bounces(self, tmp_path):
        d = _draft(key_concepts=["Armature rigging: bones drawn over the puppet [frame:009]"])
        bounces = [x for x in _check(d) if x.check == "cites unknown unit"]
        assert len(bounces) == 1 and "frame:009" in bounces[0].detail

    def test_moment_past_the_cut_bounces_as_outside_the_packet(self):
        seg = [{"start": i, "duration": 1, "text": "word " * 20} for i in range(9000)]
        d = _draft(
            key_moments=[{"timestamp": "2:20:00", "description": "word word"}],
            key_concepts=["word: said a lot"],
        )
        bounces = _check(d, _bundle(transcript=seg, duration=9000))
        assert any(x.check == "cites outside the packet" for x in bounces)
        assert not any(x.check == "key moment adjacency" for x in bounces)


def test_long_evidence_is_kept_whole_and_a_cut_is_announced():
    """Item 215: an 80k cap silently dropped the back half of a lecture and
    the judge bounced it as ungrounded. The cut now lives in the packet."""
    seg = [{"start": i, "duration": 1, "text": "word " * 20} for i in range(3000)]
    v = _view(_bundle(transcript=seg))
    assert len(v.rendered) > 80_000 and "not in this packet" not in v.rendered
    huge = _view(_bundle(transcript=seg * 3))
    assert "neither cite nor bounce them" in huge.rendered
