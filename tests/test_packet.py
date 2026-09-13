"""The packet page's reconstruction (#213): station_at over the four cases
that were wrong until measured, and the track and page builders the hub
route serves. Every row here carries an explicit instant so the tests are
a replay, not a race."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from ytk import attempt as attempt_mod
from ytk import headless, ledger
from ytk.evidence import evidence_dir

T0 = datetime(2026, 9, 6, 22, 12, tzinfo=UTC)


def at(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat()


def when(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def idle_loop(monkeypatch):
    monkeypatch.setattr("ytk.loop.health_line", lambda: {"ok": True, "working": False, "line": ""})


@pytest.fixture()
def conn():
    c = ledger.connect()
    yield c
    c.close()


def seed(conn, *, title="Loop Engineering") -> int:
    item_id = ledger.insert_item(conn, source="youtube", url="https://y/1", title=title)
    assert item_id is not None
    ledger.insert_activity(
        conn, item_id, actor="owner", action="capture", to_state="captured", at=at(0)
    )
    ledger.insert_activity(
        conn,
        item_id,
        actor="loop",
        action="read",
        from_state="captured",
        to_state="read",
        at=at(10),
    )
    return item_id


def ask(conn, item_id, *, kind, why, options, seconds, actor="loop") -> int:
    cur = conn.execute(
        "INSERT INTO asks (item_id, kind, proposal, created_at) VALUES (?, ?, ?, ?)",
        (item_id, kind, json.dumps({"kind": kind, "why": why, "options": options}), at(seconds)),
    )
    ledger.insert_activity(
        conn, item_id, actor=actor, action="ask", to_state="asking", reason=why, at=at(seconds)
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def station(conn, item_id, seconds):
    return headless.station_at(headless.history(conn, item_id), when(seconds))


def test_answered_ask_waits_at_the_proctor_until_pickup(conn):
    """Case 1: the answers row lands at the answer, the owner row at pickup.
    Between the two the packet is the proctor's, not the owner's."""
    item_id = seed(conn)
    ask_id = ask(
        conn, item_id, kind="intent missing", why="why this one?", options=["intent"], seconds=20
    )
    ledger.insert_answer(conn, ask_id, choice="intent", at=at(60))
    ledger.insert_activity(
        conn,
        item_id,
        actor="owner",
        action="answer",
        from_state="asking",
        to_state="answered",
        reason="intent",
        at=at(90),
    )

    s = station(conn, item_id, 30)
    assert s and (s.name, s.note) == ("owner", "ask · intent missing")
    s = station(conn, item_id, 61)
    assert s and s.name == "proctor" and s.note == "answered, waiting" and s.since == when(60)
    s = station(conn, item_id, 91)
    assert s and s.name == "proctor" and s.since == when(90)
    assert station(conn, item_id, 5).name == "runner"


def test_connect_with_nothing_argued_files_the_item(conn):
    """Case 2: a connect row with no ask after it is the end of the road."""
    item_id = seed(conn)
    ledger.insert_activity(
        conn,
        item_id,
        actor="loop",
        action="keep",
        from_state="enriched",
        to_state="kept",
        at=at(100),
    )
    assert station(conn, item_id, 101).name == headless.FILED
    ledger.insert_activity(
        conn,
        item_id,
        actor="connect",
        action="connect",
        model="claude-sonnet-5",
        tokens=900,
        duration_ms=12_000,
        reason="0 of 3 candidates argued",
        at=at(130),
    )
    assert station(conn, item_id, 101).note == "kept, connect pending"
    s = station(conn, item_id, 120)
    assert s and s.name == "librarian" and s.note == "arguing links"
    s = station(conn, item_id, 131)
    assert s and s.name == headless.FILED and s.note == "kept, no links"


def test_open_attempt_then_spell_checker_then_teacher(conn):
    """Case 3: the student holds the packet while the attempt is open; the
    enricher's row hands it to the spell-checker; the grade row's duration
    says when the teacher took it."""
    item_id = seed(conn)
    ledger.insert_activity(
        conn,
        item_id,
        actor="owner",
        action="answer",
        from_state="asking",
        to_state="answered",
        at=at(20),
    )
    a = attempt_mod.Attempt(
        item_id=item_id, n=1, view_hash="aaaa", take=None, previous_draft=None, opened_at=at(30)
    )
    a.save()
    s = station(conn, item_id, 40)
    assert s and (s.name, s.note) == ("student", "attempt 1")
    a.closed_at = at(100)
    a.verdict_out = {"passed": True, "layer": "model", "bounces": [], "spot_checks": []}
    a.save()
    ledger.insert_activity(
        conn,
        item_id,
        actor="enricher",
        action="enrich",
        model="claude-sonnet-5",
        tokens=2000,
        duration_ms=25_000,
        reason="attempt 1",
        inputs=json.dumps({"view_hash": "aaaa"}),
        at=at(60),
    )
    ledger.insert_activity(
        conn,
        item_id,
        actor="grader",
        action="grade",
        to_state="enriched",
        model="claude-opus-5",
        tokens=3000,
        duration_ms=30_000,
        reason="pass",
        inputs=json.dumps({"view_hash": "aaaa"}),
        at=at(100),
    )
    s = station(conn, item_id, 65)
    assert s and (s.name, s.note) == ("spell-checker", "checking")
    s = station(conn, item_id, 80)
    assert s and s.name == "teacher" and s.since == when(70)
    s = station(conn, item_id, 101)
    assert s and (s.name, s.note) == ("proctor", "passed, filing")


def test_pad_counts_every_model_call_and_runs_past_the_cap(conn):
    """Case 4: the librarian's call after an acceptance at the cap makes nine
    of eight; the page shows it, red."""
    item_id = seed(conn)
    for i in range(8):
        ledger.insert_activity(
            conn,
            item_id,
            actor="enricher" if i % 2 == 0 else "grader",
            action="enrich" if i % 2 == 0 else "grade",
            model="m",
            tokens=100,
            duration_ms=1000,
            reason=f"attempt {i // 2 + 1}" if i % 2 == 0 else "bounce: Thesis",
            at=at(100 + i),
        )
    ledger.insert_activity(
        conn,
        item_id,
        actor="loop",
        action="keep",
        from_state="enriched",
        to_state="kept",
        at=at(200),
    )
    ledger.insert_activity(
        conn,
        item_id,
        actor="connect",
        action="connect",
        model="m",
        tokens=100,
        duration_ms=1000,
        reason="2 of 3 candidates argued",
        at=at(210),
    )
    page = headless.packet(conn, item_id, when(300))
    assert page["calls"] == 9 and page["cap"] == 8 and page["tokens"] == 900
    assert page["calls"] > page["cap"]


def test_page_carries_rounds_agreement_asks_and_trail(conn, tmp_path):
    item_id = seed(conn)
    ledger.insert_activity(
        conn,
        item_id,
        actor="owner",
        action="answer",
        from_state="asking",
        to_state="answered",
        at=at(20),
    )
    ledger.insert_take(conn, item_id, kind="intent", text="why loops beat cron", at=at(20))
    draft = tmp_path / "draft.json"
    draft.write_text(
        json.dumps(
            {
                "thesis": "He builds a loop.",
                "key_concepts": ["a", "b"],
                "insights": ["x"],
                "key_moments": [],
                "interest_tags": ["ai-agents"],
            }
        )
    )
    a = attempt_mod.Attempt(
        item_id=item_id,
        n=1,
        view_hash="aaaa",
        take={"kind": "intent"},
        previous_draft=None,
        opened_at=at(30),
        closed_at=at(100),
        draft_out=str(draft),
        verdict_out={
            "passed": False,
            "layer": "model",
            "bounces": [{"check": "Grounding", "detail": "not there", "where": "t:40"}],
            "spot_checks": [{"grounded": True, "claim": "a loop", "where": "t:3"}],
        },
    )
    a.save()
    ledger.insert_activity(
        conn,
        item_id,
        actor="enricher",
        action="enrich",
        model="claude-sonnet-5",
        tokens=2000,
        duration_ms=25_000,
        reason="attempt 1",
        inputs=json.dumps({"view_hash": "aaaa"}),
        at=at(60),
    )
    ledger.insert_activity(
        conn,
        item_id,
        actor="grader",
        action="grade",
        model="claude-opus-5",
        tokens=3000,
        duration_ms=30_000,
        reason="bounce: Grounding",
        inputs=json.dumps({"view_hash": "bbbb"}),
        at=at(100),
    )
    ask_id = ask(
        conn,
        item_id,
        kind="grader bounce, twice",
        why="Grounding: not there",
        options=["accept", "say what is wrong", "drop"],
        seconds=110,
        actor="grader",
    )

    page = headless.packet(conn, item_id, when(120))
    assert page["station"]["name"] == "owner"
    assert page["agreement"] == {"status": "mismatch", "draft": "aaaa", "grade": "bbbb"}
    (rd,) = page["attempts"]
    assert rd["passed"] is False and rd["bounces"][0]["where"] == "t:40"
    assert rd["draft"] == {
        "thesis": "He builds a loop.",
        "concepts": 2,
        "insights": 1,
        "moments": 0,
        "tags": ["ai-agents"],
    }
    assert rd["writer"]["tokens"] == 2000 and rd["marker"]["view_hash"] == "bbbb"
    assert page["take"] == {"kind": "intent", "text": "why loops beat cron"}
    (k,) = page["asks"]
    assert k["id"] == ask_id and k["answer"] is None and k["options"][1] == "say what is wrong"
    assert [r["who"] for r in page["trail"]] == [
        "runner",
        "runner",
        "owner",
        "student",
        "teacher",
        "proctor",
    ]
    assert page["commands"]["view"] == f"ytk view {item_id} --attempt 1 --full"
    assert page["view"] is None
    # An open round at an earlier instant shows only what the clock reached.
    earlier = headless.packet(conn, item_id, when(50))
    assert earlier["attempts"][0]["closed_at"] is None and earlier["attempts"][0]["draft"] is None
    assert earlier["station"]["name"] == "student" and earlier["asks"] == []


def test_track_lists_only_packets_in_flight(conn):
    flying = seed(conn)
    item2 = ledger.insert_item(conn, source="web", url="https://w/2", title="Filed")
    assert item2 is not None
    ledger.insert_activity(
        conn, item2, actor="owner", action="capture", to_state="captured", at=at(0)
    )
    ledger.insert_activity(conn, item2, actor="loop", action="keep", to_state="kept", at=at(5))
    grand = ledger.insert_item(conn, source="web", url="https://w/3", title="Old")
    assert grand is not None
    ledger.insert_activity(
        conn, grand, actor="loop", action="grandfather", to_state="kept-unlabeled", at=at(0)
    )

    out = headless.track(conn, when(20))
    assert [p["id"] for p in out["packets"]] == [flying]
    assert out["packets"][0]["station"]["name"] == "runner"
    assert out["stations"][0] == "runner" and out["cap"] == 8


def test_item_text_names_the_page(conn):
    item_id = seed(conn)
    assert f"page /packet/{item_id}" in headless.item(conn, item_id)


# ---------------------------------------------------------------- the hub


@pytest.fixture()
def client():
    from ytk.ui.server import app

    return TestClient(app)


def test_packet_endpoints(client, conn):
    item_id = seed(conn)
    body = client.get("/api/packet").json()
    assert [p["id"] for p in body["packets"]] == [item_id]
    body = client.get(f"/api/packet/{item_id}").json()
    assert body["id"] == item_id and body["station"]["name"] == "runner"
    body = client.get(f"/api/packet/{item_id}", params={"t": at(5)}).json()
    assert body["station"]["note"] == "captured"
    assert client.get("/api/packet/999").status_code == 404
    assert client.get(f"/api/packet/{item_id}", params={"t": "yesterday"}).status_code == 422


def test_frame_is_served_only_from_the_evidence_dir(client, conn, tmp_path):
    from ytk import view as view_mod

    item_id = seed(conn)
    inside = evidence_dir() / "frames" / "abc" / "frame-0.jpg"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"\xff\xd8jpeg")
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"nope")
    v = view_mod.View(
        item_id=item_id,
        bundle_path="b",
        bundle_hash="h",
        source="youtube",
        transcript_origin="api-auto",
        duration=10,
        budget={},
        shown=[
            {"id": "frame:001", "kind": "frame", "path": str(inside)},
            {"id": "frame:002", "kind": "frame", "path": str(outside)},
        ],
        openable=[],
        not_shown=[],
        gaps=[],
        mounts=[],
        transcript=[],
        grounding_text="",
        rendered="",
        view_hash="vvvv",
    )
    v.path.parent.mkdir(parents=True, exist_ok=True)
    v.path.write_text(v.to_json())
    ok = client.get(f"/api/evidence/frame/{item_id}/1")
    assert ok.status_code == 200 and ok.content == b"\xff\xd8jpeg"
    assert client.get(f"/api/evidence/frame/{item_id}/2").status_code == 404
    assert client.get(f"/api/evidence/frame/{item_id}/3").status_code == 404
    page = client.get(f"/api/packet/{item_id}").json()
    assert page["view"]["frames"][0]["url"] == f"/api/evidence/frame/{item_id}/1"


def test_spa_serves_the_packet_routes(client, monkeypatch, tmp_path):
    from ytk.ui import server

    (tmp_path / "index.html").write_text("<div id=root></div>")
    monkeypatch.setattr(server, "_WEB_DIST", tmp_path)
    assert client.get("/packet").status_code == 200
    assert client.get("/packet/534").status_code == 200
    assert client.get("/packet/junk").status_code == 404


def test_live_stations_come_from_the_loop_stage_key(conn, monkeypatch):
    """Case 5, found on item 787: the grade and connect rows land when the
    verb finishes, so live the teacher and the librarian are invisible in
    the ledger. The loop's working_on stage key names them."""
    item_id = seed(conn)
    ledger.insert_activity(
        conn,
        item_id,
        actor="owner",
        action="answer",
        from_state="asking",
        to_state="answered",
        at=at(20),
    )
    a = attempt_mod.Attempt(
        item_id=item_id, n=1, view_hash="aaaa", take=None, previous_draft=None, opened_at=at(30)
    )
    a.save()
    ledger.insert_activity(
        conn,
        item_id,
        actor="enricher",
        action="enrich",
        model="m",
        tokens=100,
        duration_ms=1000,
        reason="attempt 1",
        at=at(60),
    )

    def working(key, detail=""):
        return {
            "item_id": item_id,
            "action": "advance",
            "started_at": at(30),
            "stage": {"key": key, "detail": detail},
        }

    h = headless.history(conn, item_id)
    s = headless.station_at(h, when(70), working=working("grade"))
    assert s and (s.name, s.note, s.since) == ("teacher", "marking", when(60))
    s = headless.station_at(h, when(70), working=working("checks"))
    assert s and s.name == "spell-checker"
    ledger.insert_activity(
        conn,
        item_id,
        actor="grader",
        action="grade",
        to_state="enriched",
        model="m",
        tokens=100,
        duration_ms=1000,
        reason="pass",
        at=at(100),
    )
    ledger.insert_activity(
        conn,
        item_id,
        actor="loop",
        action="keep",
        from_state="enriched",
        to_state="kept",
        at=at(101),
    )
    h = headless.history(conn, item_id)
    s = headless.station_at(h, when(110), working=working("connect", "arguing 5 candidates"))
    assert s and (s.name, s.note, s.since) == ("librarian", "arguing 5 candidates", when(101))
    assert headless.station_at(h, when(110)).name == headless.FILED
    # a replay instant never consults the loop
    monkeypatch.setattr("ytk.loop.health_line", lambda: {"working_on": working("connect")})
    assert headless.packet(conn, item_id, when(110))["station"]["name"] == headless.FILED
    assert headless.packet(conn, item_id)["station"]["name"] == "librarian"


