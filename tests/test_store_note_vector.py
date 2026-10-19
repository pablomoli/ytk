"""Doc-to-doc geometry for connect (layer 2): a note's own unit-mean vector
and its nearest notes across both collections, read from stored vectors."""

from __future__ import annotations

import importlib
import math

import pytest


def _fresh_store(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store

    importlib.reload(store)
    store.EMBEDDING_EPOCH = "v1"  # reload resets to the production default
    return store


def _unit(*xs):
    n = math.sqrt(sum(x * x for x in xs))
    return [x / n for x in xs] + [0.0] * (384 - len(xs))


def test_note_vector_is_the_unit_mean_of_its_parts(tmp_path, monkeypatch):
    store = _fresh_store(tmp_path, monkeypatch)
    store._memories_collection().upsert(
        ids=["note_a", "note_a#1", "note_b"],
        embeddings=[_unit(1, 0), _unit(0, 1), _unit(1, 1)],
        documents=["a", "a tail", "b"],
        metadatas=[
            {"doc_id": "note_a", "source_path": "/v/a.md"},
            {"doc_id": "note_a", "source_path": "/v/a.md"},
            {"doc_id": "note_b", "source_path": "/v/b.md"},
        ],
    )
    vec = store.note_vector(source_path="/v/a.md")
    assert vec is not None
    assert vec[:2] == pytest.approx([1 / math.sqrt(2), 1 / math.sqrt(2)])
    assert store.note_vector(source_path="/v/missing.md") is None


def test_note_vector_falls_back_to_the_video(tmp_path, monkeypatch):
    store = _fresh_store(tmp_path, monkeypatch)
    store._videos_collection().upsert(
        ids=["vid1"], embeddings=[_unit(0, 1)], documents=["t"], metadatas=[{"video_id": "vid1"}]
    )
    vec = store.note_vector(source_path="/v/none.md", video_id="vid1")
    assert vec is not None and vec[:2] == pytest.approx([0.0, 1.0])


def test_search_vector_merges_collections_one_hit_per_note(tmp_path, monkeypatch):
    store = _fresh_store(tmp_path, monkeypatch)
    store._videos_collection().upsert(
        ids=["vid1", "vid1#c", "vid2"],
        embeddings=[_unit(1, 0.1), _unit(1, 0.05), _unit(0, 1)],
        documents=["t1", "t1 concepts", "t2"],
        metadatas=[
            {"video_id": "vid1", "title": "V1", "thesis": "th1", "url": "https://y/1"},
            {"video_id": "vid1", "title": "V1", "thesis": "th1", "url": "https://y/1"},
            {"video_id": "vid2", "title": "V2", "thesis": "th2", "url": "https://y/2"},
        ],
    )
    store._memories_collection().upsert(
        ids=["note_a", "note_a#1"],
        embeddings=[_unit(1, 0.5), _unit(1, 0.4)],
        documents=["a", "a tail"],
        metadatas=[
            {"doc_id": "note_a", "source_path": "/v/a.md"},
            {"doc_id": "note_a", "source_path": "/v/a.md"},
        ],
    )
    hits = store.search_vector(_unit(1, 0), n=3)
    assert [(h.type, h.doc_id) for h in hits] == [
        ("video", "vid1"),
        ("memory", "note_a"),
        ("video", "vid2"),
    ]
    assert hits[0].source == "https://y/1" and hits[1].source == "/v/a.md"
    assert 1 - hits[0].distance == pytest.approx(1 / math.sqrt(1 + 0.05**2), abs=1e-4)
