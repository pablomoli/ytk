"""fetch_transcript_evidence (#197 P2): the quality flags the API path used
to compute and discard — manual vs auto, language, whisper fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ytk import transcript


def _seg():
    s = MagicMock()
    s.start, s.duration, s.text = 0.0, 2.0, "hello"
    return s


def _track(language_code: str, generated: bool):
    t = MagicMock()
    t.language_code = language_code
    t.is_generated = generated
    t.fetch.return_value = [_seg()]
    return t


def _api_with(manual: bool, language_code: str = "en", tracks=None):
    api = MagicMock()
    tlist = api.return_value.list.return_value
    tracks = tracks if tracks is not None else [_track(language_code, generated=not manual)]
    tlist.__iter__.side_effect = lambda: iter(tracks)
    return api


def test_manual_captions_flagged_api_manual():
    with patch("ytk.transcript.YouTubeTranscriptApi", _api_with(manual=True)):
        ev = transcript.fetch_transcript_evidence("https://www.youtube.com/watch?v=abcdefghijk")
    assert ev.origin == "api-manual"
    assert ev.language == "en"
    assert ev.status == "ok"
    assert ev.segments[0]["text"] == "hello"


def test_auto_captions_flagged_api_auto():
    with patch("ytk.transcript.YouTubeTranscriptApi", _api_with(manual=False)):
        ev = transcript.fetch_transcript_evidence("https://www.youtube.com/watch?v=abcdefghijk")
    assert ev.origin == "api-auto"


def test_whisper_fallback_carries_detected_language():
    api = MagicMock()
    api.return_value.list.side_effect = transcript.TranscriptsDisabled("v")
    info = MagicMock()
    info.language = "pt"
    seg = MagicMock()
    seg.start, seg.end, seg.text = 0.0, 2.0, "ola"
    with (
        patch("ytk.transcript.YouTubeTranscriptApi", api),
        patch("ytk.transcript._download_audio", return_value="/tmp/x.m4a"),
        patch("ytk.transcript.WhisperModel") as wm,
    ):
        wm.return_value.transcribe.return_value = ([seg], info)
        ev = transcript.fetch_transcript_evidence("https://www.youtube.com/watch?v=abcdefghijk")
    assert ev.origin == "whisper"
    assert ev.language == "pt"
    assert ev.status == "ok"


def test_nothing_anywhere_is_status_none():
    api = MagicMock()
    api.return_value.list.side_effect = transcript.TranscriptsDisabled("v")
    with (
        patch("ytk.transcript.YouTubeTranscriptApi", api),
        patch("ytk.transcript._download_audio", side_effect=RuntimeError("no audio")),
    ):
        ev = transcript.fetch_transcript_evidence("https://www.youtube.com/watch?v=abcdefghijk")
    assert ev.origin == "none"
    assert ev.status == "none"
    assert ev.segments == []


def _pick(tracks):
    with patch("ytk.transcript.YouTubeTranscriptApi", _api_with(True, tracks=tracks)):
        return transcript.fetch_transcript_evidence("https://www.youtube.com/watch?v=abcdefghijk")


def test_regional_english_manual_track_is_used():
    # CGZ4rn3JgDA: manual en-US plus auto id fell through to Whisper.
    ev = _pick([_track("id", generated=True), _track("en-US", generated=False)])
    assert (ev.origin, ev.language) == ("api-manual", "en-US")


def test_manual_beats_auto_within_english():
    ev = _pick([_track("en", generated=True), _track("en-GB", generated=False)])
    assert (ev.origin, ev.language) == ("api-manual", "en-GB")


def test_english_auto_beats_other_language_manual():
    ev = _pick([_track("pt", generated=False), _track("en", generated=True)])
    assert (ev.origin, ev.language) == ("api-auto", "en")


def test_only_foreign_tracks_fall_through_to_whisper():
    seg = MagicMock()
    seg.start, seg.end, seg.text = 0.0, 2.0, "hello"
    info = MagicMock()
    info.language = "en"
    with (
        patch("ytk.transcript.YouTubeTranscriptApi", _api_with(True, tracks=[_track("pt", True)])),
        patch("ytk.transcript._download_audio", return_value="/tmp/x.m4a"),
        patch("ytk.transcript.WhisperModel") as wm,
    ):
        wm.return_value.transcribe.return_value = ([seg], info)
        ev = transcript.fetch_transcript_evidence("https://www.youtube.com/watch?v=abcdefghijk")
    assert ev.origin == "whisper"
