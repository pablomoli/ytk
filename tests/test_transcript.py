from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from ytk.transcript import fetch_transcript, _fetch_via_whisper, _download_audio


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

    with patch("ytk.transcript._download_audio", return_value=audio_file), \
         patch("ytk.transcript.WhisperModel") as MockModel:
        MockModel.return_value.transcribe.return_value = _fake_segments()
        segments, source = _fetch_via_whisper("https://youtu.be/test123", whisper_model="base")

    assert source == "whisper"
    assert segments[0] == {"start": 0.0, "duration": 5.0, "text": "Hello world"}
    assert segments[1] == {"start": 5.0, "duration": 5.0, "text": "Second segment"}


def test_fetch_transcript_falls_back_to_whisper():
    """When youtube-transcript-api fails, fetch_transcript calls Whisper."""
    from youtube_transcript_api import NoTranscriptFound

    with patch("ytk.transcript._fetch_via_api", side_effect=NoTranscriptFound("x", ["en"], None)), \
         patch("ytk.transcript._fetch_via_whisper", return_value=([], "whisper")) as mock_whisper:
        segments, source = fetch_transcript("https://youtu.be/abc12345678")

    mock_whisper.assert_called_once()
    assert source == "whisper"


def test_fetch_transcript_no_ytdlp_subtitle_tier():
    """The old yt-dlp subtitle tier is gone — only two tiers exist."""
    import ytk.transcript as t
    assert not hasattr(t, "_fetch_via_ytdlp"), "yt-dlp subtitle tier should be removed"
