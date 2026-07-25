from pathlib import Path
from unittest.mock import MagicMock, patch

from ytk.transcript import _fetch_via_whisper, fetch_transcript


class _FakeSeg:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


def _fake_segments():
    return [
        _FakeSeg(0.0, 5.0, "Hello world"),
        _FakeSeg(5.0, 10.0, "Second segment"),
    ], MagicMock(language="en")


def test_whisper_segments_have_timestamps(tmp_path):
    """_fetch_via_whisper converts faster-whisper segments to {start, duration, text}."""
    audio_file = tmp_path / "audio.m4a"
    audio_file.write_bytes(b"fake")

    with (
        patch("ytk.transcript._download_audio", return_value=audio_file),
        patch("ytk.transcript.WhisperModel") as MockModel,
    ):
        MockModel.return_value.transcribe.return_value = _fake_segments()
        segments, source = _fetch_via_whisper("https://youtu.be/test123", whisper_model="base")

    assert source == "whisper"
    assert segments[0] == {"start": 0.0, "duration": 5.0, "text": "Hello world"}
    assert segments[1] == {"start": 5.0, "duration": 5.0, "text": "Second segment"}


def test_fetch_transcript_falls_back_to_whisper():
    """When youtube-transcript-api fails, fetch_transcript calls Whisper."""
    from youtube_transcript_api import NoTranscriptFound

    with (
        patch("ytk.transcript._fetch_via_api", side_effect=NoTranscriptFound("x", ["en"], None)),
        patch("ytk.transcript._fetch_via_whisper", return_value=([], "whisper")) as mock_whisper,
    ):
        segments, source = fetch_transcript("https://youtu.be/abc12345678")

    mock_whisper.assert_called_once()
    assert source == "whisper"


def test_fetch_transcript_falls_back_on_ip_block():
    """When YouTube IP-blocks the transcript endpoint, fetch_transcript falls back to Whisper."""
    from youtube_transcript_api import IpBlocked

    with (
        patch("ytk.transcript._fetch_via_api", side_effect=IpBlocked("abc12345678")),
        patch("ytk.transcript._fetch_via_whisper", return_value=([], "whisper")) as mock_whisper,
    ):
        segments, source = fetch_transcript("https://youtu.be/abc12345678")

    mock_whisper.assert_called_once()
    assert source == "whisper"


def test_fetch_transcript_no_ytdlp_subtitle_tier():
    """The old yt-dlp subtitle tier is gone — only two tiers exist."""
    import ytk.transcript as t

    assert not hasattr(t, "_fetch_via_ytdlp"), "yt-dlp subtitle tier should be removed"


# --- audio cache pruning (ytk gc) ---
import os
from datetime import datetime, timedelta

from ytk.transcript import prune_audio_cache


def _touch(path: Path, days_old: float) -> Path:
    path.write_bytes(b"x" * 10)
    ts = (datetime.now() - timedelta(days=days_old)).timestamp()
    os.utime(path, (ts, ts))
    return path


def test_prune_removes_old_yt_cache_only(tmp_path):
    """Prunes top-level yt_* files older than the cutoff; leaves fresh ones."""
    old = _touch(tmp_path / "yt_abc123.m4a", days_old=40)
    fresh = _touch(tmp_path / "yt_def456.m4a", days_old=2)

    removed = prune_audio_cache(max_age_days=30, cache_dir=tmp_path)

    assert removed == [old]
    assert not old.exists()
    assert fresh.exists()


def test_prune_never_touches_memos_or_snaps(tmp_path):
    """Voice memos and snaps live in subdirs and must never be pruned, even if old."""
    (tmp_path / "memos").mkdir()
    (tmp_path / "snaps").mkdir()
    memo = _touch(tmp_path / "memos" / "20260101-000000.wav", days_old=99)
    snap = _touch(tmp_path / "snaps" / "20260101-000000.m4a", days_old=99)
    stray = _touch(tmp_path / "note.txt", days_old=99)  # non yt_ top-level file

    removed = prune_audio_cache(max_age_days=30, cache_dir=tmp_path)

    assert removed == []
    assert memo.exists() and snap.exists() and stray.exists()


def test_prune_dry_run_reports_without_deleting(tmp_path):
    old = _touch(tmp_path / "yt_old.m4a", days_old=40)

    removed = prune_audio_cache(max_age_days=30, cache_dir=tmp_path, dry_run=True)

    assert removed == [old]
    assert old.exists()  # dry run must not delete


def test_prune_nonpositive_age_is_noop(tmp_path):
    """max_age_days <= 0 must never be treated as a 'now' cutoff that wipes all."""
    old = _touch(tmp_path / "yt_x.m4a", days_old=999)
    assert prune_audio_cache(max_age_days=0, cache_dir=tmp_path) == []
    assert prune_audio_cache(max_age_days=-5, cache_dir=tmp_path) == []
    assert old.exists()
