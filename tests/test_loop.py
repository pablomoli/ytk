"""P5 loop (#197): paths, health, tick. The loop is the single writer of
transitions; these tests stub the verbs (P4 recorder pattern) and never do
model work."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ytk import asks, ledger, loop
from ytk.capture import capture


class TestPaths:
    def test_env_seams_override_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setenv("YTK_LOOP_HEALTH", str(tmp_path / "h.json"))
        monkeypatch.setenv("YTK_LOOP_KILL", str(tmp_path / "k"))
        monkeypatch.setenv("YTK_LOOP_INERT", str(tmp_path / "i"))
        assert loop.health_path() == tmp_path / "h.json"
        assert loop.kill_path() == tmp_path / "k"
        assert loop.inert_path() == tmp_path / "i"

    def test_defaults_live_under_dot_ytk(self, monkeypatch):
        monkeypatch.delenv("YTK_LOOP_HEALTH", raising=False)
        monkeypatch.delenv("YTK_LOOP_KILL", raising=False)
        monkeypatch.delenv("YTK_LOOP_INERT", raising=False)
        assert loop.health_path() == Path.home() / ".ytk" / "loop-health.json"
        assert loop.kill_path() == Path.home() / ".ytk" / "loop.kill"
        assert loop.inert_path() == Path.home() / ".ytk" / "loop.inert"


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


def _to_state(conn, item_id, state):
    ledger.insert_activity(conn, item_id, actor="loop", action="seed", to_state=state)


@pytest.fixture
def verbs(monkeypatch):
    """Recorder stubs for both verbs; no model work in loop tests."""
    calls: dict[str, list[int]] = {"read": [], "advance": []}

    def fake_read(conn, item_id, *, actor="loop"):
        from ytk import evidence

        calls["read"].append(item_id)
        ledger.insert_activity(conn, item_id, actor=actor, action="read", to_state="read")
        return evidence.ReadResult(bundle_path=None, ask_id=None)

    def fake_advance(conn, item_id, *, actor="loop"):
        calls["advance"].append(item_id)
        ledger.insert_activity(conn, item_id, actor=actor, action="keep", to_state="kept")

    monkeypatch.setattr("ytk.evidence.read_item", fake_read)
    monkeypatch.setattr("ytk.curator.advance_item", fake_advance)
    return calls


class TestTick:
    def test_pending_answer_becomes_transition_then_advance(self, conn, verbs):
        item = _seed(conn, take="why this one")
        _to_state(conn, item, "read")
        ask_id = asks.raise_ask(
            conn, item, proposal={"kind": "grader bounce, twice", "options": []}, actor="grader"
        )
        ledger.insert_answer(conn, ask_id, choice="accept as is")
        stats = loop.tick_once(conn)
        assert ledger.item_state(conn, item) == "kept"
        row = conn.execute(
            "SELECT actor, reason FROM activity WHERE item_id = ? AND action = 'answer'", (item,)
        ).fetchone()
        assert row["actor"] == "owner" and row["reason"] == "accept as is"
        assert verbs["advance"] == [item]
        assert stats.advanced >= 1

    def test_drop_answer_transitions_to_dropped_without_advance(self, conn, verbs):
        item = _seed(conn)
        _to_state(conn, item, "read")
        ask_id = asks.raise_ask(
            conn, item, proposal={"kind": "intent missing", "options": []}, actor="loop"
        )
        ledger.insert_answer(conn, ask_id, choice="drop")
        loop.tick_once(conn)
        assert ledger.item_state(conn, item) == "dropped"
        assert verbs["advance"] == []

    def test_captured_routes_to_read_newest_first(self, conn, verbs):
        older = _seed(conn, url="https://www.youtube.com/watch?v=older000000")
        conn.execute("UPDATE items SET captured_at = '2026-01-01T00:00:00' WHERE id = ?", (older,))
        newer = _seed(conn, url="https://www.youtube.com/watch?v=newer000000")
        loop.tick_once(conn)
        assert verbs["read"] == [newer, older]

    def test_read_with_take_routes_to_advance(self, conn, verbs):
        item = _seed(conn, take="the loop owns it")
        _to_state(conn, item, "read")
        loop.tick_once(conn)
        assert verbs["advance"] == [item]

    def test_read_without_take_is_not_advanceable(self, conn, verbs):
        item = _seed(conn)
        _to_state(conn, item, "read")
        stats = loop.tick_once(conn)
        assert verbs["advance"] == []
        assert stats.stopped == "idle"

    def test_answered_state_is_picked_for_advance(self, conn, verbs):
        item = _seed(conn, take="freeze pile survivor")
        _to_state(conn, item, "answered")
        loop.tick_once(conn)
        assert verbs["advance"] == [item]

    def test_consumed_answer_is_not_reapplied_when_a_new_ask_opens(self, conn, monkeypatch):
        # Live catch 2026-08-31: intent answered -> advance bounced twice ->
        # bounce ask returned the item to asking -> the tick re-applied the
        # OLD intent answer and re-ran the advance, an infinite model-call
        # cycle. An answer applies only to the item's latest ask.
        item = _seed(conn, take="worth keeping")
        _to_state(conn, item, "read")
        ask1 = asks.raise_ask(
            conn, item, proposal={"kind": "intent missing", "options": []}, actor="loop"
        )
        ledger.insert_answer(conn, ask1, choice="intent")
        advances: list[int] = []

        def bouncing_advance(conn, item_id, *, actor="loop"):
            advances.append(item_id)
            asks.raise_ask(
                conn,
                item_id,
                proposal={"kind": "grader bounce, twice", "options": []},
                actor="grader",
            )

        monkeypatch.setattr("ytk.curator.advance_item", bouncing_advance)
        loop.tick_once(conn)
        assert advances == [item]  # one advance, not a cycle
        assert ledger.item_state(conn, item) == "asking"  # waiting on the NEW ask
        answer_rows = conn.execute(
            "SELECT count(*) FROM activity WHERE action = 'answer'"
        ).fetchone()[0]
        assert answer_rows == 1

    def test_late_answer_on_parked_item_is_picked(self, conn, verbs):
        # spec, Parked: an ask never expires; a late answer unparks the item
        item = _seed(conn, take="late but here")
        _to_state(conn, item, "read")
        ask_id = asks.raise_ask(
            conn, item, proposal={"kind": "transcript junk", "options": []}, actor="loop"
        )
        _to_state(conn, item, "parked")
        ledger.insert_answer(conn, ask_id, choice="keep with the warning")
        loop.tick_once(conn)
        assert ledger.item_state(conn, item) == "kept"
        assert verbs["advance"] == [item]

    def test_active_lease_blocks_pick_expired_lease_unblocks(self, conn, verbs):
        item = _seed(conn)
        conn.execute("UPDATE items SET lease_until = '9999-01-01T00:00:00' WHERE id = ?", (item,))
        assert loop.tick_once(conn).stopped == "idle"
        assert verbs["read"] == []
        conn.execute("UPDATE items SET lease_until = '2020-01-01T00:00:00' WHERE id = ?", (item,))
        loop.tick_once(conn)
        assert verbs["read"] == [item]

    def test_item_budget_stops_tick(self, conn, verbs, monkeypatch):
        monkeypatch.setattr(loop, "TICK_MAX_ITEMS", 1)
        _seed(conn, url="https://www.youtube.com/watch?v=first0000000")
        _seed(conn, url="https://www.youtube.com/watch?v=second000000")
        stats = loop.tick_once(conn)
        assert len(verbs["read"]) == 1
        assert stats.stopped == "budget"

    def test_inert_flag_stops_before_any_transition(self, conn, verbs):
        _seed(conn)
        loop.inert_path().parent.mkdir(parents=True, exist_ok=True)
        loop.inert_path().write_text("tripped: test")
        stats = loop.tick_once(conn)
        assert stats.stopped == "inert"
        assert verbs["read"] == []

    def test_read_dispatch_fills_the_gatherer_registry(self, conn, monkeypatch):
        # Live catch 2026-08-31: the hub process never imported ytk.gatherers,
        # so the loop's first real read found an empty registry and returned
        # "no gatherer" without a row. The dispatch owns the import now.
        from ytk import evidence

        _seed(conn)
        seen: list[bool] = []

        def probe(conn, item_id, *, actor="loop"):
            seen.append(bool(evidence.GATHERERS))
            ledger.insert_activity(conn, item_id, actor=actor, action="read", to_state="read")
            return evidence.ReadResult(bundle_path=None, ask_id=None)

        monkeypatch.setattr("ytk.evidence.read_item", probe)
        loop.tick_once(conn)
        assert seen == [True]

    def test_read_error_result_is_counted_and_recorded(self, conn, monkeypatch):
        from ytk import evidence

        item = _seed(conn)

        def failed_read(conn, item_id, *, actor="loop"):
            return evidence.ReadResult(bundle_path=None, ask_id=None, error="no gatherer for x")

        monkeypatch.setattr("ytk.evidence.read_item", failed_read)
        stats = loop.tick_once(conn)
        assert stats.errors == 1
        row = conn.execute(
            "SELECT reason FROM activity WHERE item_id = ? AND action = 'loop-error'", (item,)
        ).fetchone()
        assert "no gatherer" in row["reason"]

    def test_verb_error_recorded_without_transition(self, conn, monkeypatch):
        item = _seed(conn)

        def boom(conn, item_id, *, actor="loop"):
            raise RuntimeError("gatherer exploded")

        monkeypatch.setattr("ytk.evidence.read_item", boom)
        stats = loop.tick_once(conn)
        assert stats.errors == 1
        assert ledger.item_state(conn, item) == "captured"
        row = conn.execute(
            "SELECT reason FROM activity WHERE item_id = ? AND action = 'loop-error'", (item,)
        ).fetchone()
        assert "gatherer exploded" in row["reason"]

    def test_state_change_clears_lease_and_tick_count(self, conn, verbs):
        item = _seed(conn, take="t")
        loop.tick_once(conn)
        row = conn.execute(
            "SELECT lease_until, tick_count FROM items WHERE id = ?", (item,)
        ).fetchone()
        assert row["lease_until"] is None
        assert row["tick_count"] == 0


class TestStuck:
    def _expire_lease(self, conn, item):
        conn.execute("UPDATE items SET lease_until = '2020-01-01T00:00:00' WHERE id = ?", (item,))

    def test_three_ticks_without_state_change_parks(self, conn, monkeypatch):
        item = _seed(conn, take="stuck one")
        _to_state(conn, item, "answered")

        def noop_advance(conn, item_id, *, actor="loop"):
            pass  # eligible but never transitions (e.g. bundle repeatedly unreadable)

        monkeypatch.setattr("ytk.curator.advance_item", noop_advance)
        loop.tick_once(conn)
        self._expire_lease(conn, item)
        loop.tick_once(conn)
        self._expire_lease(conn, item)
        assert ledger.item_state(conn, item) == "answered"
        loop.tick_once(conn)
        assert ledger.item_state(conn, item) == "parked"
        row = conn.execute(
            "SELECT actor, reason FROM activity WHERE item_id = ? AND to_state = 'parked'",
            (item,),
        ).fetchone()
        assert row["actor"] == "loop" and row["reason"] == "stuck"

    def test_repeated_errors_also_park(self, conn, monkeypatch):
        item = _seed(conn)

        def boom(conn, item_id, *, actor="loop"):
            raise RuntimeError("still broken")

        monkeypatch.setattr("ytk.evidence.read_item", boom)
        for _ in range(3):
            loop.tick_once(conn)
            self._expire_lease(conn, item)
        assert ledger.item_state(conn, item) == "parked"


class TestHealthContent:
    def test_tick_stamps_measured_numbers(self, conn, verbs):
        item = _seed(conn, take="t")
        ledger.insert_activity(
            conn, item, actor="enricher", action="enrich", model="sonnet", tokens=5000
        )
        ledger.insert_activity(
            conn, item, actor="loop", action="loop-error", reason="rate_limit_error: slow down"
        )
        loop.tick_once(conn)
        h = loop.read_health()
        # captured -> read, then read-with-take -> advance: two moves, one tick
        assert h["items_advanced"] == 2
        assert h["errors_last_hour"] == 1
        assert h["rate_limit_hits_last_hour"] == 1
        assert h["tokens_today"] == 5000
        assert h["last_tick_at"]
        assert h["inert"] is False


class TestHealth:
    def test_read_missing_file_is_empty(self):
        assert loop.read_health() == {}

    def test_write_merges_existing_fields(self):
        loop.write_health(last_tick_at="t1", items_advanced=3)
        loop.write_health(last_sweep_at="s1")
        h = loop.read_health()
        assert h["last_tick_at"] == "t1"
        assert h["items_advanced"] == 3
        assert h["last_sweep_at"] == "s1"

    def test_write_creates_parent_and_valid_json(self):
        loop.write_health(inert=False)
        raw = loop.health_path().read_text()
        assert json.loads(raw)["inert"] is False


class TestWorkingOn:
    """#199: the health json names what the loop is doing while it does it."""

    def test_stamped_during_dispatch_and_cleared_after(self, conn, monkeypatch):
        item = _seed(conn, take="t")
        _to_state(conn, item, "answered")
        seen: dict = {}

        def fake_advance(conn2, item_id, *, actor="loop"):
            seen.update(loop.read_health().get("working_on") or {})
            ledger.insert_activity(conn2, item_id, actor=actor, action="keep", to_state="kept")

        monkeypatch.setattr("ytk.curator.advance_item", fake_advance)
        loop.tick_once(conn)
        assert seen["item_id"] == item
        assert seen["action"] == "advance"
        assert seen["started_at"]
        assert loop.read_health().get("working_on") is None

    def test_cleared_after_verb_error(self, conn, monkeypatch):
        item = _seed(conn, take="t")
        _to_state(conn, item, "answered")

        def boom(conn2, item_id, *, actor="loop"):
            raise RuntimeError("verb failed")

        monkeypatch.setattr("ytk.curator.advance_item", boom)
        loop.tick_once(conn)
        assert loop.read_health().get("working_on") is None

    def test_stamp_carries_title_when_items_row_has_one(self, conn, monkeypatch):
        item = _seed(conn, take="t")
        conn.execute("UPDATE items SET title = ? WHERE id = ?", ("A Real Title", item))
        conn.commit()
        _to_state(conn, item, "answered")
        seen: dict = {}

        def fake_advance(conn2, item_id, *, actor="loop"):
            seen.update(loop.read_health().get("working_on") or {})
            ledger.insert_activity(conn2, item_id, actor=actor, action="keep", to_state="kept")

        monkeypatch.setattr("ytk.curator.advance_item", fake_advance)
        loop.tick_once(conn)
        assert seen["title"] == "A Real Title"


