"""Vault-aware enrichment (issue #15): every enrichment prompt carries the
existing tag vocabulary so tags converge instead of drifting. The vocabulary
is a prompt nudge, never a schema constraint, and never breaks an ingest."""

from __future__ import annotations

import pytest

from ytk import enrich, store


@pytest.fixture(autouse=True)
def _fresh_vocab_cache(monkeypatch):
    monkeypatch.setattr(enrich, "_VOCAB_CACHE", None)


class _FakeCol:
    def __init__(self, tag_strings):
        self._metas = [{"tags": t} for t in tag_strings]

    def count(self):
        return len(self._metas)

    def get(self, include):
        # real chroma always returns ids alongside any include
        return {"ids": [f"vid{i}" for i in range(len(self._metas))], "metadatas": self._metas}


def test_tag_counts_frequency_ranked_videos_only(monkeypatch):
    monkeypatch.setattr(
        store, "_videos_collection", lambda: _FakeCol(["ai, go", "ai, geospatial", "ai, go"])
    )
    monkeypatch.setattr(
        store,
        "_memories_collection",
        lambda: (_ for _ in ()).throw(
            AssertionError("memories tags are folder paths, not interest tags")
        ),
    )

    assert store.top_tags(2) == ["ai", "go"]
    counts = store.tag_counts()
    assert counts["ai"] == 3 and counts["geospatial"] == 1


def test_vocabulary_curated_first_deduped(monkeypatch):
    class _Cfg:
        class hub:
            tags = ["ai", "creative-coding"]

    monkeypatch.setattr(enrich, "_VOCAB_CACHE", None)
    monkeypatch.setattr("ytk.config.load_config", lambda: _Cfg)
    monkeypatch.setattr(
        "ytk.reels.load_state", lambda p: type("S", (), {"custom_tags": ["oracle"]})()
    )
    monkeypatch.setattr("ytk.store.top_tags", lambda n: ["go", "ai", "wasm"])

    assert enrich.tag_vocabulary() == ["ai", "creative-coding", "oracle", "go", "wasm"]


def test_vocab_block_lists_tags(monkeypatch):
    monkeypatch.setattr(enrich, "tag_vocabulary", lambda: ["ai", "go"])
    block = enrich._vocab_block()
    assert "ai, go" in block
    assert "Reuse an existing tag" in block


def test_vocab_block_never_raises(monkeypatch):
    monkeypatch.setattr(
        enrich, "tag_vocabulary", lambda: (_ for _ in ()).throw(RuntimeError("chroma cold"))
    )
    assert enrich._vocab_block() == ""


def test_vocab_reaches_web_enrichment_prompt(monkeypatch):
    from ytk.ingest import WebContent, enrich_web

    monkeypatch.setattr(enrich, "tag_vocabulary", lambda: ["taste-modeling"])
    seen = {}

    def fake(system, user, schema, add_dirs=None, model=None):
        seen["user"] = user
        return {
            "thesis": "t",
            "summary": "s",
            "key_concepts": [],
            "insights": [],
            "interest_tags": ["taste-modeling"],
            "key_moments": [],
        }

    monkeypatch.setattr("ytk.sdk.run_structured", fake)
    monkeypatch.setattr("ytk.sdk.run_structured", fake)

    enrich_web(WebContent(url="u", title="t", author="a", date="d", text="body"))
    assert "taste-modeling" in seen["user"]
    assert "Reuse an existing tag" in seen["user"]
