"""Ops visibility surface: status file atomicity, step upsert, journal."""

import json

import pytest

from ytk import ops


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(ops, "STATUS_PATH", tmp_path / "ops-status.json")
    monkeypatch.setattr(ops, "JOURNAL_PATH", tmp_path / "logs" / "journal.md")
    monkeypatch.setattr(ops, "_notify", lambda *a, **k: None)
    return tmp_path


def test_run_step_progress_roundtrip(paths):
    ops.start_run("test-run", "intent line")
    ops.step("backup", "running", "copying")
    ops.step("backup", "done", "1.1G copied")
    ops.step("migrate", "running")
    ops.progress(50, 100, rate=2.0, label="memories")

    st = json.loads((paths / "ops-status.json").read_text())
    assert st["run"] == "test-run"
    assert [s["name"] for s in st["steps"]] == ["backup", "migrate"]
    assert st["steps"][0]["state"] == "done"  # upserted, not duplicated
    assert st["progress"]["eta_min"] == pytest.approx(25 / 60, abs=0.1)

    journal = (paths / "logs" / "journal.md").read_text()
    assert "run started: test-run" in journal
    assert "backup: done" in journal


def test_finished_step_clears_progress(paths):
    ops.start_run("r")
    ops.step("migrate", "running")
    ops.progress(10, 100, rate=1.0)
    ops.step("migrate", "done")
    assert json.loads((paths / "ops-status.json").read_text())["progress"] is None


def test_cli_entrypoint(paths):
    assert ops.main(["run", "cli-run", "hello"]) == 0
    assert ops.main(["step", "s1", "done", "detail"]) == 0
    assert ops.main(["journal", "note"]) == 0
    assert ops.main(["bogus"]) == 2
    st = json.loads((paths / "ops-status.json").read_text())
    assert st["run"] == "cli-run" and st["steps"][0]["state"] == "done"


def test_bad_state_rejected(paths):
    ops.start_run("r")
    with pytest.raises(ValueError):
        ops.step("x", "exploded")
