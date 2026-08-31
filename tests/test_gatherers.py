"""Per-source evidence gatherers (#197 P2): thin composition over the
existing fetchers, mapped into EvidenceBundle quality fields."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ytk import gatherers
from ytk.ingest import WebContent
from ytk.instagram import InstagramPost, ReelCapture
from ytk.transcript import TranscriptEvidence


@pytest.fixture(autouse=True)
def evidence_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_EVIDENCE", str(tmp_path / "evidence"))
    return tmp_path


def test_every_capture_source_has_a_gatherer():
    from ytk import evidence

    for source in ("youtube", "instagram", "web", "tiktok", "reddit", "pinterest"):
        assert source in evidence.GATHERERS


def test_youtube_maps_quality_and_description():
    ev = TranscriptEvidence(
        segments=[{"start": 0, "duration": 2, "text": "hi"}],
        origin="api-auto",
        language="en",
        status="ok",
    )
    with (
        patch("ytk.gatherers.fetch_metadata", return_value={"title": "T", "description": "D"}),
        patch("ytk.gatherers.fetch_transcript_evidence", return_value=ev),
        patch("ytk.gatherers.hint_detect", return_value=[12.0]),
    ):
        b = gatherers.gather_youtube("https://y/1", None)
    assert b.transcript_origin == "api-auto"
    assert b.transcript_language == "en"
    assert b.description == "D"
    assert b.frames == []
    assert any("frames" in g for g in b.gaps)


def test_instagram_carries_caption_and_frames(tmp_path):
    post = InstagramPost(
        url="https://www.instagram.com/reel/x/",
        username="u",
        timestamp="2026-01-01",
        caption="the caption",
        video_path=Path("/tmp/fake.mp4"),
        media_kind="video",
    )
    cap = ReelCapture(
        frame_bytes=[b"jpegbytes"],
        transcript_segments=[{"start": 0, "duration": 1, "text": "fala"}],
        transcript_status="ok",
    )
    with (
        patch("ytk.gatherers.fetch_instagram", return_value=post),
        patch("ytk.gatherers.capture_reel_media", return_value=cap),
    ):
        b = gatherers.gather_instagram("https://www.instagram.com/reel/x/", None)
    assert b.caption == "the caption"
    assert b.transcript_status == "ok"
    assert len(b.frames) == 1
    assert Path(b.frames[0]).read_bytes() == b"jpegbytes"


def test_web_strips_boilerplate():
    content = WebContent(
        url="https://w/1",
        title="A",
        author="",
        date="",
        text="Accept all cookies\nThe real article.",
    )
    with patch("ytk.gatherers.fetch_web", return_value=content):
        b = gatherers.gather_web("https://w/1", None)
    assert b.text is not None
    assert "cookies" not in b.text
    assert "The real article." in b.text
    assert b.transcript_origin == "none"
