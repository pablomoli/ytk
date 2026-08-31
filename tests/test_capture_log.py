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
    # #96: hub captures are the user's own intent; every other surface is
    # pipeline work unless the caller says otherwise
    assert lines[0]["actor"] == "user"
    assert lines[1]["actor"] == "system"


def test_log_capture_actor_override(tmp_path, monkeypatch):
    log = tmp_path / "capture_log.jsonl"
    monkeypatch.setenv("YTK_CAPTURE_LOG", str(log))
    capture_log.log_capture("sync", "u", source="youtube", outcome="ok", actor="agent")
    assert read_lines(log)[0]["actor"] == "agent"


def test_log_capture_off_switch_and_swallowed_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_CAPTURE_LOG", "off")
    capture_log.log_capture("hub", "u", source="youtube", outcome="ok")
    assert not (tmp_path / "capture_log.jsonl").exists()

    monkeypatch.setenv("YTK_CAPTURE_LOG", str(tmp_path / "no" / "dir" / "x.jsonl"))
    capture_log.log_capture("hub", "u", source="youtube", outcome="ok")  # must not raise


def test_capture_log_is_redirected_away_from_production_by_default(monkeypatch, tmp_path):
    """Six days of the E5 window were 92% pytest fixtures: tests inherited the
    production log target. The conftest fixture must redirect every test."""
    import os
    from pathlib import Path

    target = os.environ.get("YTK_CAPTURE_LOG", "")
    assert target, "conftest must set YTK_CAPTURE_LOG for every test"
    assert target != str(Path.home() / ".ytk" / "capture_log.jsonl")


def test_feed_logs_captures_with_feed_surface(tmp_path, monkeypatch):
    """P2 (#197): feed captures into the ledger; the capture itself is the
    logged outcome — note_found died with direct vault writes."""
    import os
    from pathlib import Path

    from click.testing import CliRunner

    from ytk import cli as ytk_cli
    from ytk import evidence

    monkeypatch.setenv("YTK_LEDGER", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("YTK_EVIDENCE", str(tmp_path / "evidence"))
    import ytk.gatherers  # noqa: F401 — fill the registry before overriding

    monkeypatch.setitem(
        evidence.GATHERERS,
        "youtube",
        lambda url, title: evidence.EvidenceBundle(
            source="youtube",
            url=url,
            title="T",
            transcript=[{"start": 0, "duration": 1, "text": "hi"}],
            transcript_origin="api-manual",
            transcript_language="en",
            transcript_status="ok",
        ),
    )
    result = CliRunner().invoke(ytk_cli.cli, ["feed", "https://youtu.be/realvideo123"])
    assert result.exit_code == 0, result.output

    records = [
        json.loads(line) for line in Path(os.environ["YTK_CAPTURE_LOG"]).read_text().splitlines()
    ]
    feed_records = [r for r in records if r["surface"] == "feed"]
    assert feed_records, records
    assert feed_records[-1]["outcome"] == "captured"


def test_log_capture_notes_silent_partial(tmp_path, monkeypatch):
    # outcome "ok" with note_found False is E5's target: the silent loss that
    # today vanishes without a trace
    log = tmp_path / "capture_log.jsonl"
    monkeypatch.setenv("YTK_CAPTURE_LOG", str(log))
    capture_log.log_capture(
        "hub", "https://youtu.be/z", source="youtube", outcome="ok", note_found=False
    )
    assert read_lines(log)[0]["note_found"] is False
