"""Tests for the vector removers backing UI note deletion (store.delete_*)."""

from __future__ import annotations

import importlib


def _fresh_store(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store
    importlib.reload(store)
    return store


def test_delete_video_removes_parts_and_segments(tmp_path, monkeypatch):
    store = _fresh_store(tmp_path, monkeypatch)
    vid = "abcdef12345"

    store._videos_collection().upsert(
        ids=[f"{vid}#c", f"{vid}#i", "other#c"],
        documents=["chan", "insight", "keep"],
        metadatas=[{"video_id": vid}, {"video_id": vid}, {"video_id": "other"}],
    )
    store._segments_collection().upsert(
        ids=[f"{vid}_0", f"{vid}_1", "other_0"],
        documents=["a", "b", "keep"],
        metadatas=[{"video_id": vid}, {"video_id": vid}, {"video_id": "other"}],
    )

    store.delete_video(vid)

    assert set(store._videos_collection().get(include=[])["ids"]) == {"other#c"}
    assert set(store._segments_collection().get(include=[])["ids"]) == {"other_0"}


def test_delete_visual_removes_only_named_ids(tmp_path, monkeypatch):
    store = _fresh_store(tmp_path, monkeypatch)
    store._visual_collection().upsert(
        ids=["yt:abcdefg1234", "ig:shortcode", "ig:keepme"],
        embeddings=[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
        metadatas=[{"source": "youtube"}, {"source": "instagram"}, {"source": "instagram"}],
    )

    store.delete_visual(["yt:abcdefg1234", "ig:shortcode"])

    assert set(store._visual_collection().get(include=[])["ids"]) == {"ig:keepme"}


def test_delete_visual_empty_is_noop(tmp_path, monkeypatch):
    store = _fresh_store(tmp_path, monkeypatch)
    store._visual_collection().upsert(
        ids=["ig:keepme"], embeddings=[[0.5, 0.6]], metadatas=[{"source": "instagram"}]
    )
    store.delete_visual([])
    assert store._visual_collection().get(include=[])["ids"] == ["ig:keepme"]
