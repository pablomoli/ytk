"""P2 (#197): playlist sync captures into the ledger; its vault-writing half
is gone (spec removal). Actor is sweep — the machine, not the owner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ytk import evidence, ledger, scheduler
from ytk.config import Config
from ytk.evidence import EvidenceBundle


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_LEDGER", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("YTK_EVIDENCE", str(tmp_path / "evidence"))
    monkeypatch.setenv("YTK_CAPTURE_LOG", str(tmp_path / "capture_log.jsonl"))
    import ytk.gatherers  # noqa: F401 — fill the registry before overriding

    monkeypatch.setitem(
        evidence.GATHERERS,
        "youtube",
        lambda url, title: EvidenceBundle(
            source="youtube",
            url=url,
            title=title,
            transcript=[{"start": 0, "duration": 1, "text": "hi"}],
            transcript_origin="api-manual",
            transcript_language="en",
            transcript_status="ok",
        ),
    )
    monkeypatch.setattr(scheduler, "_write_playlist_cache", lambda videos: None)
    # db module caches its connection at ~/.ytk/ytk.db; point it at tmp.
    import ytk.db as db

    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "ytk.db")
    monkeypatch.setattr(db, "_conn", None)
    return tmp_path


def _run_sync(videos):
    with patch.object(scheduler, "fetch_playlist_videos", return_value=videos):
        return scheduler.sync(MagicMock(), Config())


def test_sync_captures_new_videos_as_sweep(env):
    result = _run_sync([{"video_id": "abcdefghijk", "title": "A talk"}])
    assert result.ingested == 1
    assert result.failed == 0
    conn = ledger.connect()
    row = conn.execute("SELECT * FROM items").fetchone()
    assert row["provenance"] == "sync"
    assert row["title"] == "A talk"
    assert ledger.item_state(conn, row["id"]) == "read"
    actor = conn.execute("SELECT actor FROM activity WHERE action = 'capture'").fetchone()
    assert actor["actor"] == "sweep"


def test_sync_skips_processed_and_is_idempotent(env):
    videos = [{"video_id": "abcdefghijk", "title": "A talk"}]
    _run_sync(videos)
    result = _run_sync(videos)
    assert result.already_processed == 1
    assert result.ingested == 0
    conn = ledger.connect()
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 1


def test_sync_read_failure_leaves_video_unprocessed_for_retry(env, monkeypatch):
    def boom(url, title):
        raise RuntimeError("network down")

    monkeypatch.setitem(evidence.GATHERERS, "youtube", boom)
    result = _run_sync([{"video_id": "abcdefghijk", "title": "A talk"}])
    assert result.failed == 1
    import ytk.db as db

    assert not db.is_processed("abcdefghijk")
    conn = ledger.connect()
    row = conn.execute("SELECT id FROM items").fetchone()
    assert ledger.item_state(conn, row["id"]) == "captured"  # capture survives
