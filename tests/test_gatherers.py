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
    assert b.uploader == "u"  # the handle is the author, never the note's title
    assert b.transcript_status == "ok"
    assert len(b.frames) == 1
    assert Path(b.frames[0]).read_bytes() == b"jpegbytes"


def test_instagram_reel_bundle_carries_dense_tier_and_sheet(tmp_path):
    from ytk.vision import TimedFrame

    post = InstagramPost(
        url="https://www.instagram.com/reel/x/",
        username="u",
        timestamp="2026-01-01",
        caption="c",
        video_path=Path("/tmp/fake.mp4"),
        media_kind="video",
    )
    cap = ReelCapture(
        frame_bytes=[b"base"],
        dense_frames=[TimedFrame(t=0.0, data=b"d0"), TimedFrame(t=2.0, data=b"d1")],
        sheet_bytes=b"sheet",
        ruler="time",
        transcript_segments=[{"start": 0, "duration": 1, "text": "fala"}],
        transcript_status="ok",
    )
    with (
        patch("ytk.gatherers.fetch_instagram", return_value=post),
        patch("ytk.gatherers.capture_reel_media", return_value=cap),
    ):
        b = gatherers.gather_instagram(post.url, None)
    assert [d["t"] for d in b.dense_frames] == [0.0, 2.0]
    assert Path(b.dense_frames[1]["path"]).read_bytes() == b"d1"
    assert Path(b.dense_frames[1]["path"]).name == "f-001.jpg"
    assert b.sheet and Path(b.sheet).name == "sheet.jpg"
    assert Path(b.sheet).read_bytes() == b"sheet"
    assert b.frame_ruler == "time"
    # the sparse frames the enricher sees live in their own directory: the
    # model mounts that directory and must not reach the tier or the sheet
    assert len(b.frames) == 1 and "/shown/" in b.frames[0]
    shown_dir = Path(b.frames[0]).parent
    assert not Path(b.dense_frames[0]["path"]).is_relative_to(shown_dir)
    assert not Path(b.sheet).is_relative_to(shown_dir)
    # the timed transcript rides in the bundle next to the frames
    assert b.transcript[0]["start"] == 0


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


def test_youtube_carries_note_and_grader_metadata():
    """P4: the timestamp check needs duration; the note writer needs
    uploader/upload_date/thumbnail/id without a refetch."""
    ev = TranscriptEvidence(
        segments=[{"start": 0, "duration": 2, "text": "hi"}],
        origin="api-manual",
        language="en",
        status="ok",
    )
    meta = {
        "id": "abc123xyz00",
        "title": "T",
        "description": "D",
        "uploader": "Someone",
        "upload_date": "20260830",
        "duration": 613,
        "thumbnail": "https://i.ytimg.com/vi/abc123xyz00/hq.jpg",
        "chapters": [{"start_time": 0, "title": "intro"}],
    }
    with (
        patch("ytk.gatherers.fetch_metadata", return_value=meta),
        patch("ytk.gatherers.fetch_transcript_evidence", return_value=ev),
        patch("ytk.gatherers.hint_detect", return_value=[]),
    ):
        b = gatherers.gather_youtube("https://y/1", None)
    assert b.media_id == "abc123xyz00"
    assert b.uploader == "Someone"
    assert b.upload_date == "20260830"
    assert b.duration == 613
    assert b.thumbnail == "https://i.ytimg.com/vi/abc123xyz00/hq.jpg"
    assert b.chapters == [{"start_time": 0, "title": "intro"}]


def test_bundle_metadata_defaults_tolerate_p2_era_bundles():
    from ytk.evidence import EvidenceBundle

    b = EvidenceBundle(
        source="web",
        url="https://x",
        title=None,
        transcript=[],
        transcript_origin="none",
        transcript_language=None,
        transcript_status="none",
    )
    assert b.duration is None
    assert b.media_id is None
    assert b.chapters == []


