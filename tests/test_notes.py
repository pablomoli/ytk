"""The curator note writer (#197 P4): spine My take / Response / Thesis,
located by frontmatter url so rewrites are idempotent, indexed as
ingestion used to."""

import pytest

from ytk import notes, store
from ytk.enricher import EnrichmentV2
from ytk.evidence import EvidenceBundle


@pytest.fixture(autouse=True)
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    return tmp_path


def _bundle(**overrides) -> EvidenceBundle:
    base = {
        "source": "youtube",
        "url": "https://www.youtube.com/watch?v=abc123xyz00",
        "title": "Loop Engineering",
        "transcript": [{"start": 0, "duration": 3, "text": "we built a three-file loop"}],
        "transcript_origin": "api-manual",
        "transcript_language": "en",
        "transcript_status": "ok",
        "description": "About loops.",
        "duration": 613,
        "media_id": "abc123xyz00",
        "uploader": "Someone",
        "upload_date": "20260830",
    }
    base.update(overrides)
    return EvidenceBundle(**base)


def _draft(**overrides) -> EnrichmentV2:
    base = {
        "thesis": "He builds a three-file agent loop.",
        "summary": "Work script, grader, rules markdown.",
        "key_concepts": ["three-file loop: work, grader, rules"],
        "insights": ["Grader outside the worker."],
        "interest_tags": ["ai-agents"],
        "key_moments": [{"timestamp": "0:00", "description": "the loop"}],
        "recommendations": [],
        "evidence_gaps": ["frames not extracted"],
        "take_response": "Agreed; cron cannot carry blame.",
        "new_tags": [],
    }
    base.update(overrides)
    return EnrichmentV2.model_validate(base)


def test_spine_order_and_frontmatter(brain):
    path = notes.write_curator_note(_bundle(), "intent", "why loops beat cron", _draft())
    text = path.read_text()
    assert path.parent == brain / "sources" / "youtube"
    assert "url: https://www.youtube.com/watch?v=abc123xyz00" in text
    i_take = text.index("## My take")
    i_resp = text.index("## Response")
    i_thesis = text.index("## Thesis")
    assert i_take < i_resp < i_thesis
    assert "why loops beat cron" in text
    assert "Agreed; cron cannot carry blame." in text
    assert "## Transcript" in text  # youtube keeps the raw body
    assert "## Evidence Gaps" in text
    assert "  - ai-agents" in text


def test_rewrite_is_idempotent_by_url(brain):
    p1 = notes.write_curator_note(_bundle(), "intent", "t", _draft())
    p2 = notes.write_curator_note(
        _bundle(title="Renamed Later"), "intent", "t", _draft(thesis="New thesis.")
    )
    assert p1 == p2
    assert "New thesis." in p2.read_text()
    assert len(list((brain / "sources" / "youtube").glob("*.md"))) == 1


def test_reflex_take_omits_sections_not_fakes_them(brain):
    d = _draft(take_response=None)
    path = notes.write_curator_note(_bundle(), "reflex", "$$", d)
    text = path.read_text()
    assert "## My take" not in text
    assert "## Response" not in text
    assert "## Thesis" in text


def test_web_note_carries_no_transcript_section(brain):
    b = _bundle(
        source="web",
        url="https://example.com/post",
        transcript=[],
        transcript_status="none",
        text="Body text.",
        media_id=None,
        duration=None,
    )
    path = notes.write_curator_note(b, "intent", "t", _draft())
    assert path.parent == brain / "sources" / "web"
    assert "## Transcript" not in path.read_text()


def test_index_note_youtube_uses_store_upsert(brain, monkeypatch):
    calls = {}
    monkeypatch.setattr(
        store, "upsert", lambda meta, enr, segs: calls.update(meta=meta, enr=enr, segs=segs)
    )
    b = _bundle()
    path = notes.write_curator_note(b, "intent", "t", _draft())
    notes.index_note(path, b, _draft())
    assert calls["meta"]["id"] == "abc123xyz00"
    assert calls["meta"]["uploader"] == "Someone"
    assert calls["segs"] == b.transcript


def test_index_note_web_uses_upsert_doc(brain, monkeypatch):
    calls = {}
    monkeypatch.setattr(
        store, "upsert_doc", lambda doc_id, body, meta: calls.update(doc_id=doc_id, meta=meta)
    )
    b = _bundle(source="web", url="https://example.com/post", transcript=[], media_id=None)
    path = notes.write_curator_note(b, "intent", "t", _draft())
    notes.index_note(path, b, _draft())
    assert calls["doc_id"]
    assert calls["meta"]["source_path"] == str(path)