def test_ask_note_names_the_kind_and_ask_rows_are_the_proctors(conn):
    item_id = seed(conn)
    ask(
        conn,
        item_id,
        kind="grader bounce, twice",
        why="What I do not want: rubric bars openings",
        options=["accept as is", "say what is wrong", "drop"],
        seconds=50,
        actor="grader",
    )
    s = station(conn, item_id, 60)
    assert s and s.note == "ask · grader bounce, twice"
    page = headless.packet(conn, item_id, when(60))
    assert page["trail"][-1]["who"] == "proctor"


def test_music_only_packet_has_no_timeline(conn):
    from ytk import view as view_mod

    item_id = seed(conn)
    v = view_mod.View(
        item_id=item_id,
        bundle_path="b",
        bundle_hash="h",
        source="instagram",
        transcript_origin="whisper",
        duration=None,
        budget={},
        shown=[{"id": "t:0-0", "kind": "transcript", "t": 0.0, "t_end": 0.0, "lines": 1}],
        openable=[],
        not_shown=[],
        gaps=[],
        mounts=[],
        transcript=[{"start": 0.0, "text": "Music"}],
        grounding_text="",
        rendered="",
        view_hash="vvvv",
    )
    v.path.parent.mkdir(parents=True, exist_ok=True)
    v.path.write_text(v.to_json())
    page = headless.packet(conn, item_id)
    assert page["view"]["duration"] is None and page["view"]["nlines"] == 1
