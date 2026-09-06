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


def test_landing_renames_a_handle_titled_item(conn, monkeypatch, brain):
    """The digest card and the ledger row carry the drafted title once the
    note lands, so an Instagram item stops reading as its author's handle."""
    item_id = _seed(conn)
    bundle_path = conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item_id,)).fetchone()[
        0
    ]
    raw = json.loads(open(bundle_path).read())
    raw.update(source="instagram", title="luchen_xi", uploader="luchen_xi", media_id=None)
    open(bundle_path, "w").write(json.dumps(raw))
    conn.execute("UPDATE items SET title = 'luchen_xi' WHERE id = ?", (item_id,))
    _stub_sdk(monkeypatch, [dict(DRAFT, title="Ink-wash Gaussian splats")], [dict(PASS_VERDICT)])
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "kept"
    row = conn.execute("SELECT title FROM items WHERE id = ?", (item_id,)).fetchone()
    assert row["title"] == "Ink-wash Gaussian splats"


def test_retry_is_a_patch_carrying_the_previous_draft(conn, monkeypatch):
    """After a bounce the second enrich call sees its own previous draft and
    returns only what it changes; the untouched fields ride through."""
    bad = dict(DRAFT, key_concepts=["Jawed Karim: uploaded the first video"])
    patch = {"key_concepts": ["three-file loop: work script, grader, rules markdown"]}
    calls = _stub_sdk(monkeypatch, [bad, patch], [dict(PASS_VERDICT)])
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "kept"
    enrich_calls = [c for c in calls if c["model"] == "claude-sonnet-5"]
    assert len(enrich_calls) == 2
    assert "Previous draft:" in enrich_calls[1]["user"]
    assert "Jawed Karim" in enrich_calls[1]["user"]
    rows = conn.execute(
        "SELECT reason, inputs FROM activity WHERE item_id = ? AND action = 'enrich' ORDER BY id",
        (item_id,),
    ).fetchall()
    assert "(patch)" in rows[1]["reason"]
    assert json.loads(rows[1]["inputs"])["mode"] == "patch"
    text = res.note_path.read_text()
    assert "three-file loop" in text and DRAFT["thesis"] in text


def test_landing_over_an_existing_note_snapshots_it_first(conn, monkeypatch, brain):
    _stub_sdk(monkeypatch, [dict(DRAFT), dict(DRAFT)], [dict(PASS_VERDICT), dict(PASS_VERDICT)])
    item_id = _seed(conn)
    first = curator.advance_item(conn, item_id)
    assert first.outcome == "kept"
    assert conn.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0
    ledger.insert_activity(conn, item_id, actor="operator", action="read", to_state="read")
    second = curator.advance_item(conn, item_id)
    assert second.outcome == "kept" and second.note_path == first.note_path
    snap = conn.execute("SELECT before_ref FROM snapshots WHERE item_id = ?", (item_id,)).fetchone()
    assert snap is not None and DRAFT["thesis"] in open(snap["before_ref"]).read()


def test_item_call_cap_stops_the_loop_with_a_budget_ask(conn, monkeypatch):
    """Seven calls already spent: one more round (two calls) crosses the cap,
    the loop asks instead of starting another round, and accept-as-is lands
    the last draft for free."""
    item_id = _seed(conn)
    for _ in range(curator.ITEM_CALL_CAP - 1):
        ledger.insert_activity(conn, item_id, actor="enricher", action="enrich", tokens=100)
    calls = _stub_sdk(
        monkeypatch, [dict(DRAFT), dict(DRAFT)], [dict(BOUNCE_VERDICT), dict(PASS_VERDICT)]
    )
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "asked"
    ask = conn.execute("SELECT kind, proposal FROM asks WHERE id = ?", (res.ask_id,)).fetchone()
    assert ask["kind"] == "budget spent"
    assert "accept as is" in ask["proposal"]
    assert len(calls) == 2  # one enrich, one grade, then the cap
    _answer(conn, res.ask_id, choice="accept as is")

    def explode(*a, **k):
        raise AssertionError("accept as is must not spend a model call")

    monkeypatch.setattr(sdk, "call_structured", explode)
    res2 = curator.advance_item(conn, item_id)
    assert res2.outcome == "kept" and res2.note_path.exists()


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


def test_say_what_is_wrong_also_carries_the_last_verdict(conn, monkeypatch):
    """A one-line owner answer must not drop the grader's findings: the retry
    prompt carries both."""
    calls = _stub_sdk(
        monkeypatch,
        [dict(DRAFT), dict(DRAFT), {"summary": "fixed"}],
        [dict(BOUNCE_VERDICT), dict(BOUNCE_VERDICT), dict(PASS_VERDICT)],
    )
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "asked"
    _answer(conn, res.ask_id, choice="say what is wrong", text="tighten it")
    curator.advance_item(conn, item_id)
    retry = [c for c in calls if c["model"] == "claude-sonnet-5"][-1]["user"]
    assert "the owner says: tighten it" in retry
    assert "Thesis: could attach to any video" in retry


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


def test_landing_triggers_connect_propose(conn, monkeypatch):
    """#197 P6: connect runs only on fresh landings — structurally excluding
    the grandfathered kept pile (no selector over kept exists)."""
    _stub_sdk(monkeypatch, [dict(DRAFT)], [dict(PASS_VERDICT)])
    calls = []
    monkeypatch.setattr(
        "ytk.connect.propose",
        lambda conn2, item_id, thesis, summary, **kw: calls.append(
            {"item_id": item_id, "thesis": thesis, **kw}
        ),
    )
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "kept"
    assert len(calls) == 1
    call = calls[0]
    assert call["item_id"] == item_id
    assert call["thesis"] == DRAFT["thesis"]
    # Self-exclusion travels on every handle the store can return the note by.
    assert call["exclude_media_id"] == "abc123xyz00"
    assert call["exclude_url"] == "https://www.youtube.com/watch?v=abc123xyz00"
    assert call["note_path"].exists()
    assert call["key_concepts"] == DRAFT["key_concepts"]
    assert call["take"] == "why loops beat cron"


