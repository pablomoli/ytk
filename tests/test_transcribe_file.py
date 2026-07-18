"""Shared local-media Whisper transcription: transcribe_file()."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import ytk.transcript as transcript_mod


def _seg(start, end, text):
    return SimpleNamespace(start=start, end=end, text=text)


class FakeModel:
    def __init__(self, segments=None, exc=None):
        self.segments = segments or []
        self.exc = exc
        self.transcribed_paths = []

    def transcribe(self, path, **kwargs):
        if self.exc:
            raise self.exc
        self.transcribed_paths.append(path)
        return iter(self.segments), SimpleNamespace()


@pytest.fixture
def media_file(tmp_path):
    f = tmp_path / "reel.mp4"
    f.write_bytes(b"\x00\x00fake mp4")
    return f


@pytest.fixture(autouse=True)
def media_has_audio(monkeypatch):
    """Unit-test fake MP4 bytes are not probeable; model them as audio media."""
    monkeypatch.setattr(transcript_mod, "_has_audio_stream", lambda path: True)


def test_transcribes_local_file_with_timestamped_segments(monkeypatch, media_file):
    fake = FakeModel(segments=[_seg(0.0, 2.5, " hello "), _seg(2.5, 4.0, "world")])
    monkeypatch.setattr(transcript_mod, "WhisperModel", lambda name, **kw: fake)

    result = transcript_mod.transcribe_file(media_file, whisper_model="base")

    assert result.status == "ok"
    assert result.segments == [
        {"start": 0.0, "duration": 2.5, "text": "hello"},
        {"start": 2.5, "duration": 1.5, "text": "world"},
    ]
    assert fake.transcribed_paths == [str(media_file)]


def test_no_download_machinery_is_touched(monkeypatch, media_file):
    """transcribe_file operates on the already-downloaded file only."""
    def boom(*a, **kw):
        raise AssertionError("must not download")

    monkeypatch.setattr(transcript_mod, "_download_audio", boom)
    monkeypatch.setattr(
        transcript_mod, "WhisperModel", lambda name, **kw: FakeModel(segments=[_seg(0, 1, "x")])
    )
    result = transcript_mod.transcribe_file(media_file)
    assert result.status == "ok"


def test_no_speech_is_a_valid_result(monkeypatch, media_file):
    monkeypatch.setattr(transcript_mod, "WhisperModel", lambda name, **kw: FakeModel())
    result = transcript_mod.transcribe_file(media_file)
    assert result.status == "no_speech"
    assert result.segments == []
    assert result.error is None


def test_video_only_container_is_no_speech_without_loading_whisper(
    monkeypatch, media_file
):
    monkeypatch.setattr(transcript_mod, "_has_audio_stream", lambda path: False)
    monkeypatch.setattr(
        transcript_mod,
        "WhisperModel",
        lambda *args, **kwargs: pytest.fail("Whisper must not load without audio"),
    )

    result = transcript_mod.transcribe_file(media_file)

    assert result.status == "no_speech"
    assert result.segments == []
    assert result.error is None


def test_whitespace_only_segments_count_as_no_speech(monkeypatch, media_file):
    fake = FakeModel(segments=[_seg(0, 1, "  "), _seg(1, 2, "")])
    monkeypatch.setattr(transcript_mod, "WhisperModel", lambda name, **kw: fake)
    assert transcript_mod.transcribe_file(media_file).status == "no_speech"


def test_transcription_failure_is_distinguished(monkeypatch, media_file):
    monkeypatch.setattr(
        transcript_mod,
        "WhisperModel",
        lambda name, **kw: FakeModel(exc=RuntimeError("cuda exploded")),
    )
    result = transcript_mod.transcribe_file(media_file)
    assert result.status == "failed"
    assert result.segments == []
    assert "cuda exploded" in result.error


def test_missing_file_fails_without_raising(monkeypatch, tmp_path):
    monkeypatch.setattr(
        transcript_mod, "WhisperModel", lambda name, **kw: FakeModel(segments=[_seg(0, 1, "x")])
    )
    result = transcript_mod.transcribe_file(tmp_path / "nope.mp4")
    assert result.status == "failed"


def test_configured_model_name_is_used(monkeypatch, media_file):
    seen = []

    def factory(name, **kw):
        seen.append(name)
        return FakeModel(segments=[_seg(0, 1, "x")])

    monkeypatch.setattr(transcript_mod, "WhisperModel", factory)
    transcript_mod.transcribe_file(media_file, whisper_model="small")
    assert seen == ["small"]


def test_transcribe_tiktok_reuses_shared_helper(monkeypatch, media_file):
    """TikTok path: download audio once, then hand the local file to transcribe_file."""
    import ytk.tiktok as tiktok_mod

    monkeypatch.setattr(
        transcript_mod, "_download_audio", lambda url: media_file
    )
    monkeypatch.setattr(
        transcript_mod,
        "WhisperModel",
        lambda name, **kw: FakeModel(segments=[_seg(0, 1, "hi")]),
    )
    segments = tiktok_mod.transcribe_tiktok("https://tiktok.com/@u/video/1")
    assert segments == [{"start": 0, "duration": 1.0, "text": "hi"}]


def test_transcribe_tiktok_returns_empty_on_download_failure(monkeypatch):
    import ytk.tiktok as tiktok_mod

    def boom(url):
        raise RuntimeError("blocked")

    monkeypatch.setattr(transcript_mod, "_download_audio", boom)
    assert tiktok_mod.transcribe_tiktok("https://tiktok.com/@u/video/1") == []
