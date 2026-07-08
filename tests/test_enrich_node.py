import ytk.enrich as e
from ytk.enrich import Enrichment

_STUB = {"thesis": "t", "summary": "s", "key_concepts": ["k: used"],
         "insights": ["i"], "interest_tags": ["go"], "key_moments": []}


def test_enrich_content_composes_system_and_returns_enrichment(monkeypatch):
    captured = {}

    def fake_run(system, user, schema, add_dirs=None, **kw):
        captured["system"] = system
        captured["user"] = user
        return _STUB

    monkeypatch.setattr(e, "run_structured", fake_run)
    out = e.enrich_content("Article body here", source="web", user_note="my angle")
    assert isinstance(out, Enrichment)
    assert e.SOURCE_BIAS["web"] in captured["system"]
    assert "Article body here" in captured["user"]
    assert "my angle" in captured["user"]  # _note_block appended


def test_enrich_wrapper_delegates_with_youtube_source(monkeypatch):
    captured = {}
    monkeypatch.setattr(e, "run_structured",
                         lambda s, u, sc, add_dirs=None, **kw: captured.update(system=s) or _STUB)
    e.enrich("the transcript", {"title": "T", "duration": 60})
    assert e.SOURCE_BIAS["youtube"] in captured["system"]
