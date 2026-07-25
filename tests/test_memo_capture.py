"""Capture and conversion build the right ffmpeg commands. No real mic/model."""

from unittest.mock import MagicMock, patch

import pytest

from ytk.memo import ensure_wav, record, transcribe


def test_record_builds_avfoundation_command(tmp_path):
    out = tmp_path / "m.wav"
    out.write_bytes(b"RIFFfake")  # pretend ffmpeg wrote the file
    proc = MagicMock()
    proc.communicate.return_value = (b"", b"")
    proc.returncode = 255  # ffmpeg exit code after 'q'
    with patch("ytk.memo.subprocess.Popen", return_value=proc) as popen:
        record(out, max_seconds=120, wait=lambda *_: None)
    cmd = popen.call_args.args[0]
    assert "avfoundation" in cmd
    assert ":default" in cmd
    assert "-t" in cmd and "120" in cmd
    assert str(out) in cmd
    proc.communicate.assert_called_once_with(b"q", timeout=10)


def test_record_raises_on_missing_mic_permission(tmp_path):
    proc = MagicMock()
    proc.communicate.return_value = (b"", b"Input/output error")
    proc.returncode = 1
    with (
        patch("ytk.memo.subprocess.Popen", return_value=proc),
        pytest.raises(RuntimeError, match="[Mm]icrophone"),
    ):
        record(tmp_path / "m.wav", wait=lambda *_: None)


def test_ensure_wav_passthrough(tmp_path):
    wav = tmp_path / "a.wav"
    wav.touch()
    assert ensure_wav(wav) == wav


def test_ensure_wav_converts_m4a(tmp_path):
    m4a = tmp_path / "a.m4a"
    m4a.touch()
    with patch("ytk.memo.subprocess.run", return_value=MagicMock(returncode=0)) as run:
        out = ensure_wav(m4a)
    assert out == tmp_path / "a.wav"
    cmd = run.call_args.args[0]
    assert cmd[0] == "ffmpeg" and "-ar" in cmd and "16000" in cmd


def test_transcribe_joins_segments(tmp_path):
    seg1, seg2 = MagicMock(text=" hello"), MagicMock(text=" world ")
    model = MagicMock()
    model.transcribe.return_value = (iter([seg1, seg2]), MagicMock())
    with patch("ytk.memo._whisper_model", return_value=model):
        text = transcribe(tmp_path / "a.wav", "base")
    assert text == "hello world"
