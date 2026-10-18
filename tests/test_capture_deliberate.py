"""Step 3 (docs/design/ingestion): a deliberate capture is the sentence.

Deliberate surfaces (ytk add, the per-source adds, hub picks and $$, an
interactive reels pick) carry a reflex take when the owner wrote nothing,
so the intent ask never fires. Passive surfaces (playlist sync, feed,
reels --all) keep the ask. A deliberate re-capture answers an open intent
ask or revives a dropped item. Every downstream gate still runs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from click.testing import CliRunner

from ytk import asks, capture, evidence, ledger, loop
from ytk.cli import cli
from ytk.evidence import EvidenceBundle

WATCH = "https://www.youtube.com/watch?v=abcdefghijk"
SHORT = "https://youtu.be/abcdefghijk"


@pytest.fixture
def conn():
    c = ledger.connect()
    yield c
    c.close()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def no_fetch(url, **kw):
        raise RuntimeError("offline in tests")

    monkeypatch.setattr("ytk.fetch.fetch", no_fetch)
    monkeypatch.setattr("ytk.wake.nudge_loop", lambda: True)


def _bundle(url: str, *, ok: bool = True) -> EvidenceBundle:
    return EvidenceBundle(
        source="youtube",
        url=url,
        title="T",
        transcript=[{"start": 0, "duration": 2, "text": "real words here"}] if ok else [],
        transcript_origin="api-manual" if ok else "none",
        transcript_language="en" if ok else None,
        transcript_status="ok" if ok else "none",
    )


@pytest.fixture
def gather(monkeypatch):
    import ytk.gatherers  # noqa: F401 — fill the registry before overriding

    monkeypatch.setitem(evidence.GATHERERS, "youtube", lambda url, title: _bundle(url))


def _takes(conn, item_id):
    return conn.execute(
        "SELECT kind, text, surface FROM takes WHERE item_id = ? ORDER BY id", (item_id,)
    ).fetchall()


def _intent_asks(conn, item_id) -> int:
    return conn.execute(
        "SELECT count(*) FROM asks WHERE item_id = ? AND kind = 'intent missing'", (item_id,)
    ).fetchone()[0]


def _only_item(conn) -> int:
    return conn.execute("SELECT id FROM items").fetchone()["id"]


def _read_and_drop(conn, item_id):
    """The path every one of the 25 drops took: read, ask, window expired."""
    ledger.insert_activity(conn, item_id, actor="loop", action="read", to_state="read")
    ask_id = asks.raise_intent_ask(conn, item_id)
    assert ask_id is not None
    old = (datetime.now(UTC) - timedelta(days=9)).isoformat()
    conn.execute("UPDATE outbox SET presented_at = ? WHERE ask_id = ?", (old, ask_id))
    conn.commit()
    loop.sweep(conn)
    assert ledger.item_state(conn, item_id) == "dropped"


class TestDeliberateSurfaces:
    def test_silent_add_carries_a_reflex_take_and_reads_without_asking(self, conn, gather):
        result = CliRunner().invoke(cli, ["add", WATCH])
        assert result.exit_code == 0, result.output
        item = _only_item(conn)
        assert [tuple(t) for t in _takes(conn, item)] == [("reflex", "", "cli")]
        rr = evidence.read_item(conn, item)
        assert rr.ask_id is None
        assert ledger.item_state(conn, item) == "read"
        pick = loop.next_advanceable(conn)
        assert pick is not None and (pick.item_id, pick.action) == (item, "advance")

    def test_add_with_note_is_an_intent_take(self, conn):
        CliRunner().invoke(cli, ["add", WATCH, "--note", "the caching trick"])
        assert [tuple(t) for t in _takes(conn, _only_item(conn))] == [
            ("intent", "the caching trick", "cli")
        ]

    @pytest.mark.parametrize("cmd", ["add-tiktok", "add-instagram", "ingest"])
    def test_per_source_adds_are_deliberate(self, conn, cmd):
        url = {
            "add-tiktok": "https://www.tiktok.com/@u/video/123",
            "add-instagram": "https://www.instagram.com/reel/xyz/",
            "ingest": "https://example.org/a",
        }[cmd]
        result = CliRunner().invoke(cli, [cmd, url])
        assert result.exit_code == 0, result.output
        assert [t["kind"] for t in _takes(conn, _only_item(conn))] == ["reflex"]

    def test_hub_pick_without_thought_is_deliberate(self, conn, monkeypatch):
        import ytk.ui.hub as hub

        monkeypatch.setattr(hub, "wake_loop", lambda: None)
        hub.ingest_via_cli(WATCH, "")
        assert [tuple(t) for t in _takes(conn, _only_item(conn))] == [("reflex", "", "hub")]

    def test_quality_gate_still_runs_first(self, conn, monkeypatch):
        import ytk.gatherers  # noqa: F401

        monkeypatch.setitem(evidence.GATHERERS, "youtube", lambda u, t: _bundle(u, ok=False))
        CliRunner().invoke(cli, ["add", WATCH])
        item = _only_item(conn)
        rr = evidence.read_item(conn, item)
        kind = conn.execute("SELECT kind FROM asks WHERE id = ?", (rr.ask_id,)).fetchone()
        assert kind["kind"] == "transcript junk"


class TestPassiveSurfaces:
    def test_sync_capture_still_asks_why(self, conn, gather):
        res = capture.capture(
            conn, source="youtube", url=WATCH, surface="sync", actor="sweep", log=False
        )
        assert _takes(conn, res.item_id) == []
        evidence.read_item(conn, res.item_id)
        assert _intent_asks(conn, res.item_id) == 1

    def test_feed_capture_carries_no_take(self, conn, tmp_path):
        urls = tmp_path / "urls.txt"
        urls.write_text(WATCH + "\n")
        result = CliRunner().invoke(cli, ["feed", "--file", str(urls)])
        assert result.exit_code == 0, result.output
        assert _takes(conn, _only_item(conn)) == []


class TestAgentShell:
    def test_agent_add_without_note_is_not_deliberate(self, conn, monkeypatch, gather):
        monkeypatch.setenv("CLAUDECODE", "1")
        result = CliRunner().invoke(cli, ["add", WATCH])
        assert result.exit_code == 0, result.output
        item = _only_item(conn)
        assert _takes(conn, item) == []
        actor = conn.execute(
            "SELECT actor FROM activity WHERE item_id = ? AND action = 'capture'", (item,)
        ).fetchone()
        assert actor["actor"] == "agent"
        evidence.read_item(conn, item)
        assert _intent_asks(conn, item) == 1
        assert "owner is asked why" in result.output

    def test_agent_note_is_marked_as_the_agents(self, conn, monkeypatch):
        monkeypatch.setenv("AI_AGENT", "some-agent")
        CliRunner().invoke(cli, ["add", WATCH, "--note", "owner pasted it about caching"])
        assert [tuple(t) for t in _takes(conn, _only_item(conn))] == [
            ("intent", "owner pasted it about caching", "agent")
        ]

    def test_agent_never_revives(self, conn, monkeypatch):
        res = capture.capture(conn, source="youtube", url=WATCH, surface="sync", log=False)
        _read_and_drop(conn, res.item_id)
        monkeypatch.setenv("CLAUDECODE", "1")
        CliRunner().invoke(cli, ["add", WATCH])
        assert ledger.item_state(conn, res.item_id) == "dropped"


class TestDeliberateRecapture:
    def test_answers_the_open_intent_ask(self, conn, gather):
        res = capture.capture(conn, source="youtube", url=WATCH, surface="sync", log=False)
        evidence.read_item(conn, res.item_id)
        assert ledger.item_state(conn, res.item_id) == "asking"
        again = capture.capture(
            conn, source="youtube", url=SHORT, surface="cli", log=False, deliberate=True
        )
        assert (again.item_id, again.reclaimed) == (res.item_id, "answered")
        ans = conn.execute("SELECT choice, text FROM answers").fetchone()
        assert (ans["choice"], ans["text"]) == ("just want it", None)
        assert [t["kind"] for t in _takes(conn, res.item_id)] == ["reflex"]
        pick = loop.next_advanceable(conn)
        assert pick is not None and pick.action == "answer"
        loop.apply_answer(conn, pick.item_id, pick.answer_id)
        assert ledger.item_state(conn, res.item_id) == "answered"

    def test_note_answers_as_intent(self, conn, gather):
        res = capture.capture(conn, source="youtube", url=WATCH, surface="sync", log=False)
        evidence.read_item(conn, res.item_id)
        capture.capture(
            conn,
            source="youtube",
            url=WATCH,
            surface="hub",
            text="for the shader part",
            log=False,
            deliberate=True,
        )
        ans = conn.execute("SELECT choice, text FROM answers").fetchone()
        assert (ans["choice"], ans["text"]) == ("intent", "for the shader part")
        assert [tuple(t)[:2] for t in _takes(conn, res.item_id)] == [
            ("intent", "for the shader part")
        ]

    def test_revives_a_dropped_item_through_read_again(self, conn, gather):
        res = capture.capture(conn, source="youtube", url=WATCH, surface="sync", log=False)
        _read_and_drop(conn, res.item_id)
        again = capture.capture(
            conn, source="youtube", url=SHORT, surface="cli", log=False, deliberate=True
        )
        assert again.reclaimed == "revived"
        assert ledger.item_state(conn, res.item_id) == "captured"
        row = conn.execute(
            "SELECT actor, from_state FROM activity WHERE item_id = ? AND action = 'revive'",
            (res.item_id,),
        ).fetchone()
        assert (row["actor"], row["from_state"]) == ("owner", "dropped")
        pick = loop.next_advanceable(conn)
        assert pick is not None and (pick.item_id, pick.action) == (res.item_id, "read")
        rr = evidence.read_item(conn, res.item_id)
        assert rr.ask_id is None
        assert ledger.item_state(conn, res.item_id) == "read"

    def test_passive_recapture_never_revives(self, conn):
        res = capture.capture(conn, source="youtube", url=WATCH, surface="sync", log=False)
        _read_and_drop(conn, res.item_id)
        capture.capture(conn, source="youtube", url=WATCH, surface="sync", log=False)
        assert ledger.item_state(conn, res.item_id) == "dropped"

    def test_silent_recapture_of_a_kept_item_adds_nothing(self, conn):
        res = capture.capture(conn, source="youtube", url=WATCH, surface="cli", log=False)
        ledger.insert_activity(conn, res.item_id, actor="loop", action="keep", to_state="kept")
        again = capture.capture(
            conn, source="youtube", url=WATCH, surface="cli", log=False, deliberate=True
        )
        assert (again.reclaimed, again.take_id) == (None, None)
        assert _takes(conn, res.item_id) == []

    def test_recapture_before_the_read_gives_the_missing_take(self, conn, gather):
        res = capture.capture(conn, source="youtube", url=WATCH, surface="sync", log=False)
        capture.capture(
            conn, source="youtube", url=WATCH, surface="cli", log=False, deliberate=True
        )
        assert [t["kind"] for t in _takes(conn, res.item_id)] == ["reflex"]
        assert evidence.read_item(conn, res.item_id).ask_id is None


class TestOneIdentity:
    @pytest.mark.parametrize(
        ("first", "second"),
        [
            (WATCH, SHORT),
            (SHORT, "https://www.youtube.com/shorts/abcdefghijk"),
            (WATCH, WATCH + "&t=42s"),
        ],
    )
    def test_youtube_shapes_are_one_item(self, conn, first, second):
        a = capture.capture(conn, source="youtube", url=first, surface="cli", log=False)
        b = capture.capture(conn, source="youtube", url=second, surface="sync", log=False)
        assert b.duplicate and b.item_id == a.item_id
        assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 1

    def test_instagram_share_params_are_one_item(self, conn):
        a = capture.capture(
            conn,
            source="instagram",
            url="https://www.instagram.com/reel/AbC/?igsh=x1",
            surface="cli",
            log=False,
        )
        b = capture.capture(
            conn,
            source="instagram",
            url="https://www.instagram.com/reel/AbC/",
            surface="hub",
            log=False,
        )
        assert b.item_id == a.item_id

    def test_different_videos_stay_apart(self, conn):
        capture.capture(conn, source="youtube", url=WATCH, surface="cli", log=False)
        b = capture.capture(
            conn, source="youtube", url="https://youtu.be/abcdefghijX", surface="cli", log=False
        )
        assert not b.duplicate

    def test_web_query_strings_are_distinct_pages(self, conn):
        capture.capture(conn, source="web", url="https://e.org/p?id=1", surface="cli", log=False)
        b = capture.capture(
            conn, source="web", url="https://e.org/p?id=2", surface="cli", log=False
        )
        assert not b.duplicate


class TestExpiryRunsFromPresentation:
    def _asking(self, conn, *, created_days: int, presented_days: int | None):
        res = capture.capture(conn, source="youtube", url=WATCH, surface="sync", log=False)
        ledger.insert_activity(conn, res.item_id, actor="loop", action="read", to_state="read")
        ask_id = asks.raise_intent_ask(conn, res.item_id)
        created = (datetime.now(UTC) - timedelta(days=created_days)).isoformat()
        presented = (
            None
            if presented_days is None
            else (datetime.now(UTC) - timedelta(days=presented_days)).isoformat()
        )
        conn.execute("UPDATE asks SET created_at = ? WHERE id = ?", (created, ask_id))
        conn.execute(
            "UPDATE outbox SET created_at = ?, presented_at = ? WHERE ask_id = ?",
            (created, presented, ask_id),
        )
        conn.commit()
        return res.item_id

    def test_never_presented_never_expires(self, conn):
        item = self._asking(conn, created_days=60, presented_days=None)
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "asking"

    def test_old_ask_presented_recently_waits(self, conn):
        item = self._asking(conn, created_days=60, presented_days=2)
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "asking"

    def test_presented_past_the_window_expires(self, conn):
        item = self._asking(conn, created_days=60, presented_days=8)
        loop.sweep(conn)
        assert ledger.item_state(conn, item) == "dropped"
        detail = conn.execute(
            "SELECT detail FROM activity WHERE item_id = ? AND action = 'expire'", (item,)
        ).fetchone()
        assert json.loads(detail["detail"])["non_answer"] == "intent window expired"
