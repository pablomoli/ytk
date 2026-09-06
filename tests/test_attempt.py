"""The attempt record (#212): one round's memory, written by the proctor,
read by both roles as the same header."""

import json
from dataclasses import asdict

from ytk import attempt as A
from ytk import view as V
from ytk.evidence import EvidenceBundle, evidence_dir


def _view() -> V.View:
    b = EvidenceBundle(
        source="youtube",
        url="https://y/1",
        title="T",
        transcript=[{"start": 0, "duration": 3, "text": "we built a loop"}],
        transcript_origin="api-manual",
        transcript_language="en",
        transcript_status="ok",
        duration=10,
    )
    out = evidence_dir() / "7.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(b)))
    return V.ensure_view(7, out)


def test_open_writes_the_record_and_renders_the_header():
    v = _view()
    take = {"id": 3, "kind": "intent", "text": "why loops beat cron"}
    a = A.open_attempt(7, 1, v, take=take, previous=None, findings_in=[])
    assert a.path == evidence_dir() / "attempts" / "7-1.json" and a.path.exists()
    h = a.rendered()
    assert "Attempt 1" in h and v.view_hash in h
    assert "why loops beat cron" in h and "No previous draft" in h
    assert a.opened_at and a.closed_at is None


def test_findings_in_and_previous_draft_ride_in_the_header():
    v = _view()
    prev = {"thesis": "old thesis", "summary": "s", "key_concepts": [], "insights": []}
    finding = {"check": "Thesis", "detail": "could attach to any video", "where": "thesis"}
    a = A.open_attempt(7, 2, v, take=None, previous=prev, findings_in=[finding])
    h = a.rendered()
    assert "Findings requested last round" in h
    assert "Thesis: could attach to any video (where: thesis)" in h
    assert "old thesis" in h
    assert "not a new objection" in h


def test_record_draft_and_close_persist():
    v = _view()
    a = A.open_attempt(7, 2, v, take=None, previous=None, findings_in=[])
    a.record_draft("/p/7-2.json")
    a.close({"layer": "model", "passed": False, "bounces": []})
    r = A.load_attempt(7, 2)
    assert r is not None
    assert r.draft_out == "/p/7-2.json" and r.verdict_out["layer"] == "model" and r.closed_at
    assert r.view_hash == v.view_hash
    assert A.load_attempt(7, 9) is None
    assert [x.n for x in A.attempts_for(7)] == [2]
