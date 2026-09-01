"""The enricher verb (#197 P4): evidence + take -> draft note, never the
rubric. Drafts keyed by item+attempt; every call writes one activity row
carrying model/tokens/duration."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from ytk import enricher, evidence, ledger, sdk
from ytk.capture import capture
from ytk.evidence import EvidenceBundle


@pytest.fixture
def conn():
    c = ledger.connect()
    yield c
    c.close()


def _bundle(**overrides) -> EvidenceBundle:
    base = {
        "source": "youtube",
        "url": "https://y/1",
        "title": "T",
        "transcript": [
            {"start": 0, "duration": 2, "text": "we built a three-file loop"},
            {"start": 2, "duration": 2, "text": "the grader cannot edit the work script"},
        ],
        "transcript_origin": "api-manual",
        "transcript_language": "en",
        "transcript_status": "ok",
        "description": "D",
        "duration": 613,
        "media_id": "abc123xyz00",
        "uploader": "Someone",
        "upload_date": "20260830",
        "gaps": ["frames not extracted"],
    }
    base.update(overrides)
    return EvidenceBundle(**base)


def _seed(conn, *, take: str | None = "why loops beat cron") -> int:
    res = capture(
        conn,
        source="youtube",
        url="https://y/1",
        surface="cli",
        text=take,
        take_kind="intent",
        log=False,
    )
    out = evidence.evidence_dir() / f"{res.item_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(_bundle())))
    conn.execute("UPDATE items SET payload_ref = ? WHERE id = ?", (str(out), res.item_id))
    conn.commit()
    return res.item_id


DRAFT = {
    "thesis": "He builds a three-file agent loop with an uneditable grader.",
    "summary": "Work script, grader, rules markdown; the agent edits only the first.",
    "key_concepts": ["three-file loop: work script, grader, rules"],
    "insights": ["Keep the grader outside the worker."],
    "interest_tags": ["ai-agents"],
    "key_moments": [{"timestamp": "0:02", "description": "grader cannot edit the work script"}],
    "recommendations": [],
    "evidence_gaps": ["frames not extracted"],
    "take_response": "Agreed, and cron cannot carry blame the way a loop's ledger can.",
    "new_tags": [],
}


@pytest.fixture
def stub_call(monkeypatch):
    calls: list[dict] = []

    def fake(system, user, schema, *, add_dirs=None, max_turns=20, model=None):
        calls.append({"system": system, "user": user, "schema": schema, "model": model})
        return sdk.StructuredResult(
            data=DRAFT, model=model, tokens=1234, duration_ms=5000, usage={"input_tokens": 1000}
        )

    monkeypatch.setattr(sdk, "call_structured", fake)
    return calls


def test_enrich_item_writes_draft_and_activity(conn, stub_call):
    item_id = _seed(conn)
    res = enricher.enrich_item(conn, item_id, attempt=1)
    assert res.draft.take_response is not None
    assert res.draft_path.name == f"{item_id}-1.json"
    assert res.draft_path.exists()
    row = conn.execute(
        "SELECT * FROM activity WHERE item_id = ? AND action = 'enrich'", (item_id,)
    ).fetchone()
    assert row["actor"] == "enricher"
    assert row["model"] == enricher.ENRICHER_MODEL
    assert row["tokens"] == 1234
    assert row["duration_ms"] == 5000
    assert row["to_state"] is None  # enrich never transitions; the grader does
    inputs = json.loads(row["inputs"])
    assert len(inputs["evidence_hash"]) == 12
    assert inputs["take_id"] is not None
    assert inputs["prompt_version"] == enricher.PROMPT_VERSION
    assert row["output_ref"] == str(res.draft_path)


def test_prompt_carries_take_and_never_the_rubric(conn, stub_call):
    item_id = _seed(conn, take="why loops beat cron")
    enricher.enrich_item(conn, item_id, attempt=1)
    user = stub_call[0]["user"]
    assert "why loops beat cron" in user
    # The conftest stub rubric says "Be specific. No filler." — the wall
    # holds only if none of it reaches the enricher's prompts.
    for text in (stub_call[0]["system"], user):
        assert "No filler" not in text
    assert stub_call[0]["model"] == enricher.ENRICHER_MODEL


def test_bounce_feedback_reaches_the_retry_prompt(conn, stub_call):
    item_id = _seed(conn)
    enricher.enrich_item(
        conn, item_id, attempt=2, feedback=["thesis: could attach to any video on the topic"]
    )
    assert "could attach to any video" in stub_call[0]["user"]
    row = conn.execute(
        "SELECT reason FROM activity WHERE item_id = ? AND action = 'enrich'", (item_id,)
    ).fetchone()
    assert "attempt 2" in row["reason"]


def test_take_less_item_enriches_without_response_section(conn, stub_call, monkeypatch):
    draft = dict(DRAFT, take_response=None)
    monkeypatch.setattr(
        sdk,
        "call_structured",
        lambda *a, **k: sdk.StructuredResult(
            data=draft, model=None, tokens=None, duration_ms=None, usage=None
        ),
    )
    item_id = _seed(conn, take=None)
    res = enricher.enrich_item(conn, item_id, attempt=1)
    assert res.draft.take_response is None
    row = conn.execute(
        "SELECT * FROM activity WHERE item_id = ? AND action = 'enrich'", (item_id,)
    ).fetchone()
    assert row["tokens"] is None  # subscription auth may not report usage
    assert json.loads(row["inputs"])["take_id"] is None


def test_enricher_sees_at_most_two_frames(conn, monkeypatch, tmp_path):
    """Measured 2026-08-31 on item 756 (four ~60KB reel frames): 4 frames
    fail structured output 3/3, 2 and 1 succeed. The cap protects the model
    call; the bundle keeps every frame for the note embed."""
    import json as _json

    from ytk import sdk
    from ytk.enricher import enrich_item

    frames = []
    for i in range(4):
        f = tmp_path / f"frame-{i}.jpg"
        f.write_bytes(b"jpeg")
        frames.append(str(f))
    item = _seed(conn)
    bundle = _json.loads(
        Path(
            conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item,)).fetchone()[
                "payload_ref"
            ]
        ).read_text()
    )
    bundle["frames"] = frames
    Path(
        conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item,)).fetchone()[
            "payload_ref"
        ]
    ).write_text(_json.dumps(bundle))

    seen = {}

    def fake(system, user, schema, *, add_dirs=None, max_turns=20, model=None):
        seen["user"] = user
        seen["add_dirs"] = add_dirs
        return sdk.StructuredResult(
            data=dict(DRAFT), model=model, tokens=10, duration_ms=5, usage=None
        )

    monkeypatch.setattr(sdk, "call_structured", fake)
    enrich_item(conn, item, attempt=1)
    listed = [ln for ln in seen["user"].splitlines() if "frame-" in ln]
    assert len(listed) == 2
    assert "frame-0" in listed[0] and "frame-1" in listed[1]