def test_load_bundle_round_trips_and_tolerates_old_json(tmp_path):
    import json
    from dataclasses import asdict

    from ytk.evidence import EvidenceBundle, load_bundle

    b = EvidenceBundle(
        source="youtube",
        url="https://y/1",
        title="T",
        transcript=[{"start": 0, "duration": 2, "text": "hi"}],
        transcript_origin="api-manual",
        transcript_language="en",
        transcript_status="ok",
        duration=613,
    )
    p = tmp_path / "b.json"
    p.write_text(json.dumps(asdict(b)))
    assert load_bundle(p) == b

    old = asdict(b)
    for key in ("media_id", "uploader", "upload_date", "duration", "thumbnail", "chapters"):
        old.pop(key)
    old["future_field"] = 1
    p.write_text(json.dumps(old))
    loaded = load_bundle(p)
    assert loaded.duration is None
    assert loaded.url == "https://y/1"


def test_instagram_reel_carries_thumbnail(tmp_path):
    post = InstagramPost(
        url="https://www.instagram.com/reel/x/",
        username="u",
        timestamp="2026-01-01",
        caption="c",
        video_path=Path("/tmp/fake.mp4"),
        thumbnail_url="https://cdn/cover.jpg",
        media_kind="video",
    )
    cap = ReelCapture(frame_bytes=[], transcript_segments=[], transcript_status="none")

    def fake_download(url, dest):
        dest.write_bytes(b"img")
        return dest

    with (
        patch("ytk.gatherers.fetch_instagram", return_value=post),
        patch("ytk.gatherers.capture_reel_media", return_value=cap),
        patch("ytk.gatherers._download_image", side_effect=fake_download),
    ):
        b = gatherers.gather_instagram(post.url, None)
    # Downloaded at read time: IG CDN URLs expire within days (coverless cards).
    assert b.thumbnail is not None and not b.thumbnail.startswith("http")
    assert Path(b.thumbnail).is_file()
    assert "/thumbs/" in b.thumbnail


def test_instagram_carousel_downloads_images_to_local_files(tmp_path):
    post = InstagramPost(
        url="https://www.instagram.com/p/x/",
        username="u",
        timestamp="2026-01-01",
        caption="c",
        images=["https://cdn/a.jpg", "https://cdn/b.jpg"],
        media_kind="carousel",
    )

    def fake_download(url, dest):
        dest.write_bytes(b"img")
        return dest

    with (
        patch("ytk.gatherers.fetch_instagram", return_value=post),
        patch("ytk.gatherers._download_image", side_effect=fake_download),
    ):
        b = gatherers.gather_instagram(post.url, None)
    assert len(b.frames) == 2
    for p in b.frames:
        assert Path(p).is_file()
    assert b.thumbnail is not None and Path(b.thumbnail).is_file()


def test_instagram_image_download_failure_lands_in_gaps_not_urls_in_frames(tmp_path):
    post = InstagramPost(
        url="https://www.instagram.com/p/y/",
        username="u",
        timestamp="2026-01-01",
        caption="c",
        images=["https://cdn/a.jpg"],
        media_kind="image",
    )

    def boom(url, dest):
        raise OSError("cdn said no")

    with (
        patch("ytk.gatherers.fetch_instagram", return_value=post),
        patch("ytk.gatherers._download_image", side_effect=boom),
    ):
        b = gatherers.gather_instagram(post.url, None)
    assert b.frames == []
    assert any("image download failed" in g for g in b.gaps)


def test_instagram_thumbnail_download_failure_falls_back_to_url(tmp_path):
    post = InstagramPost(
        url="https://www.instagram.com/reel/z/",
        username="u",
        timestamp="2026-01-01",
        caption="c",
        video_path=Path("/tmp/fake.mp4"),
        thumbnail_url="https://cdn/cover.jpg",
        media_kind="video",
    )
    cap = ReelCapture(frame_bytes=[], transcript_segments=[], transcript_status="none")

    def boom(url, dest):
        raise OSError("cdn said no")

    with (
        patch("ytk.gatherers.fetch_instagram", return_value=post),
        patch("ytk.gatherers.capture_reel_media", return_value=cap),
        patch("ytk.gatherers._download_image", side_effect=boom),
    ):
        b = gatherers.gather_instagram(post.url, None)
    assert b.thumbnail == "https://cdn/cover.jpg"
    assert any("thumbnail download failed" in g for g in b.gaps)
