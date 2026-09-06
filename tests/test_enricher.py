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


def _packet(conn, item_id, n=1, *, findings=None, previous=None, take=True):
    """The proctor's job in miniature: one view per bundle, one attempt."""
    from ytk import attempt as A
    from ytk import view as V

    payload = conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item_id,)).fetchone()
    v = V.ensure_view(item_id, payload["payload_ref"])
    row = conn.execute(
        "SELECT * FROM takes WHERE item_id = ? ORDER BY id DESC LIMIT 1", (item_id,)
    ).fetchone()
    take_rec = {"id": row["id"], "kind": row["kind"], "text": row["text"]} if row and take else None
    a = A.open_attempt(item_id, n, v, take=take_rec, previous=previous, findings_in=findings or [])
    return v, a


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
    v, a = _packet(conn, item_id)
    res = enricher.enrich_item(conn, item_id, view=v, attempt=a)
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
    assert inputs["view_hash"] == v.view_hash and inputs["attempt"] == 1
    assert row["output_ref"] == str(res.draft_path)


def test_prompt_carries_take_and_never_the_rubric(conn, stub_call):
    item_id = _seed(conn, take="why loops beat cron")
    v, a = _packet(conn, item_id)
    enricher.enrich_item(conn, item_id, view=v, attempt=a)
    user = stub_call[0]["user"]
    assert v.rendered in user
    assert "why loops beat cron" in user
    # The conftest stub rubric says "Be specific. No filler." — the wall
    # holds only if none of it reaches the enricher's prompts.
    for text in (stub_call[0]["system"], user):
        assert "No filler" not in text
    assert stub_call[0]["model"] == enricher.ENRICHER_MODEL


def test_bounce_feedback_reaches_the_retry_prompt(conn, stub_call):
    item_id = _seed(conn)
    v, a = _packet(
        conn,
        item_id,
        2,
        findings=[{"check": "thesis", "detail": "could attach to any video on the topic"}],
    )
    enricher.enrich_item(conn, item_id, view=v, attempt=a)
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
    v, a = _packet(conn, item_id, take=False)
    res = enricher.enrich_item(conn, item_id, view=v, attempt=a)
    assert res.draft.take_response is None
    row = conn.execute(
        "SELECT * FROM activity WHERE item_id = ? AND action = 'enrich'", (item_id,)
    ).fetchone()
    assert row["tokens"] is None  # subscription auth may not report usage
    assert json.loads(row["inputs"])["take_id"] is None


def test_enricher_lists_the_packets_shown_frames_and_mounts_only_them(conn, monkeypatch, tmp_path):
    """e501375: four reel frames fail structured output 3/3, two pass. The
    cap is the view's budget now; the enricher lists what the view shows and
    mounts what the view mounts, nothing of its own."""
    import json as _json

    from ytk import sdk
    from ytk.enricher import enrich_item

    frames = []
    for i in range(4):
        f = tmp_path / f"frame-{i}.jpg"
        f.write_bytes(b"jpeg")
        frames.append(str(f))
    item = _seed(conn)
    payload = Path(
        conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item,)).fetchone()[
            "payload_ref"
        ]
    )
    bundle = _json.loads(payload.read_text())
    bundle["frames"] = frames
    payload.write_text(_json.dumps(bundle))

    seen = {}

    def fake(system, user, schema, *, add_dirs=None, max_turns=20, model=None):
        seen["user"] = user
        seen["add_dirs"] = add_dirs
        return sdk.StructuredResult(
            data=dict(DRAFT), model=model, tokens=10, duration_ms=5, usage=None
        )

    monkeypatch.setattr(sdk, "call_structured", fake)
    v, a = _packet(conn, item)
    enrich_item(conn, item, view=v, attempt=a)
    listed = [ln for ln in seen["user"].splitlines() if "frame-" in ln]
    assert len(listed) == 2
    assert "frame:001" in listed[0] and "frame-0" in listed[0] and "frame-1" in listed[1]
    assert seen["add_dirs"] == v.mounts == [str(tmp_path)]
    assert "frames 3 to 4" in seen["user"]