def test_accept_as_is_also_triggers_connect(conn, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "ytk.connect.propose",
        lambda conn2, item_id, thesis, summary, **kw: calls.append(item_id),
    )
    _stub_sdk(monkeypatch, [dict(BAD_DRAFT), dict(BAD_DRAFT)], [])
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "asked"
    asks.answer_ask(conn, res.ask_id, choice="accept as is")
    ledger.insert_activity(
        conn, item_id, actor="owner", action="answer", from_state="asking", to_state="answered"
    )
    res2 = curator.advance_item(conn, item_id)
    assert res2.outcome == "kept"
    assert calls == [item_id]


def test_connect_failure_never_unlands_the_note(conn, monkeypatch):
    _stub_sdk(monkeypatch, [dict(DRAFT)], [dict(PASS_VERDICT)])

    def boom(*a, **k):
        raise RuntimeError("argue call failed")

    monkeypatch.setattr("ytk.connect.propose", boom)
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "kept"
    assert ledger.item_state(conn, item_id) == "kept"
    err = conn.execute(
        "SELECT reason FROM activity WHERE item_id = ? AND action = 'connect-error'", (item_id,)
    ).fetchone()
    assert "argue call failed" in err["reason"]


def test_advance_narrates_stages_into_health(conn, monkeypatch):
    from ytk import loop as loop_mod

    stages = []
    monkeypatch.setattr(loop_mod, "stamp_stage", lambda key, detail=None: stages.append(key))
    monkeypatch.setattr("ytk.connect.propose", lambda *a, **k: None)
    _stub_sdk(monkeypatch, [dict(DRAFT)], [dict(PASS_VERDICT)])
    item_id = _seed(conn)
    curator.advance_item(conn, item_id)
    assert stages == ["enrich", "checks", "grade", "land"]


def test_student_and_teacher_read_the_same_packet(conn, monkeypatch):
    """#212's invariant: identical rendered bytes in both prompts, the same
    attempt header, and every enrich and grade row naming the view."""
    from ytk import attempt as A
    from ytk import view as V

    calls = _stub_sdk(monkeypatch, [dict(BAD_DRAFT), dict(DRAFT)], [dict(PASS_VERDICT)])
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "kept"
    view = V.latest_view(item_id)
    assert view is not None
    sonnet = [c["user"] for c in calls if c["model"] == "claude-sonnet-5"]
    opus = [c["user"] for c in calls if c["model"] == "claude-opus-5"]
    assert len(sonnet) == 2 and len(opus) == 1
    for user in (*sonnet, *opus):
        assert view.rendered in user
    assert "Attempt 1 for item" in sonnet[0] and "Attempt 2 for item" in sonnet[1]
    assert "Attempt 2 for item" in opus[0] and "banned phrasing" in opus[0]
    rows = conn.execute(
        "SELECT action, inputs FROM activity WHERE item_id = ? AND action IN ('enrich', 'grade')",
        (item_id,),
    ).fetchall()
    assert len(rows) == 4
    assert {json.loads(r["inputs"])["view_hash"] for r in rows} == {view.view_hash}
    attempts = A.attempts_for(item_id)
    assert [a.n for a in attempts] == [1, 2]
    assert attempts[0].verdict_out["layer"] == "deterministic"
    assert attempts[1].verdict_out["passed"] is True
    assert attempts[1].findings_in[0]["check"] == "banned phrasing"
    assert attempts[1].previous_draft["thesis"] == BAD_DRAFT["thesis"]


def test_a_grade_over_a_different_packet_is_refused(conn, monkeypatch):
    from ytk import view as V

    _stub_sdk(monkeypatch, [dict(DRAFT)], [dict(PASS_VERDICT)])
    item_id = _seed(conn)
    payload = conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item_id,)).fetchone()[
        "payload_ref"
    ]
    real = V.ensure_view(item_id, payload)
    other = V.build_view(item_id, payload, V.Budget(frames_shown=1))
    conn.execute(
        "INSERT INTO activity (item_id, at, actor, action, inputs) VALUES (?, ?, 'enricher', 'enrich', ?)",
        (item_id, ledger.now(), json.dumps({"view_hash": other.view_hash})),
    )
    with pytest.raises(RuntimeError, match="different|would read"):
        curator._grade_inputs(
            conn, item_id, view=real, attempt_n=1, rubric_hash=None, prompt_version=None
        )


def test_bare_say_what_is_wrong_sends_the_last_verdict_back(conn, monkeypatch):
    """No owner line: the retry is still a patch over the last draft with the
    grader's findings in, never a blind first attempt."""
    calls = _stub_sdk(
        monkeypatch,
        [dict(DRAFT), dict(DRAFT), {"summary": "fixed"}],
        [dict(BOUNCE_VERDICT), dict(BOUNCE_VERDICT), dict(PASS_VERDICT)],
    )
    item_id = _seed(conn)
    res = curator.advance_item(conn, item_id)
    assert res.outcome == "asked"
    _answer(conn, res.ask_id, choice="say what is wrong", text=None)
    out = curator.advance_item(conn, item_id)
    assert out.outcome == "kept"
    retry = [c for c in calls if c["model"] == "claude-sonnet-5"][-1]
    assert "Previous draft:" in retry["user"]
    assert "Thesis: could attach to any video" in retry["user"]
    assert "the owner says" not in retry["user"]
