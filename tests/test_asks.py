"""Asks + outbox (#197 P3): one raise path, one answer path.

Invariants from the spec (Asks; Voice and consolidation): at most one open
ask per item; every ask gets an outbox row; answers are insert-only and the
acting surface transitions the item (actor "owner") until P5's loop takes
over; the intent window ships in the proposal payload so P5's sweep can
enforce expiry without a schema change.
"""

from __future__ import annotations

import json

import pytest

from ytk import asks, ledger


@pytest.fixture()
def conn():
    c = ledger.connect()
    yield c
    c.close()


def item(conn, url="https://y/1") -> int:
    item_id = ledger.insert_item(conn, source="youtube", url=url, title="T")
    assert item_id is not None
    ledger.insert_activity(conn, item_id, actor="owner", action="capture", to_state="captured")
    return item_id


QUALITY = {
    "kind": "transcript junk",
    "why": "no captions and no transcript",
    "options": ["retry with Whisper", "keep with the warning", "drop"],
}


# ------------------------------------------------------------------ raise


def test_raise_ask_inserts_ask_outbox_and_transition(conn):
    item_id = item(conn)
    ask_id = asks.raise_ask(conn, item_id, proposal=QUALITY, actor="loop")
    assert ask_id is not None
    row = conn.execute("SELECT * FROM asks WHERE id = ?", (ask_id,)).fetchone()
    assert row["kind"] == "transcript junk"
    out = conn.execute("SELECT * FROM outbox WHERE ask_id = ?", (ask_id,)).fetchone()
    assert out["kind"] == "ask"
    assert out["subkind"] == "transcript junk"
    assert out["item_id"] == item_id
    assert json.loads(out["payload"])["why"] == QUALITY["why"]
    assert out["presented_at"] is None
    assert out["answered_at"] is None
    assert ledger.item_state(conn, item_id) == "asking"


def test_raise_ask_noop_while_an_ask_is_open(conn):
    item_id = item(conn)
    first = asks.raise_ask(conn, item_id, proposal=QUALITY)
    second = asks.raise_ask(
        conn, item_id, proposal={"kind": "intent missing", "why": "no take", "options": []}
    )
    assert first is not None
    assert second is None
    assert conn.execute("SELECT count(*) FROM asks").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM outbox").fetchone()[0] == 1


def test_raise_ask_allowed_again_after_answer(conn):
    item_id = item(conn)
    first = asks.raise_ask(conn, item_id, proposal=QUALITY)
    asks.answer_ask(conn, first, choice="keep with the warning", surface="hub")
    second = asks.raise_ask(
        conn, item_id, proposal={"kind": "intent missing", "why": "no take", "options": []}
    )
    assert second is not None


# ------------------------------------------------------------------ intent


def test_intent_ask_raised_for_item_without_take(conn):
    item_id = item(conn)
    ask_id = asks.raise_intent_ask(conn, item_id)
    assert ask_id is not None
    row = conn.execute("SELECT * FROM asks WHERE id = ?", (ask_id,)).fetchone()
    assert row["kind"] == "intent missing"
    proposal = json.loads(row["proposal"])
    # The 7-day window is a stated guess (spec, Asks); P5's sweep reads it
    # from the payload, so it must ship with the ask from day one.
    assert proposal["window_days"] == 7
    assert "drop" in proposal["options"]


def test_intent_ask_skipped_when_take_exists(conn):
    item_id = item(conn)
    ledger.insert_take(conn, item_id, kind="intent", text="want the CLI trick")
    assert asks.raise_intent_ask(conn, item_id) is None


# ------------------------------------------------------------------ answer


def test_answer_records_row_stamps_outbox_and_transitions(conn):
    item_id = item(conn)
    ask_id = asks.raise_ask(conn, item_id, proposal=QUALITY)
    answer_id = asks.answer_ask(
        conn, ask_id, choice="keep with the warning", text=None, surface="hub"
    )
    assert answer_id is not None
    out = conn.execute("SELECT * FROM outbox WHERE ask_id = ?", (ask_id,)).fetchone()
    assert out["answered_at"] is not None
    assert ledger.item_state(conn, item_id) == "answered"
    last = conn.execute(
        "SELECT actor, from_state FROM activity WHERE item_id = ? ORDER BY id DESC", (item_id,)
    ).fetchone()
    assert last["actor"] == "owner"
    assert last["from_state"] == "asking"


def test_answer_drop_transitions_to_dropped(conn):
    item_id = item(conn)
    ask_id = asks.raise_ask(conn, item_id, proposal=QUALITY)
    asks.answer_ask(conn, ask_id, choice="drop", surface="hub")
    assert ledger.item_state(conn, item_id) == "dropped"