class TestHealthLineWorking:
    def test_renders_working_on_with_elapsed(self):
        from datetime import UTC, datetime, timedelta

        started = (datetime.now(UTC) - timedelta(seconds=40)).isoformat()
        loop.write_health(
            last_tick_at="2026-08-31T00:00:00+00:00",
            working_on={
                "item_id": 7,
                "action": "advance",
                "title": "How to Read Papers",
                "started_at": started,
            },
        )
        line = loop.health_line()
        assert line["ok"] is True
        assert line["working"] is True
        assert "enriching How to Read Papers" in line["line"]
        assert "40s" in line["line"]

    def test_read_action_renders_as_reading(self):
        from datetime import UTC, datetime

        loop.write_health(
            working_on={
                "item_id": 7,
                "action": "read",
                "title": "Some Video",
                "started_at": datetime.now(UTC).isoformat(),
            }
        )
        assert "reading Some Video" in loop.health_line()["line"]

    def test_stale_working_on_is_ignored(self):
        from datetime import UTC, datetime, timedelta

        stale = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
        loop.write_health(
            last_tick_at="2026-08-31T00:00:00+00:00",
            working_on={"item_id": 7, "action": "advance", "title": "X", "started_at": stale},
        )
        line = loop.health_line()
        assert line["working"] is False
        assert "enriching" not in line["line"]

    def test_idle_line_reports_not_working(self):
        loop.write_health(last_tick_at="2026-08-31T00:00:00+00:00", working_on=None)
        assert loop.health_line()["working"] is False


