"""P3 (#197): the hub delivers the outbox — GET renders the digest (the
delivery view, stamping presented_at), POST answers through the one path."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ytk import asks, ledger

QUALITY = {
    "kind": "transcript junk",
    "why": "no captions and no transcript",
    "options": ["retry with Whisper", "keep with the warning", "drop"],
}


@pytest.fixture(autouse=True)
def stub_spawn(monkeypatch):
    """An answer nudges the loop (P5); tests record the wake instead of
    letting a thread near model work."""
    calls: list[bool] = []
    monkeypatch.setattr("ytk.ui.hub.wake_loop", lambda: calls.append(True))
    return calls


@pytest.fixture()
def client():
    from ytk.ui.server import app

    return TestClient(app)


def seed_ask(kind_proposal=QUALITY, url="https://y/1"):
    conn = ledger.connect()
    item_id = ledger.insert_item(conn, source="youtube", url=url, title="T")
    assert item_id is not None
    ledger.insert_activity(conn, item_id, actor="owner", action="capture", to_state="captured")
    ask_id = asks.raise_ask(conn, item_id, proposal=kind_proposal)
    conn.close()
    return item_id, ask_id


def test_outbox_returns_digest_and_stamps_presented(client):
    _, ask_id = seed_ask()
    body = client.get("/api/outbox").json()
    assert [a["subkind"] for a in body["asks"]] == ["transcript junk"]
    assert body["asks"][0]["proposal"]["options"] == QUALITY["options"]
    assert body["speaks"] == []
    assert body["parked"] == {"count": 0, "oldest": None}
    assert body["loop"]["ok"] is True
    conn = ledger.connect()
    stamped = conn.execute(
        "SELECT presented_at FROM outbox WHERE ask_id = ?", (ask_id,)
    ).fetchone()["presented_at"]
    conn.close()
    assert stamped is not None


def test_answer_records_and_leaves_transition_to_loop(client):
    item_id, ask_id = seed_ask()
    resp = client.post(
        "/api/outbox/answer",
        json={"ask_id": ask_id, "choice": "keep with the warning"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "asking"  # the loop writes the transition
    conn = ledger.connect()
    assert ledger.item_state(conn, item_id) == "asking"
    conn.close()
    assert client.get("/api/outbox").json()["asks"] == []


def test_answer_twice_is_a_noop(client):
    _, ask_id = seed_ask()
    client.post("/api/outbox/answer", json={"ask_id": ask_id, "choice": "drop"})
    again = client.post(
        "/api/outbox/answer", json={"ask_id": ask_id, "choice": "keep with the warning"}
    )
    assert again.status_code == 200
    assert again.json() == {"answer_id": None, "state": "asking", "advancing": False}


def test_answer_unknown_ask_is_404(client):
    resp = client.post("/api/outbox/answer", json={"ask_id": 999, "choice": "drop"})
    assert resp.status_code == 404


def test_parked_line_counts_parked_items(client):
    conn = ledger.connect()
    item_id = ledger.insert_item(conn, source="youtube", url="https://y/p", title="P")
    assert item_id is not None
    ledger.insert_activity(conn, item_id, actor="owner", action="capture", to_state="captured")
    ledger.insert_activity(
        conn, item_id, actor="sweep", action="park", from_state="asking", to_state="parked"
    )
    conn.close()
    parked = client.get("/api/outbox").json()["parked"]
    assert parked["count"] == 1
    assert parked["oldest"] is not None


def test_non_drop_answer_wakes_the_loop(client, stub_spawn):
    _, ask_id = seed_ask()
    body = client.post(
        "/api/outbox/answer", json={"ask_id": ask_id, "choice": "keep with the warning"}
    ).json()
    assert body["advancing"] is True
    assert stub_spawn == [True]


def test_drop_answer_reaches_the_loop_but_reports_not_advancing(client, stub_spawn):
    # P5: the loop writes the dropped transition too, so a drop still nudges.
    _, ask_id = seed_ask()
    body = client.post("/api/outbox/answer", json={"ask_id": ask_id, "choice": "drop"}).json()
    assert body["advancing"] is False
    assert stub_spawn == [True]
