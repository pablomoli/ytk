"""Reel notes persist transcript, frames, and structural capture metadata."""

from __future__ import annotations

import pytest

from ytk.enrich import Enrichment
from ytk.instagram import InstagramPost
from ytk.vault import write_instagram_note


@pytest.fixture
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    return tmp_path


def _enrichment():
    return Enrichment(
        thesis="A dev shows a build.",
        summary="s",
        key_concepts=[],
        insights=[],
        interest_tags=["ai-coding"],
        key_moments=[],
    )


def _reel_post():
    return InstagramPost(
        url="https://www.instagram.com/reel/SC123/",
        username="elif.codes",
        timestamp="2026-07-15",
        caption="Comment judge",
        images=[],
        media_kind="video",
    )


def test_reel_note_persists_transcript_frames_and_capture_metadata(brain):
    segments = [
        {"start": 0.0, "duration": 3.0, "text": "build an app"},
        {"start": 62.0, "duration": 2.0, "text": "deploy it"},
    ]
    path = write_instagram_note(
        _reel_post(),
        _enrichment(),
        transcript_segments=segments,
        transcript_status="ok",
        frame_bytes=[b"jpeg1", b"jpeg2"],
    )
    content = path.read_text(encoding="utf-8")

    assert "media: video" in content
    assert "capture_schema: 2" in content
    assert "frames: 2" in content
    assert "transcript: ok" in content

    assert "## Transcript" in content
    assert "<details>" in content
    assert "[0:00] build an app" in content
    assert "[1:02] deploy it" in content

    # basenames must be vault-unique: Obsidian resolves ![[name]] by filename
    # across the whole vault, so bare frame-1.jpg collides between notes
    frame_dir = brain / "sources" / "instagram" / "frames" / "SC123"
    assert (frame_dir / "SC123-frame-1.jpg").read_bytes() == b"jpeg1"
    assert (frame_dir / "SC123-frame-2.jpg").read_bytes() == b"jpeg2"
    assert "frames/SC123/SC123-frame-1.jpg" in content  # image_paths entry
    assert "![[SC123-frame-1.jpg]]" in content
    assert "![[frame-1.jpg]]" not in content


def test_reel_note_no_speech_omits_transcript_section(brain):
    path = write_instagram_note(
        _reel_post(),
        _enrichment(),
        transcript_segments=[],
        transcript_status="no_speech",
        frame_bytes=[b"j"],
    )
    content = path.read_text(encoding="utf-8")
    assert "transcript: no_speech" in content
    assert "## Transcript" not in content


def test_reel_note_records_transcription_failure(brain):
    path = write_instagram_note(
        _reel_post(),
        _enrichment(),
        transcript_segments=[],
        transcript_status="failed",
        frame_bytes=[],
    )
    content = path.read_text(encoding="utf-8")
    assert "transcript: failed" in content
    assert "frames: 0" in content


def test_carousel_note_gets_schema_stamp_without_video_keys(brain):
    post = InstagramPost(
        url="https://www.instagram.com/p/CAR1/",
        username="u",
        timestamp="2026-07-15",
        caption="c",
        images=[],
        media_kind="carousel",
    )
    path = write_instagram_note(post, _enrichment())
    content = path.read_text(encoding="utf-8")
    assert "media: carousel" in content
    assert "capture_schema: 2" in content
    assert "transcript:" not in content
    assert "frames:" not in content