class TestConnectionsDispatch:
    """#197 P6: an answered connections ask routes to connect.apply_links —
    advance_item would re-enrich a kept item."""

    def _connections_item(self, conn):
        item = _seed(conn, take="t")
        ledger.insert_activity(
            conn, item, actor="loop", action="keep", from_state="enriched", to_state="kept"
        )
        ask_id = asks.raise_ask(
            conn,
            item,
            proposal={
                "kind": "connections",
                "why": "1 related note argued",
                "options": ["approve", "strike some", "none"],
                "links": [{"target": "a", "target_title": "A", "argument": "x"}],
            },
            actor="connect",
        )
        asks.answer_ask(conn, ask_id, choice="approve")
        return item

    def test_answered_connections_ask_routes_to_apply_links(self, conn, monkeypatch):
        item = self._connections_item(conn)
        applied = []

        def fake_apply(conn2, item_id, *, actor="loop"):
            applied.append(item_id)
            ledger.insert_activity(
                conn2,
                item_id,
                actor=actor,
                action="connect-apply",
                from_state="answered",
                to_state="connected",
            )

        advanced = []
        monkeypatch.setattr("ytk.connect.apply_links", fake_apply)
        monkeypatch.setattr("ytk.curator.advance_item", lambda *a, **k: advanced.append(a))
        loop.tick_once(conn)
        assert applied == [item]
        assert advanced == []
        assert ledger.item_state(conn, item) == "connected"

    def test_other_answered_items_still_route_to_advance(self, conn, verbs):
        item = _seed(conn, take="t")
        _to_state(conn, item, "answered")
        loop.tick_once(conn)
        assert verbs["advance"] == [item]


