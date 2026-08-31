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


def test_bounce_ask_carries_draft_objections_title_and_thumbnail(client, tmp_path):
    # Live catch 2026-08-31: the bounce card asked the owner to judge a draft
    # it did not show. Context is attached at render time from the ledger and
    # disk, so already-open asks gain it without a re-raise.
    import json as _json

    bundle = tmp_path / "b.json"
    bundle.write_text(
        _json.dumps(
            {
                "source": "youtube",
                "url": "https://y/2",
                "title": "How to read papers",
                "thumbnail": "https://i.ytimg.com/vi/x/hq720.jpg",
                "transcript": [],
                "transcript_origin": "api-manual",
                "transcript_language": "en",
                "transcript_status": "ok",
            }
        )
    )
    draft = tmp_path / "d.json"
    draft.write_text(
        _json.dumps(
            {
                "thesis": "A six-step workflow for deep reading.",
                "summary": "Front-load context, then alternate reads.",
                "key_concepts": ["deep research report"],
                "insights": ["interview the first author"],
                "interest_tags": [],
                "key_moments": [],
                "recommendations": [],
                "evidence_gaps": [],
                "take_response": "This answers your reading-list intent.",
                "new_tags": [],
            }
        )
    )
    conn = ledger.connect()
    item_id = ledger.insert_item(conn, source="youtube", url="https://y/2")
    assert item_id is not None
    conn.execute("UPDATE items SET payload_ref = ? WHERE id = ?", (str(bundle), item_id))
    ledger.insert_activity(conn, item_id, actor="owner", action="capture", to_state="captured")
    ledger.insert_activity(conn, item_id, actor="enricher", action="enrich", output_ref=str(draft))
    ledger.insert_activity(
        conn,
        item_id,
        actor="grader",
        action="grade",
        detail=_json.dumps(
            {
                "layer": "deterministic",
                "bounces": [
                    {"check": "concept grounding", "detail": "not findable", "where": None}
                ],
            }
        ),
    )
    asks.raise_ask(
        conn,
        item_id,
        proposal={"kind": "grader bounce, twice", "options": ["accept as is", "drop"]},
    )
    conn.close()
    body = client.get("/api/outbox").json()
    card = body["asks"][0]
    assert card["title"] == "How to read papers"  # bundle fallback, items.title NULL
    assert card["thumbnail"] == "https://i.ytimg.com/vi/x/hq720.jpg"
    assert card["draft"]["thesis"] == "A six-step workflow for deep reading."
    assert card["draft"]["key_concepts"] == ["deep research report"]
    assert card["objections"] == [{"check": "concept grounding", "detail": "not findable"}]


def test_intent_ask_still_gets_title_and_thumbnail_but_no_draft(client, tmp_path):
    import json as _json

    bundle = tmp_path / "b2.json"
    bundle.write_text(
        _json.dumps(
            {
                "source": "youtube",
                "url": "https://y/3",
                "title": "T3",
                "thumbnail": "https://i/t.jpg",
            }
        )
    )
    conn = ledger.connect()
    item_id = ledger.insert_item(conn, source="youtube", url="https://y/3")
    assert item_id is not None
    conn.execute("UPDATE items SET payload_ref = ? WHERE id = ?", (str(bundle), item_id))
    ledger.insert_activity(conn, item_id, actor="owner", action="capture", to_state="captured")
    asks.raise_intent_ask(conn, item_id)
    conn.close()
    body = client.get("/api/outbox").json()
    card = body["asks"][0]
    assert card["title"] == "T3"
    assert card["thumbnail"] == "https://i/t.jpg"
    assert card.get("draft") is None
