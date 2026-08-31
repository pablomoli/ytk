"""advance_item (#197 P4): answered/read-with-take -> enriched -> kept,
two bounces raise the ask, the owner's answers steer the retry."""

import json
from dataclasses import asdict

import pytest

from ytk import asks, curator, evidence, ledger, sdk
from ytk.capture import capture
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

PASS_VERDICT = {"passed": True, "bounces": [], "spot_checks": []}
BOUNCE_VERDICT = {
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
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path / "brain")
    return tmp_path / "brain"


@pytest.fixture(autouse=True)
def quiet_store(monkeypatch):
    monkeypatch.setattr("ytk.store.upsert", lambda *a, **k: None)
    monkeypatch.setattr("ytk.store.upsert_doc", lambda *a, **k: None)
    monkeypatch.setattr(curator, "neighbor_cosine", lambda draft, mid: None)
    monkeypatch.setattr(curator, "_vocab", lambda: ["ai-agents"])


def _seed(conn, *, take="why loops beat cron", state_take=True) -> int:
    res = capture(
        conn,
        source="youtube",
        url="https://www.youtube.com/watch?v=abc123xyz00",
        surface="cli",
        text=take if state_take else None,
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
        uploader="Someone",
        upload_date="20260830",
    )
    out = evidence.evidence_dir() / f"{res.item_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(bundle)))
    conn.execute("UPDATE items SET payload_ref = ? WHERE id = ?", (str(out), res.item_id))
    ledger.insert_activity(
        conn, res.item_id, actor="loop", action="read", from_state="captured", to_state="read"
    )
    return res.item_id


def _stub_sdk(monkeypatch, drafts, verdicts):
    """Dispatch on model: Sonnet calls pop drafts, Opus calls pop verdicts."""
    calls = []

    def fake(system, user, schema, *, add_dirs=None, max_turns=20, model=None):
        calls.append({"user": user, "model": model})
        data = drafts.pop(0) if model == "claude-sonnet-5" else verdicts.pop(0)
        return sdk.StructuredResult(
            data=data, model=model, tokens=100, duration_ms=1000, usage=None
        )

    monkeypatch.setattr(sdk, "call_structured", fake)
    return calls


def test_happy_path_lands_the_note(conn, monkeypatch, brain):
    _stub_sdk(monkeypatch, [dict(DRAFT)], [dict(PASS_VERDICT)])
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "kept"
    assert res.note_path is not None and res.note_path.exists()
    assert "## My take" in res.note_path.read_text()
    states = [
        r["to_state"]
        for r in conn.execute(
            "SELECT to_state FROM activity WHERE item_id = ? AND to_state IS NOT NULL", (item_id,)
        )
    ]
    assert states[-2:] == ["enriched", "kept"]
    grade = conn.execute(
        "SELECT * FROM activity WHERE item_id = ? AND action = 'grade'", (item_id,)
    ).fetchone()
    assert grade["model"] == "claude-opus-5"
    assert json.loads(grade["inputs"])["rubric_hash"]


def test_deterministic_bounce_feeds_retry_and_spends_no_opus(conn, monkeypatch):
    calls = _stub_sdk(monkeypatch, [dict(BAD_DRAFT), dict(DRAFT)], [dict(PASS_VERDICT)])
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "kept"
    sonnet = [c for c in calls if c["model"] == "claude-sonnet-5"]
    assert len(sonnet) == 2
    assert "banned phrasing" in sonnet[1]["user"]
    assert len([c for c in calls if c["model"] == "claude-opus-5"]) == 1
    det = conn.execute(
        "SELECT detail FROM activity WHERE item_id = ? AND action = 'grade' ORDER BY id", (item_id,)
    ).fetchall()
    assert json.loads(det[0]["detail"])["layer"] == "deterministic"


def test_two_bounces_raise_the_ask(conn, monkeypatch):
    _stub_sdk(monkeypatch, [dict(DRAFT), dict(DRAFT)], [dict(BOUNCE_VERDICT), dict(BOUNCE_VERDICT)])
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "asked"
    ask = conn.execute("SELECT * FROM asks WHERE id = ?", (res.ask_id,)).fetchone()
    assert ask["kind"] == "grader bounce, twice"
    assert ledger.item_state(conn, item_id) == "asking"
    assert not list((evidence.evidence_dir().parent).glob("**/sources/**/*.md"))


def _answer(conn, ask_id, **kw):
    """answer_ask + the transition the loop writes in production (P5)."""
    from ytk import loop

    asks.answer_ask(conn, ask_id, **kw)
    row = conn.execute("SELECT id FROM answers WHERE ask_id = ?", (ask_id,)).fetchone()
    item = conn.execute("SELECT item_id FROM asks WHERE id = ?", (ask_id,)).fetchone()
    loop.apply_answer(conn, item["item_id"], row["id"])


def test_intent_answer_becomes_take_and_advances(conn, monkeypatch):
    _stub_sdk(monkeypatch, [dict(DRAFT)], [dict(PASS_VERDICT)])
    item_id = _seed(conn, state_take=False)
    ask_id = asks.raise_intent_ask(conn, item_id)
    assert ask_id is not None
    _answer(conn, ask_id, choice="intent", text="how the breaker works", surface="hub")
    take = conn.execute("SELECT * FROM takes WHERE item_id = ?", (item_id,)).fetchone()
    assert take["kind"] == "intent"
    assert take["text"] == "how the breaker works"
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "kept"
    assert "how the breaker works" in res.note_path.read_text()


def test_accept_as_is_lands_last_draft_without_model_calls(conn, monkeypatch):
    _stub_sdk(monkeypatch, [dict(DRAFT), dict(DRAFT)], [dict(BOUNCE_VERDICT), dict(BOUNCE_VERDICT)])
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "asked"
    _answer(conn, res.ask_id, choice="accept as is")

    def explode(*a, **k):
        raise AssertionError("accept as is must not spend a model call")

    monkeypatch.setattr(sdk, "call_structured", explode)
    res2 = curator.advance_item(conn, item_id)
    assert res2.outcome == "kept"
    assert res2.note_path.exists()


def test_say_what_is_wrong_feeds_owner_text(conn, monkeypatch):
    calls = _stub_sdk(
        monkeypatch,
        [dict(DRAFT), dict(DRAFT), dict(DRAFT)],
        [dict(BOUNCE_VERDICT), dict(BOUNCE_VERDICT), dict(PASS_VERDICT)],
    )
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    _answer(conn, res.ask_id, choice="say what is wrong", text="name the actual flags")
    res2 = curator.advance_item(conn, item_id)
    assert res2.outcome == "kept"
    retry = [c for c in calls if c["model"] == "claude-sonnet-5"][2]
    assert "name the actual flags" in retry["user"]


def test_ineligible_states_are_noops(conn, monkeypatch):
    _stub_sdk(monkeypatch, [], [])
    item_id = _seed(conn, state_take=False)  # read, no take
    assert curator.advance_item(conn, item_id).outcome == "skipped"
