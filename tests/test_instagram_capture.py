"""capture_reel_media: frames + transcript from the downloaded MP4, with a
hard lifecycle guarantee — the temp video is always deleted."""

from __future__ import annotations

import io

import pytest
from PIL import Image

import ytk.instagram as instagram_mod
from ytk.instagram import InstagramPost, capture_reel_media
from ytk.transcript import TranscriptionResult
from ytk.vision import TimedFrame, nearest_frames


def _jpeg(seed: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 18), (seed * 11 % 256, 40, 40)).save(buf, format="JPEG")
    return buf.getvalue()


def _reel(video_path):
    return InstagramPost(
        url="https://www.instagram.com/reel/SC/",
        username="u",
        timestamp="2026-07-15",
        caption="c",
        images=[],
        video_path=video_path,
        media_kind="video",
    )


@pytest.fixture
def mp4(tmp_path):
    f = tmp_path / "reel.mp4"
    f.write_bytes(b"fake")
    return f


def test_success_path_transcribes_local_file_and_unlinks(monkeypatch, mp4):
    seen = {}

    def fake_transcribe(path, whisper_model="base"):
        seen["path"] = path
        seen["exists_at_transcribe_time"] = path.exists()
        seen["model"] = whisper_model
        return TranscriptionResult(
            segments=[{"start": 0, "duration": 1.0, "text": "hi"}], status="ok"
        )

    monkeypatch.setattr(instagram_mod, "transcribe_file", fake_transcribe)
    tier = [TimedFrame(t=2.0 * i, data=_jpeg(i)) for i in range(21)]  # 42 s at 2 s
    monkeypatch.setattr(instagram_mod, "extract_frame_tier", lambda p, plan, duration: tier)
    monkeypatch.setattr(instagram_mod, "probe_duration", lambda p: 42.0)

    cap = capture_reel_media(_reel(mp4), whisper_model="small")

    assert seen["path"] == mp4
    assert seen["exists_at_transcribe_time"]
    assert seen["model"] == "small"
    # one ffmpeg pass: the four baseline frames are picked from the tier
    assert cap.dense_frames == tier
    assert cap.ruler == "time"
    assert [f.t for f in nearest_frames(tier, [8.4, 16.8, 25.2, 33.6])] == [8.0, 16.0, 26.0, 34.0]
    assert cap.frame_bytes == [_jpeg(4), _jpeg(8), _jpeg(13), _jpeg(17)]
    assert cap.sheet_bytes and cap.sheet_bytes[:2] == b"\xff\xd8"
    assert cap.transcript_status == "ok"
    assert cap.transcript_segments[0]["text"] == "hi"
    assert cap.duration == 42.0
    assert cap.warnings == []
    assert not mp4.exists()  # deleted in the outer finally


def test_no_video_path_is_skipped_with_warning():
    cap = capture_reel_media(_reel(None))
    assert cap.transcript_status == "skipped"
    assert cap.frame_bytes == []
    assert any("video" in w.lower() for w in cap.warnings)


@pytest.fixture(autouse=True)
def tier_unavailable(request, monkeypatch):
    """Every test below the success path exercises the fallback: the dense
    tier raises, and the sparse extract_frames path must still run."""
    if "success_path" in request.node.name:
        return

    def no_tier(p, plan, duration):
        raise RuntimeError("tier exploded")

    monkeypatch.setattr(instagram_mod, "extract_frame_tier", no_tier)


def test_tier_failure_falls_back_to_sparse_frames_with_a_warning(monkeypatch, mp4):
    monkeypatch.setattr(instagram_mod, "extract_frames", lambda p, timestamps, baseline_n=4: [b"f"])
    monkeypatch.setattr(instagram_mod, "probe_duration", lambda p: 10.0)
    monkeypatch.setattr(
        instagram_mod,
        "transcribe_file",
        lambda p, whisper_model="base": TranscriptionResult(segments=[], status="no_speech"),
    )
    cap = capture_reel_media(_reel(mp4))
    assert cap.frame_bytes == [b"f"]
    assert cap.dense_frames == [] and cap.sheet_bytes is None
    assert any("tier exploded" in w for w in cap.warnings)


def test_frame_extraction_failure_still_transcribes_and_unlinks(monkeypatch, mp4):
    def boom(p, timestamps, baseline_n=4):
        raise RuntimeError("ffmpeg exploded")

    monkeypatch.setattr(instagram_mod, "extract_frames", boom)
    monkeypatch.setattr(instagram_mod, "probe_duration", lambda p: None)
    monkeypatch.setattr(
        instagram_mod,
        "transcribe_file",
        lambda p, whisper_model="base": TranscriptionResult(
            segments=[{"start": 0, "duration": 1.0, "text": "x"}], status="ok"
        ),
    )
    cap = capture_reel_media(_reel(mp4))
    assert cap.frame_bytes == []
    assert cap.transcript_status == "ok"
    assert any("frame" in w.lower() for w in cap.warnings)
    assert not mp4.exists()


def test_zero_frames_is_warned(monkeypatch, mp4):
    monkeypatch.setattr(instagram_mod, "extract_frames", lambda p, timestamps, baseline_n=4: [])
    monkeypatch.setattr(instagram_mod, "probe_duration", lambda p: 10.0)
    monkeypatch.setattr(
        instagram_mod,
        "transcribe_file",
        lambda p, whisper_model="base": TranscriptionResult(segments=[], status="no_speech"),
    )
    cap = capture_reel_media(_reel(mp4))
    assert any("frame" in w.lower() for w in cap.warnings)
    assert cap.transcript_status == "no_speech"


def test_transcription_failure_is_warned_and_frames_kept(monkeypatch, mp4):
    monkeypatch.setattr(instagram_mod, "extract_frames", lambda p, timestamps, baseline_n=4: [b"f"])
    monkeypatch.setattr(instagram_mod, "probe_duration", lambda p: 10.0)
    monkeypatch.setattr(
        instagram_mod,
        "transcribe_file",
        lambda p, whisper_model="base": TranscriptionResult(
            segments=[], status="failed", error="cuda exploded"
        ),
    )
    cap = capture_reel_media(_reel(mp4))
    assert cap.frame_bytes == [b"f"]
    assert cap.transcript_status == "failed"
    assert any("cuda exploded" in w for w in cap.warnings)
    assert not mp4.exists()


def test_mp4_unlinked_even_if_everything_raises(monkeypatch, mp4):
    def boom(*a, **kw):
        raise RuntimeError("total meltdown")

    monkeypatch.setattr(instagram_mod, "extract_frames", boom)
    monkeypatch.setattr(instagram_mod, "probe_duration", boom)
    monkeypatch.setattr(instagram_mod, "transcribe_file", boom)
    cap = capture_reel_media(_reel(mp4))
    assert not mp4.exists()
    assert cap.transcript_status == "failed"
    assert cap.warnings
