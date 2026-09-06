"""The headless surface (#212): item, ask list, ask answer, view, grade, all
reading what the loop wrote and writing only an answer row."""

import json
from dataclasses import asdict

import pytest
from click.testing import CliRunner

from ytk import curator, evidence, headless, ledger, sdk, wake
from ytk.capture import capture
from ytk.cli import cli
from ytk.evidence import EvidenceBundle

DRAFT = {
    "thesis": "He builds a three-file agent loop whose grader the agent cannot edit.",
    "summary": "Work script, grader, rules markdown; ripgrep scans the rules.",
    "key_concepts": ["three-file loop: work script, grader, rules markdown"],
    "insights": ["Keep the grader outside the worker."],
    "interest_tags": ["ai-agents"],
    "key_moments": [{"timestamp": "0:03", "description": "grader cannot edit the work script"}],
    "recommendations": [],
    "evidence_gaps": [],
    "take_response": "Agreed; cron cannot carry blame.",
    "new_tags": [],
}
BAD_DRAFT = dict(DRAFT, thesis="This talk delves into the landscape of agent loops.")
BOUNCE = {
    "passed": False,
    "bounces": [{"check": "Thesis", "detail": "could attach to any video", "where": "thesis"}],
    "spot_checks": [],
}


@pytest.fixture
def conn():
    c = ledger.connect()
    yield c
    c.close()


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path / "brain")
    monkeypatch.setattr("ytk.store.upsert", lambda *a, **k: None)
    monkeypatch.setattr("ytk.store.upsert_doc", lambda *a, **k: None)
    monkeypatch.setattr(curator, "neighbor_cosine", lambda draft, mid: None)
    monkeypatch.setattr(curator, "_vocab", lambda: ["ai-agents"])
    monkeypatch.setattr(wake, "nudge_loop", lambda: True)


def _seed(conn) -> int:
    res = capture(
        conn,
        source="youtube",
        url="https://www.youtube.com/watch?v=abc123xyz00",
        surface="cli",
        text="why loops beat cron",
        take_kind="intent",
        log=False,
    )
    bundle = EvidenceBundle(
        source="youtube",
        url="https://www.youtube.com/watch?v=abc123xyz00",
        title="Loop Engineering",
        transcript=[
            {"start": 0, "duration": 3, "text": "we built a three-file loop for agents"},
            {"start": 3, "duration": 3, "text": "the grader cannot edit the work script"},
            {"start": 40, "duration": 3, "text": "ripgrep scans the rules markdown fast"},
        ],
        transcript_origin="api-manual",
        transcript_language="en",
        transcript_status="ok",
        description="claude-agent-sdk loops",
        duration=613,
        media_id="abc123xyz00",
    )
    out = evidence.evidence_dir() / f"{res.item_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(bundle)))
    conn.execute("UPDATE items SET payload_ref = ? WHERE id = ?", (str(out), res.item_id))
    ledger.insert_activity(
        conn, res.item_id, actor="loop", action="read", from_state="captured", to_state="read"
    )
    conn.commit()
    return res.item_id


def _stub(monkeypatch, drafts, verdicts):
    def fake(system, user, schema, *, add_dirs=None, max_turns=20, model=None):
        data = drafts.pop(0) if model == "claude-sonnet-5" else verdicts.pop(0)
        return sdk.StructuredResult(
            data=data, model=model, tokens=100, duration_ms=1000, usage=None
        )

    monkeypatch.setattr(sdk, "call_structured", fake)


def _asked(conn, monkeypatch) -> tuple[int, int]:
    _stub(monkeypatch, [dict(BAD_DRAFT), dict(DRAFT)], [dict(BOUNCE), dict(BOUNCE)])
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "asked" and res.ask_id is not None
    return item_id, res.ask_id


