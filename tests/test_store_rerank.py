"""Two-stage retrieval wiring (#86): search paths behind the rerank flag.

Fake scorers only — the real cross-encoder is exercised by
experiments/rerank_bench.py and the live eval gate, never the fast suite.
"""

import pytest

from ytk.enrich import Enrichment


@pytest.fixture
def store(tmp_path, monkeypatch):
    # patch the chroma path instead of reloading (see test_store_epochs)
    import ytk.store as store_mod

    monkeypatch.setattr(store_mod, "_CHROMA_PATH", tmp_path / "chroma")
    monkeypatch.setattr(store_mod, "_client", None)
    monkeypatch.delenv("YTK_RERANK", raising=False)
    return store_mod


def _seed_memories(store):
    for i, text in enumerate(
        ["apples and orchard care through the seasons of the year",
         "vector database internals and how hnsw indexes work",
         "sourdough starter care and feeding schedules explained"]
    ):
        store.upsert_memory(f"m{i}", text, [], f"/vault/m{i}.md")


def test_search_all_rerank_reorders_and_cuts_to_n(store, monkeypatch):
    _seed_memories(store)

    def scorer(query, texts):
        return [1.0 if "sourdough" in t else 0.0 for t in texts]

    monkeypatch.setattr(store, "_reranker", scorer)
    out = store.search_all("apples and orchard care", n=2, rerank=True)
    assert len(out) == 2
    assert out[0].doc_id == "m2"


def test_search_all_rerank_off_by_default(store, monkeypatch):
    _seed_memories(store)

    def scorer(query, texts):
        raise AssertionError("reranker must not run unless enabled")

    monkeypatch.setattr(store, "_reranker", scorer)
    out = store.search_all("vector database internals", n=2)
    assert out[0].doc_id == "m1"


def test_search_all_env_flag_enables_rerank(store, monkeypatch):
    _seed_memories(store)
    called = {}

    def scorer(query, texts):
        called["n"] = len(texts)
        return [0.0] * len(texts)

    monkeypatch.setattr(store, "_reranker", scorer)
    monkeypatch.setenv("YTK_RERANK", "1")
    store.search_all("anything", n=2)
    assert called["n"] == 3


def test_search_all_rerank_scores_memories_on_full_text(store, monkeypatch):
    # the 200-char excerpt is a display artifact; the reranker must read
    # the stored document, not the excerpt
    store.upsert_memory("long", "banana " * 100, [], "/vault/long.md")
    seen: list[str] = []

    def scorer(query, texts):
        seen.extend(texts)
        return [0.5] * len(texts)

    monkeypatch.setattr(store, "_reranker", scorer)
    store.search_all("banana", n=1, rerank=True)
    assert any(len(t) > 300 for t in seen)


def _video(store, video_id: str, thesis: str):
    enr = Enrichment(
        thesis=thesis,
        summary=f"Summary for {video_id}.",
        key_concepts=[], insights=[], interest_tags=[], key_moments=[],
    )
    store.upsert(
        {"id": video_id, "title": video_id, "url": "u", "uploader": "x",
         "upload_date": "20260101"},
        enr,
        segments=[{"start": 0.0, "text": f"segment text for {video_id}"}],
    )


def test_search_videos_rerank_reorders_on_thesis_summary(store, monkeypatch):
    _video(store, "vid1", "A talk about baking bread at home.")
    _video(store, "vid2", "A talk about growing apples in orchards.")

    def scorer(query, texts):
        assert all("Summary for" in t for t in texts)
        return [1.0 if "apples" in t else 0.0 for t in texts]

    monkeypatch.setattr(store, "_reranker", scorer)
    out = store.search_videos("baking bread", n=2, rerank=True)
    assert out[0].video_id == "vid2"


def test_search_segments_rerank_reorders_on_segment_text(store, monkeypatch):
    _video(store, "vid1", "Thesis one.")
    _video(store, "vid2", "Thesis two.")

    def scorer(query, texts):
        return [1.0 if "vid2" in t else 0.0 for t in texts]

    monkeypatch.setattr(store, "_reranker", scorer)
    out = store.search_segments("segment text", n=2, rerank=True)
    assert out[0].video_id == "vid2"
