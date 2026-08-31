"""P2 (#197): the hub drain captures into the ledger; the thought box is a
take; the sync catch-up thread is gone."""

from __future__ import annotations

import json
import time

import pytest

import ytk.ui.hub as hub
from ytk import evidence, ledger
from ytk.evidence import EvidenceBundle
from ytk.reels import ReelItem


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_LEDGER", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("YTK_EVIDENCE", str(tmp_path / "evidence"))
    log = tmp_path / "capture_log.jsonl"
    monkeypatch.setenv("YTK_CAPTURE_LOG", str(log))
    monkeypatch.setattr(hub, "STATE_PATH", tmp_path / "reels_state.json")
    monkeypatch.setattr(hub, "JOB_PATH", tmp_path / "ingest-job.json")
    monkeypatch.setattr(hub, "PACING_SECONDS", 0)
    # Other hub suites assign hub.INGEST directly; pin the real seam here.
    monkeypatch.setattr(hub, "INGEST", hub.ingest_via_cli)
    import ytk.gatherers  # noqa: F401 — fill the registry before overriding

    monkeypatch.setitem(
        evidence.GATHERERS,
        "youtube",
        lambda url, title: EvidenceBundle(
            source="youtube",
            url=url,
            title="T",
            transcript=[{"start": 0, "duration": 1, "text": "hi"}],
            transcript_origin="api-manual",
            transcript_language="en",
            transcript_status="ok",
        ),
    )
    return log


def _wait_done(timeout=5.0):
    start = time.time()
    while time.time() - start < timeout:
        if not hub.job_status()["running"]:
            return
        time.sleep(0.05)
    raise AssertionError("drain did not finish")


@pytest.fixture(autouse=True)
def stub_advance(monkeypatch):
    """The drain now advances clean take-ful reads (P4); these tests pin the
    capture path, so the verb is recorded, never run."""
    from ytk.curator import AdvanceResult

    calls: list[int] = []

    def fake(conn, item_id, *, actor="loop"):
        calls.append(item_id)
        return AdvanceResult(item_id, "skipped", detail="stubbed in tests")

    monkeypatch.setattr("ytk.curator.advance_item", fake)
    return calls


def test_drain_captures_with_take_and_hub_log_line(env):
    from ytk import reels

    url = "https://www.youtube.com/watch?v=abcdefghijk"
    state = reels.load_state(hub.STATE_PATH)
    state.pending.append(ReelItem(url=url, source="youtube"))
    reels.save_state(state, hub.STATE_PATH)
    hub.start_ingest([url], tags=[], thought="why I saved it")
    _wait_done()
    conn = ledger.connect()
    row = conn.execute("SELECT * FROM items").fetchone()
    assert row["provenance"] == "hub"
    assert ledger.item_state(conn, row["id"]) == "read"
    take = conn.execute("SELECT text FROM takes WHERE item_id = ?", (row["id"],)).fetchone()
    assert take["text"] == "why I saved it"
    lines = [json.loads(line) for line in env.read_text().splitlines()]
    hub_lines = [r for r in lines if r["surface"] == "hub"]
    assert len(hub_lines) == 1  # the drain's line; capture() itself stays quiet
    assert hub_lines[0]["outcome"] == "ok"
    assert "note_found" not in hub_lines[0]


def test_sync_catchup_thread_is_gone():
    assert not hasattr(hub, "start_sync_catchup")