def test_answer_twice_is_a_noop(conn):
    item_id = item(conn)
    ask_id = asks.raise_ask(conn, item_id, proposal=QUALITY)
    asks.answer_ask(conn, ask_id, choice="drop", surface="hub")
    again = asks.answer_ask(conn, ask_id, choice="keep with the warning", surface="cli")
    assert again is None
    assert ledger.item_state(conn, item_id) == "dropped"
    transitions = conn.execute(
        "SELECT count(*) FROM activity WHERE item_id = ? AND to_state IS NOT NULL", (item_id,)
    ).fetchone()[0]
    assert transitions == 3  # captured, asking, dropped — no fourth


# ------------------------------------------------------------------ backfill


def test_backfill_gives_preexisting_asks_outbox_rows(conn):
    item_id = item(conn)
    # P2's gate inserted asks directly, before the outbox existed.
    cur = conn.execute(
        "INSERT INTO asks (item_id, kind, proposal, created_at) VALUES (?, ?, ?, ?)",
        (item_id, "transcript junk", json.dumps(QUALITY), ledger.now()),
    )
    orphan = cur.lastrowid
    created = asks.backfill_outbox(conn)
    assert created == 1
    out = conn.execute("SELECT * FROM outbox WHERE ask_id = ?", (orphan,)).fetchone()
    assert out["subkind"] == "transcript junk"
    assert asks.backfill_outbox(conn) == 0  # idempotent


# ------------------------------------------------------------------ digest


def test_open_outbox_orders_quality_before_intent(conn):
    a = item(conn, url="https://y/a")
    b = item(conn, url="https://y/b")
    asks.raise_intent_ask(conn, a)
    asks.raise_ask(conn, b, proposal=QUALITY)
    rows = asks.open_outbox(conn)
    assert [r["subkind"] for r in rows] == ["transcript junk", "intent missing"]


def test_answered_rows_leave_the_open_outbox(conn):
    item_id = item(conn)
    ask_id = asks.raise_ask(conn, item_id, proposal=QUALITY)
    asks.answer_ask(conn, ask_id, choice="drop", surface="hub")
    assert asks.open_outbox(conn) == []


def test_mark_presented_stamps_once(conn):
    item_id = item(conn)
    ask_id = asks.raise_ask(conn, item_id, proposal=QUALITY)
    rows = asks.open_outbox(conn)
    asks.mark_presented(conn, [rows[0]["id"]])
    first = conn.execute("SELECT presented_at FROM outbox WHERE ask_id = ?", (ask_id,)).fetchone()[
        "presented_at"
    ]
    assert first is not None
    asks.mark_presented(conn, [rows[0]["id"]])
    second = conn.execute("SELECT presented_at FROM outbox WHERE ask_id = ?", (ask_id,)).fetchone()[
        "presented_at"
    ]
    # presented_at is the answer-latency instrument's zero point; re-renders
    # must not move it.
    assert second == first


# ---------------------------------------------------- read gate integration


def test_read_gate_ask_lands_in_outbox(conn, monkeypatch):
    from ytk import evidence

    item_id = item(conn)
    monkeypatch.setitem(
        evidence.GATHERERS,
        "youtube",
        lambda url, title: evidence.EvidenceBundle(
            source="youtube",
            url=url,
            title=title,
            transcript=[],
            transcript_origin="none",
            transcript_language=None,
            transcript_status="none",
            description="d",
            caption=None,
            text=None,
            frames=[],
            gaps=[],
        ),
    )
    result = evidence.read_item(conn, item_id)
    assert result.ask_id is not None
    out = conn.execute("SELECT * FROM outbox WHERE ask_id = ?", (result.ask_id,)).fetchone()
    assert out is not None
    assert out["subkind"] == "transcript junk"


def clean_bundle(url, title):
    from ytk import evidence

    return evidence.EvidenceBundle(
        source="youtube",
        url=url,
        title=title,
        transcript=[{"start": 0, "duration": 2, "text": "hello there"}],
        transcript_origin="api-manual",
        transcript_language="en",
        transcript_status="ok",
        description="d",
        caption=None,
        text=None,
        frames=[],
        gaps=[],
    )


def test_clean_read_without_take_raises_intent_ask(conn, monkeypatch):
    from ytk import evidence

    item_id = item(conn)
    monkeypatch.setitem(evidence.GATHERERS, "youtube", clean_bundle)
    result = evidence.read_item(conn, item_id)
    assert result.ask_id is not None
    kind = conn.execute("SELECT kind FROM asks WHERE id = ?", (result.ask_id,)).fetchone()["kind"]
    assert kind == "intent missing"
    assert ledger.item_state(conn, item_id) == "asking"


def test_clean_read_with_take_stays_at_read(conn, monkeypatch):
    from ytk import evidence

    item_id = item(conn)
    ledger.insert_take(conn, item_id, kind="intent", text="the CLI trick")
    monkeypatch.setitem(evidence.GATHERERS, "youtube", clean_bundle)
    result = evidence.read_item(conn, item_id)
    assert result.ask_id is None
    assert ledger.item_state(conn, item_id) == "read"
