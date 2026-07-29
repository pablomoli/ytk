"""E5 (#149): capture-outcome logging is the baseline instrumentation for the
ingest queue state machine (#148). Records attempts, never changes behavior."""

import json

from ytk import capture_log


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_log_capture_appends_attempt_records(tmp_path, monkeypatch):
    log = tmp_path / "capture_log.jsonl"
    monkeypatch.setenv("YTK_CAPTURE_LOG", str(log))
    capture_log.log_capture(
        "hub", "https://youtu.be/x", source="youtube", outcome="ok", attempt=1, duration_s=112.4
    )
    capture_log.log_capture(
        "feed",
        "https://instagram.com/p/y",
        source="instagram",
        outcome="error",
        error="login required",
    )

    lines = read_lines(log)
    assert lines[0]["surface"] == "hub"
    assert lines[0]["url"] == "https://youtu.be/x"
    assert lines[0]["outcome"] == "ok"
    assert lines[0]["attempt"] == 1
    assert lines[0]["duration_s"] == 112.4
    assert lines[0]["ts"]
    assert lines[1]["outcome"] == "error"
    assert lines[1]["error"] == "login required"
    assert "attempt" not in lines[1]  # optional fields stay absent, not null


def test_log_capture_off_switch_and_swallowed_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_CAPTURE_LOG", "off")
    capture_log.log_capture("hub", "u", source="youtube", outcome="ok")
    assert not (tmp_path / "capture_log.jsonl").exists()

    monkeypatch.setenv("YTK_CAPTURE_LOG", str(tmp_path / "no" / "dir" / "x.jsonl"))
    capture_log.log_capture("hub", "u", source="youtube", outcome="ok")  # must not raise


def test_log_capture_notes_silent_partial(tmp_path, monkeypatch):
    # outcome "ok" with note_found False is E5's target: the silent loss that
    # today vanishes without a trace
    log = tmp_path / "capture_log.jsonl"
    monkeypatch.setenv("YTK_CAPTURE_LOG", str(log))
    capture_log.log_capture(
        "hub", "https://youtu.be/z", source="youtube", outcome="ok", note_found=False
    )
    assert read_lines(log)[0]["note_found"] is False
