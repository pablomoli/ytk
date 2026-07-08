"""The user's thought steers enrichment when provided (top-down attention)."""

from __future__ import annotations

import pytest

FAKE_RESULT = {
    "thesis": "t",
    "summary": "s",
    "key_concepts": [],
    "insights": [],
    "interest_tags": [],
    "key_moments": [],
}


@pytest.fixture
def captured(monkeypatch):
    calls = {}

    def fake(system_prompt, user_prompt, schema, add_dirs=None, max_turns=20):
        calls["system"] = system_prompt
        calls["prompt"] = user_prompt
        return dict(FAKE_RESULT)

    monkeypatch.setattr("ytk.enrich.run_structured", fake)
    return calls


def test_instagram_enrichment_includes_user_note(captured):
    from ytk.enrich import enrich_instagram

    enrich_instagram(
        caption="c", username="u", slide_count=0, visual_blocks=[],
        user_note="this could work for the epicmap parcel viewer",
    )
    assert "this could work for the epicmap parcel viewer" in captured["prompt"]
    assert "saved this with their own note" in captured["prompt"]


def test_instagram_enrichment_omits_note_block_when_empty(captured):
    from ytk.enrich import enrich_instagram

    enrich_instagram(caption="c", username="u", slide_count=0, visual_blocks=[])
    assert "saved this with their own note" not in captured["prompt"]


def test_youtube_enrichment_includes_user_note(captured):
    from ytk.enrich import enrich

    enrich("transcript text", {"title": "T"}, user_note="focus on the lighting rig")
    assert "focus on the lighting rig" in captured["prompt"]


def test_tiktok_enrichment_includes_user_note(captured):
    from ytk.enrich import enrich_tiktok

    enrich_tiktok({"username": "u"}, "", user_note="ref for the yt thumbnail")
    assert "ref for the yt thumbnail" in captured["prompt"]


def test_web_enrichment_includes_user_note(captured):
    from ytk.ingest import WebContent, enrich_web

    content = WebContent(url="https://x/", title="T", author="", date="", text="body")
    enrich_web(content, user_note="compare against my vtk notes")
    assert "compare against my vtk notes" in captured["prompt"]