def test_item_shows_packet_attempts_ask_spend_and_trail(conn, monkeypatch):
    from ytk import view as V

    item_id, ask_id = _asked(conn, monkeypatch)
    out = headless.item(conn, item_id)
    v = V.latest_view(item_id)
    assert f"item {item_id}: Loop Engineering" in out and "state asking" in out
    assert f"packet {v.view_hash}" in out and "shown t:0-40" in out
    assert "attempt 1 · findings in 0 · deterministic bounce: banned phrasing" in out
    assert "attempt 2 · findings in 1 · model bounce: Thesis" in out
    assert (
        f"ask {ask_id} · grader bounce, twice" in out and f"packet {v.view_hash} attempt 2" in out
    )
    assert "calls 3 of 8" in out
    assert "enricher · enrich" in out and "grader · grade" in out


def test_ask_list_then_answer_wakes_the_loop_once(conn, monkeypatch):
    item_id, ask_id = _asked(conn, monkeypatch)
    listing = headless.ask_list(conn)
    assert f"ask {ask_id} · grader bounce, twice" in listing and "Loop Engineering" in listing
    refused = headless.ask_answer(conn, ask_id, "nope")
    assert "is not one of them" in refused
    done = headless.ask_answer(conn, ask_id, "accept as is")
    assert f"ask {ask_id} answered 'accept as is'" in done and "loop woken" in done
    assert headless.ask_answer(conn, ask_id, "accept as is") == f"ask {ask_id} was already answered"
    assert headless.ask_list(conn) == "no open asks"
    row = conn.execute("SELECT surface FROM answers WHERE ask_id = ?", (ask_id,)).fetchone()
    assert row["surface"] == "cli"


def test_view_show_summary_and_full(conn, monkeypatch):
    item_id, _ = _asked(conn, monkeypatch)
    out = headless.view_show(conn, item_id)
    assert "budget frames_shown 2" in out and "transcript lines" in out
    assert "[0:00] we built" not in out
    full = headless.view_show(conn, item_id, attempt=2, full=True)
    assert "[0:00] we built a three-file loop for agents" in full
    assert "no packet for attempt 9" in headless.view_show(conn, item_id, attempt=9)


def test_grade_dry_reruns_the_deterministic_layer_and_writes_nothing(conn, monkeypatch):
    item_id, _ = _asked(conn, monkeypatch)
    before = conn.execute("SELECT count(*) FROM activity").fetchone()[0]
    out = headless.grade(conn, item_id, attempt=1)
    assert "bounce banned phrasing" in out
    out2 = headless.grade(conn, item_id)
    assert "pass" in out2 and "model layer not run" in out2
    assert conn.execute("SELECT count(*) FROM activity").fetchone()[0] == before


def test_cli_wrappers(conn, monkeypatch):
    item_id, ask_id = _asked(conn, monkeypatch)
    runner = CliRunner()
    r = runner.invoke(cli, ["item", str(item_id)])
    assert r.exit_code == 0, r.output
    assert "state asking" in r.output
    r = runner.invoke(cli, ["ask", "list"])
    assert r.exit_code == 0 and f"ask {ask_id}" in r.output
    r = runner.invoke(cli, ["view", str(item_id), "--full"])
    assert r.exit_code == 0 and "[0:00]" in r.output
    r = runner.invoke(cli, ["grade", str(item_id), "--attempt", "1"])
    assert r.exit_code == 0 and "banned phrasing" in r.output
    r = runner.invoke(cli, ["ask", "answer", str(ask_id), "say what is wrong", "--text", "tighten"])
    assert r.exit_code == 0 and "answered 'say what is wrong'" in r.output
    row = conn.execute("SELECT text FROM answers WHERE ask_id = ?", (ask_id,)).fetchone()
    assert row["text"] == "tighten"


def test_ask_list_hides_asks_the_loop_superseded(conn, monkeypatch):
    """An unanswered ask on an item that has since moved on is not answerable."""
    item_id, ask_id = _asked(conn, monkeypatch)
    assert f"ask {ask_id}" in headless.ask_list(conn)
    ledger.insert_activity(
        conn, item_id, actor="loop", action="keep", from_state="asking", to_state="kept"
    )
    assert headless.ask_list(conn) == "no open asks"