class TestSweepConnectionsExpiry:
    def test_stale_connections_ask_resolves_as_none(self, conn):
        from datetime import UTC, datetime, timedelta

        item = _seed(conn, take="t")
        ledger.insert_activity(
            conn, item, actor="loop", action="keep", from_state="enriched", to_state="kept"
        )
        ask_id = asks.raise_ask(
            conn,
            item,
            proposal={
                "kind": "connections",
                "why": "1 related note argued",
                "options": ["approve", "strike some", "none"],
                "links": [{"target": "a", "target_title": "A", "argument": "x"}],
            },
            actor="connect",
        )
        old = (datetime.now(UTC) - timedelta(days=loop.ASK_PARK_DAYS + 1)).isoformat()
        conn.execute("UPDATE asks SET created_at = ? WHERE id = ?", (old, ask_id))
        conn.commit()
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "kept"
        stamped = conn.execute(
            "SELECT answered_at FROM outbox WHERE ask_id = ?", (ask_id,)
        ).fetchone()
        assert stamped["answered_at"] is not None
        row = conn.execute(
            "SELECT reason FROM activity WHERE item_id = ? AND actor = 'sweep'", (item,)
        ).fetchone()
        assert "none" in row["reason"]

    def test_fresh_connections_ask_is_left_alone(self, conn):
        item = _seed(conn, take="t")
        ledger.insert_activity(
            conn, item, actor="loop", action="keep", from_state="enriched", to_state="kept"
        )
        asks.raise_ask(
            conn,
            item,
            proposal={"kind": "connections", "why": "w", "options": [], "links": []},
            actor="connect",
        )
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "asking"
