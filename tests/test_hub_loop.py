"""P5 (#197): the hub hosts the loop — wake API, lifecycle, digest health
line. The thread is a thin driver around tick_once; tests tick on demand
and never let a thread near model work."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from ytk import ledger, loop
from ytk.ui import hub


@pytest.fixture()
def client():
    from ytk.ui.server import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def fresh_events(monkeypatch):
    """Pin fresh module events so tests never share wake state."""
    wake, stop = threading.Event(), threading.Event()
    monkeypatch.setattr(hub, "_LOOP_WAKE", wake)
    monkeypatch.setattr(hub, "_LOOP_STOP", stop)
    monkeypatch.setattr(hub, "_LOOP_THREAD", None)
    return wake


class TestWakeApi:
    def test_wake_endpoint_sets_the_event(self, client, fresh_events):
        assert not fresh_events.is_set()
        resp = client.post("/api/loop/wake")
        assert resp.status_code == 200
        assert resp.json() == {"woken": True}
        assert fresh_events.is_set()

    def test_answer_post_wakes_the_loop(self, client, fresh_events):
        from ytk import asks

        conn = ledger.connect()
        item_id = ledger.insert_item(conn, source="youtube", url="https://y/w", title="W")
        ledger.insert_activity(conn, item_id, actor="owner", action="capture", to_state="captured")
        ask_id = asks.raise_ask(conn, item_id, proposal={"kind": "transcript junk", "options": []})
        conn.close()
        client.post("/api/outbox/answer", json={"ask_id": ask_id, "choice": "drop"})
        assert fresh_events.is_set()


class TestDigestLine:
    def test_outbox_carries_health_line(self, client):
        loop.write_health(last_tick_at="2026-08-31T13:00:00+00:00", items_advanced=2, errors=0)
        body = client.get("/api/outbox").json()
        assert body["loop"]["ok"] is True
        assert "2 advanced" in body["loop"]["line"]

    def test_inert_flag_flips_ok_and_names_the_reason(self, client):
        loop.inert_path().parent.mkdir(parents=True, exist_ok=True)
        loop.inert_path().write_text("tripped: token ceiling")
        body = client.get("/api/outbox").json()
        assert body["loop"]["ok"] is False
        assert "token ceiling" in body["loop"]["line"]

    def test_never_ticked_says_so(self, client):
        body = client.get("/api/outbox").json()
        assert body["loop"]["ok"] is True
        assert "never ticked" in body["loop"]["line"]


class TestRunLoop:
    def test_thread_ticks_on_wake_and_joins_on_stop(self, monkeypatch):
        ticks: list[int] = []
        monkeypatch.setattr(loop, "tick_once", lambda conn: ticks.append(1))
        monkeypatch.setattr(loop, "sweep_due", lambda: False)
        wake, stop = threading.Event(), threading.Event()
        t = threading.Thread(
            target=loop.run_loop, args=(wake, stop), kwargs={"poll_seconds": 30}, daemon=True
        )
        t.start()
        deadline = time.monotonic() + 2
        while not ticks and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ticks  # start runs one cycle without a wake
        n = len(ticks)
        wake.set()
        deadline = time.monotonic() + 2
        while len(ticks) <= n and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(ticks) > n
        stop.set()
        wake.set()
        t.join(timeout=2)
        assert not t.is_alive()

    def test_start_reverts_orphan_leases(self, monkeypatch):
        # spec, Single writer: a crash mid-transition leaves a lease no thread
        # owns; the hub lock guarantees one loop, so start clears them all.
        conn = ledger.connect()
        item_id = ledger.insert_item(conn, source="youtube", url="https://y/lease", title="L")
        ledger.insert_activity(conn, item_id, actor="owner", action="capture", to_state="captured")
        conn.execute(
            "UPDATE items SET lease_until = '9999-01-01T00:00:00', tick_count = 2 WHERE id = ?",
            (item_id,),
        )
        conn.commit()
        conn.close()
        monkeypatch.setattr(loop, "tick_once", lambda conn: None)
        monkeypatch.setattr(loop, "sweep_due", lambda: False)
        wake, stop = threading.Event(), threading.Event()
        t = threading.Thread(
            target=loop.run_loop, args=(wake, stop), kwargs={"poll_seconds": 30}, daemon=True
        )
        t.start()
        deadline = time.monotonic() + 2
        conn = ledger.connect()
        try:
            while time.monotonic() < deadline:
                row = conn.execute(
                    "SELECT lease_until FROM items WHERE id = ?", (item_id,)
                ).fetchone()
                if row["lease_until"] is None:
                    break
                time.sleep(0.02)
            assert row["lease_until"] is None
        finally:
            conn.close()
        stop.set()
        wake.set()
        t.join(timeout=2)

    def test_sweep_runs_when_due(self, monkeypatch):
        ran: list[str] = []
        monkeypatch.setattr(loop, "tick_once", lambda conn: ran.append("tick"))
        monkeypatch.setattr(loop, "sweep", lambda conn: ran.append("sweep"))
        monkeypatch.setattr(loop, "sweep_due", lambda: True)
        wake, stop = threading.Event(), threading.Event()
        t = threading.Thread(
            target=loop.run_loop, args=(wake, stop), kwargs={"poll_seconds": 30}, daemon=True
        )
        t.start()
        deadline = time.monotonic() + 2
        while "sweep" not in ran and time.monotonic() < deadline:
            time.sleep(0.01)
        stop.set()
        wake.set()
        t.join(timeout=2)
        assert "sweep" in ran and "tick" in ran


class TestHubLifecycle:
    def test_start_and_stop_loop(self, monkeypatch):
        monkeypatch.setattr(loop, "tick_once", lambda conn: None)
        monkeypatch.setattr(loop, "sweep_due", lambda: False)
        hub.start_loop()
        thread = hub._LOOP_THREAD
        assert thread is not None and thread.is_alive()
        hub.stop_loop()
        assert not thread.is_alive()

    def test_wake_loop_sets_event(self, fresh_events):
        hub.wake_loop()
        assert fresh_events.is_set()
