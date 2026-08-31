"""The capture verb (#197 P2): a URL becomes a ledger row and nothing else.

Spec: docs/architecture/curator-engine.md, Verbs — "capture: URL, paste, memo,
screenshot, DM item -> a ledger row; corpus after: nothing written".
"""

from __future__ import annotations

import json

import pytest

from ytk import capture, ledger


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_LEDGER", str(tmp_path / "ledger.db"))
    log = tmp_path / "capture_log.jsonl"
    monkeypatch.setenv("YTK_CAPTURE_LOG", str(log))
    return log


def test_capture_inserts_item_activity_and_log_line(env):
    conn = ledger.connect()
    result = capture.capture(conn, source="youtube", url="https://y/1", title="T", surface="hub")
    assert result.item_id is not None
    assert not result.duplicate
    assert ledger.item_state(conn, result.item_id) == "captured"
    row = conn.execute("SELECT provenance FROM items WHERE id = ?", (result.item_id,)).fetchone()
    assert row["provenance"] == "hub"
    lines = [json.loads(line) for line in env.read_text().splitlines()]
    assert len(lines) == 1
    assert lines[0]["surface"] == "hub"
    assert lines[0]["outcome"] == "captured"


def test_capture_with_text_writes_a_take(env):
    conn = ledger.connect()
    result = capture.capture(
        conn,
        source="youtube",
        url="https://y/1",
        surface="hub",
        text="why I saved this",
        take_kind="intent",
    )
    take = conn.execute("SELECT * FROM takes WHERE id = ?", (result.take_id,)).fetchone()
    assert take["item_id"] == result.item_id
    assert take["kind"] == "intent"
    assert take["text"] == "why I saved this"
    assert take["surface"] == "hub"


def test_capture_without_text_writes_no_take(env):
    conn = ledger.connect()
    result = capture.capture(conn, source="web", url="https://w/1", surface="cli")
    assert result.take_id is None
    assert conn.execute("SELECT count(*) FROM takes").fetchone()[0] == 0


def test_capture_text_is_capped(env):
    conn = ledger.connect()
    result = capture.capture(
        conn,
        source="imessage",
        url="note://paste/1",
        surface="hub",
        text="x" * (capture.TEXT_CAP + 5_000_000),
        take_kind="reflex",
    )
    take = conn.execute("SELECT text FROM takes WHERE id = ?", (result.take_id,)).fetchone()
    assert len(take["text"]) == capture.TEXT_CAP


def test_duplicate_capture_attaches_take_to_existing_item(env):
    conn = ledger.connect()
    first = capture.capture(conn, source="youtube", url="https://y/1", surface="hub")
    again = capture.capture(
        conn, source="youtube", url="https://y/1", surface="hub", text="second thought"
    )
    assert again.duplicate
    assert again.item_id == first.item_id
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 1
    # One activity row: the duplicate insert is a no-op, not a transition.
    assert conn.execute("SELECT count(*) FROM activity").fetchone()[0] == 1
    take = conn.execute("SELECT item_id FROM takes WHERE id = ?", (again.take_id,)).fetchone()
    assert take["item_id"] == first.item_id


def test_machine_surface_gets_machine_actor(env):
    conn = ledger.connect()
    result = capture.capture(
        conn, source="youtube", url="https://y/2", surface="sync", actor="sweep"
    )
    row = conn.execute("SELECT actor FROM activity WHERE item_id = ?", (result.item_id,)).fetchone()
    assert row["actor"] == "sweep"
