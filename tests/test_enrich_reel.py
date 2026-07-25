"""Reel enrichment prompt: video-aware, truthful about capture, no carousel framing."""

import pytest

import ytk.enrich as enrich_mod
from ytk.enrich import SOURCE_BIAS, enrich_instagram_reel

_RESULT = {
    "thesis": "t",
    "summary": "s",
    "key_concepts": [],
    "insights": [],
    "interest_tags": ["ai"],
    "key_moments": [],
}


@pytest.fixture
def captured(monkeypatch):
    calls = {}

    def fake_run(system, user, schema, add_dirs=None):
        calls["system"] = system
        calls["user"] = user
        return dict(_RESULT)

    monkeypatch.setattr(enrich_mod, "run_structured", fake_run)
    return calls


def _segments():
    return [
        {"start": 0.0, "duration": 3.0, "text": "build an app"},
        {"start": 62.0, "duration": 2.0, "text": "deploy it"},
    ]


def test_reel_bias_exists_and_talks_video_frames_not_slides():
    bias = SOURCE_BIAS["instagram_reel"]
    assert "sampled video frames" in bias
    assert "carousel" not in bias.lower() or "not carousel" in bias.lower()
    assert "EVERY" in bias


def test_reel_bias_separates_evidence_from_inference():
    bias = SOURCE_BIAS["instagram_reel"]
    assert "shown or spoken" in bias


def test_reel_prompt_carries_transcript_frames_and_no_slide_count(captured):
    enrich_instagram_reel(
        caption="my caption",
        username="elif.codes",
        duration=65.0,
        frame_count=4,
        transcript_segments=_segments(),
        transcript_status="ok",
    )
    user = captured["user"]
    assert "Slide count" not in user
    assert "@elif.codes" in user
    assert "reel" in user.lower()
    assert "4" in user
    assert "build an app" in user
    assert "[1:02]" in user  # timestamps preserved
    assert "my caption" in user
    assert SOURCE_BIAS["instagram_reel"] in captured["system"]


def test_reel_prompt_states_no_speech_plainly(captured):
    enrich_instagram_reel(
        caption="c",
        username="u",
        duration=None,
        frame_count=4,
        transcript_segments=[],
        transcript_status="no_speech",
    )
    assert "no speech" in captured["user"].lower()
    assert "failed" not in captured["user"].lower()


def test_reel_prompt_reports_transcription_failure_not_empty_video(captured):
    enrich_instagram_reel(
        caption="c",
        username="u",
        duration=None,
        frame_count=4,
        transcript_segments=[],
        transcript_status="failed",
    )
    assert "transcription failed" in captured["user"].lower()


def test_reel_prompt_reports_frame_extraction_failure(captured):
    enrich_instagram_reel(
        caption="c",
        username="u",
        duration=None,
        frame_count=0,
        transcript_segments=_segments(),
        transcript_status="ok",
    )
    assert "frame extraction failed" in captured["user"].lower()


def test_carousel_prompt_is_untouched(captured):
    enrich_mod.enrich_instagram(caption="cap", username="u", slide_count=3, visual_blocks=[])
    assert "Slide count: 3" in captured["user"]
