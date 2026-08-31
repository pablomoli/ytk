"""P5 idle sweep (#197): park stale quality asks, retry parked read-gate
failures, expire the intent window. Reflex sweep deferred past P5 (owner
decision 2026-08-31)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from ytk import asks, evidence, ledger, loop
from ytk.capture import capture
from ytk.evidence import EvidenceBundle


@pytest.fixture
def conn():
    c = ledger.connect()
    yield c
    c.close()


def _seed(conn, url="https://www.youtube.com/watch?v=abc123xyz00", take=None) -> int:
    res = capture(
        conn, source="youtube", url=url, surface="cli", text=take, take_kind="intent", log=False
    )
    return res.item_id


def _age_ask(conn, ask_id, days):
    old = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    conn.execute("UPDATE asks SET created_at = ? WHERE id = ?", (old, ask_id))
    conn.execute("UPDATE outbox SET created_at = ? WHERE ask_id = ?", (old, ask_id))
    conn.commit()


def _junk_ask(conn, item, *, days_old=0) -> int:
    ledger.insert_activity(conn, item, actor="loop", action="read", to_state="read")
    ask_id = asks.raise_ask(
        conn,
        item,
        proposal={"kind": "transcript junk", "why": "no captions", "options": []},
        actor="loop",
    )
    assert ask_id is not None
    if days_old:
        _age_ask(conn, ask_id, days_old)
    return ask_id


def _good_bundle(url) -> EvidenceBundle:
    return EvidenceBundle(
        source="youtube",
        url=url,
        title="Recovered",
        transcript=[{"start": 0, "duration": 2, "text": "captions arrived at last"}],
        transcript_origin="api-manual",
        transcript_language="en",
        transcript_status="ok",
    )


def _bad_bundle(url) -> EvidenceBundle:
    return EvidenceBundle(
        source="youtube",
        url=url,
        title="Still junk",
        transcript=[],
        transcript_origin="none",
        transcript_language=None,
        transcript_status="none",
        frames=["f.jpg"],
    )


class TestParkStaleAsks:
    def test_quality_ask_past_window_parks(self, conn):
        item = _seed(conn)
        _junk_ask(conn, item, days_old=15)
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "parked"

    def test_young_quality_ask_stays_asking(self, conn):
        item = _seed(conn)
        _junk_ask(conn, item, days_old=2)
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "asking"

    def test_intent_ask_never_parks_it_expires_instead(self, conn):
        item = _seed(conn)
        ledger.insert_activity(conn, item, actor="loop", action="read", to_state="read")
        ask_id = asks.raise_intent_ask(conn, item)
        _age_ask(conn, ask_id, 15)
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "dropped"


class TestIntentExpiry:
    def test_past_window_drops_with_archive_detail(self, conn):
        item = _seed(conn, url="https://www.youtube.com/watch?v=expire00000")
        ledger.insert_activity(conn, item, actor="loop", action="read", to_state="read")
        ask_id = asks.raise_intent_ask(conn, item)
        _age_ask(conn, ask_id, 8)
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "dropped"
        row = conn.execute(
            "SELECT actor, reason, detail FROM activity WHERE item_id = ? AND to_state = 'dropped'",
            (item,),
        ).fetchone()
        assert row["actor"] == "sweep"
        detail = json.loads(row["detail"])
        assert detail["url"] == "https://www.youtube.com/watch?v=expire00000"
        assert detail["non_answer"] == "intent window expired"
        out = conn.execute("SELECT answered_at FROM outbox WHERE ask_id = ?", (ask_id,)).fetchone()
        assert out["answered_at"] is not None
        assert conn.execute("SELECT count(*) FROM answers").fetchone()[0] == 0

    def test_inside_window_untouched(self, conn):
        item = _seed(conn)
        ledger.insert_activity(conn, item, actor="loop", action="read", to_state="read")
        asks.raise_intent_ask(conn, item)
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "asking"

    def test_answered_ask_is_not_expired(self, conn):
        item = _seed(conn)
        ledger.insert_activity(conn, item, actor="loop", action="read", to_state="read")
        ask_id = asks.raise_intent_ask(conn, item)
        _age_ask(conn, ask_id, 8)
        ledger.insert_answer(conn, ask_id, choice="intent", text="want it")
        conn.execute("UPDATE outbox SET answered_at = ? WHERE ask_id = ?", ("t", ask_id))
        loop.sweep(conn)
        assert ledger.item_state(conn, item) != "dropped"


class TestRetryParked:
    def _park(self, conn, item):
        ledger.insert_activity(
            conn, item, actor="sweep", action="park", to_state="parked", reason="ask unanswered"
        )

    def test_pass_returns_to_read_and_closes_the_ask(self, conn, monkeypatch):
        item = _seed(conn, take="still want it")
        ask_id = _junk_ask(conn, item)
        self._park(conn, item)
        monkeypatch.setitem(evidence.GATHERERS, "youtube", lambda url, title: _good_bundle(url))
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "read"
        out = conn.execute("SELECT answered_at FROM outbox WHERE ask_id = ?", (ask_id,)).fetchone()
        assert out["answered_at"] is not None
        assert conn.execute("SELECT count(*) FROM asks").fetchone()[0] == 1  # no new ask
        row = conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item,)).fetchone()
        assert row["payload_ref"] and "evidence" in row["payload_ref"]

    def test_fail_stays_parked_with_attempt_recorded(self, conn, monkeypatch):
        item = _seed(conn)
        _junk_ask(conn, item)
        self._park(conn, item)
        monkeypatch.setitem(evidence.GATHERERS, "youtube", lambda url, title: _bad_bundle(url))
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "parked"
        n = conn.execute(
            "SELECT count(*) FROM activity WHERE item_id = ? AND action = 'retry-read'", (item,)
        ).fetchone()[0]
        assert n == 1

    def test_recent_attempt_is_cooled_down(self, conn, monkeypatch):
        item = _seed(conn)
        _junk_ask(conn, item)
        self._park(conn, item)
        calls: list[int] = []

        def gather(url, title):
            calls.append(1)
            return _bad_bundle(url)

        monkeypatch.setitem(evidence.GATHERERS, "youtube", gather)
        loop.sweep(conn)
        loop.sweep(conn)
        assert len(calls) == 1

    def test_per_sweep_cap(self, conn, monkeypatch):
        monkeypatch.setattr(loop, "RETRY_MAX_PER_SWEEP", 1)
        for i in range(2):
            item = _seed(conn, url=f"https://www.youtube.com/watch?v=cap{i}00000000")
            _junk_ask(conn, item)
            self._park(conn, item)
        calls: list[int] = []

        def gather(url, title):
            calls.append(1)
            return _bad_bundle(url)

        monkeypatch.setitem(evidence.GATHERERS, "youtube", gather)
        loop.sweep(conn)
        assert len(calls) == 1

    def test_stuck_parked_items_are_not_retried(self, conn, monkeypatch):
        item = _seed(conn)
        ledger.insert_activity(
            conn, item, actor="loop", action="park", to_state="parked", reason="stuck"
        )
        calls: list[int] = []
        monkeypatch.setitem(
            evidence.GATHERERS, "youtube", lambda url, title: calls.append(1) or _bad_bundle(url)
        )
        loop.sweep(conn)
        assert calls == []


class TestSweepDue:
    def test_due_when_never_swept(self):
        assert loop.sweep_due() is True

    def test_not_due_right_after_a_sweep(self, conn):
        loop.sweep(conn)
        assert loop.sweep_due() is False

    def test_due_again_after_the_window(self, conn):
        loop.sweep(conn)
        old = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        loop.write_health(last_sweep_at=old)
        assert loop.sweep_due() is True