def test_v2_schema_asks_for_a_title():
    from ytk.enricher import _V2_ADDENDUM, SCHEMA_V2

    assert "title" in SCHEMA_V2["properties"]
    assert "title" in _V2_ADDENDUM


class TestPatchRetry:
    """A retry is a patch: previous draft + findings in, changed fields out,
    unchanged fields copied in code; the packet is the same on every round."""

    def _prev(self):
        from ytk.enricher import EnrichmentV2

        return EnrichmentV2.model_validate(
            {
                "thesis": "old thesis",
                "summary": "old summary",
                "key_concepts": ["keep me: as is"],
                "insights": ["insight stays"],
                "interest_tags": ["ai-agents"],
                "key_moments": [{"timestamp": "5:48", "description": "icon quiz reveal"}],
            }
        )

    def test_merge_keeps_unnamed_fields(self):
        from ytk.enricher import EnrichmentPatch, merge_patch

        out = merge_patch(self._prev(), EnrichmentPatch(summary="new summary"))
        assert out.summary == "new summary"
        assert out.thesis == "old thesis"
        assert out.key_concepts == ["keep me: as is"]
        assert out.key_moments[0].timestamp == "5:48"

    def test_json_blob_in_a_prose_field_is_unwrapped(self):
        """Item 761: the patch returned {"summary": ..., "insights": [...]} as
        the summary string. The inner summary lands; nothing else leaks."""
        import json

        from ytk.enricher import EnrichmentPatch, merge_patch

        blob = json.dumps({"summary": "the real prose", "insights": ["smuggled"]})
        out = merge_patch(self._prev(), EnrichmentPatch(summary=blob))
        assert out.summary == "the real prose"
        assert out.insights == ["insight stays"]

    def test_json_blob_without_its_key_keeps_the_previous_prose(self):
        from ytk.enricher import EnrichmentPatch, merge_patch

        out = merge_patch(self._prev(), EnrichmentPatch(thesis='{"insights": ["x"]}'))
        assert out.thesis == "old thesis"

    def test_patch_reads_the_whole_packet_and_the_attempt_header(self, conn, monkeypatch):
        """The retry windows (b144705) are gone: the packet is the record on
        every round, and the previous draft and findings ride in the attempt
        header, not in a private rendering."""
        from ytk import sdk
        from ytk.enricher import SCHEMA_PATCH, enrich_item

        item = _seed(conn)
        seen = {}

        def fake(system, user, schema, *, add_dirs=None, max_turns=20, model=None):
            seen["user"] = user
            seen["schema"] = schema
            seen["system"] = system
            return sdk.StructuredResult(
                data={"summary": "new summary"}, model=model, tokens=10, duration_ms=5, usage=None
            )

        monkeypatch.setattr(sdk, "call_structured", fake)
        prev = self._prev().model_dump()
        v, a = _packet(
            conn,
            item,
            2,
            previous=prev,
            findings=[{"check": "Key moments", "detail": "5:48 is wrong", "where": "5:48"}],
        )
        res = enrich_item(conn, item, view=v, attempt=a)
        assert seen["schema"] == SCHEMA_PATCH and "RETRY" in seen["system"]
        assert v.rendered in seen["user"]
        assert "Previous draft:" in seen["user"] and "old thesis" in seen["user"]
        assert "Key moments: 5:48 is wrong (where: 5:48)" in seen["user"]
        assert "the grader cannot edit the work script" in seen["user"]
        assert res.draft.summary == "new summary" and res.draft.thesis == "old thesis"
        row = conn.execute(
            "SELECT reason, inputs FROM activity WHERE item_id = ? AND action = 'enrich'", (item,)
        ).fetchone()
        assert "attempt 2 (patch)" in row["reason"]
        assert json.loads(row["inputs"])["mode"] == "patch"
