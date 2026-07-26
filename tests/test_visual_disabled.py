"""Visual-index circuit breaker behavior."""

from __future__ import annotations


def _unexpected_collection_access():
    raise AssertionError("disabled visual index accessed Chroma")


def test_visual_index_switch_is_dynamic_and_case_insensitive(monkeypatch):
    from ytk import store

    monkeypatch.delenv("YTK_VISUAL_INDEX", raising=False)
    assert store.visual_index_enabled()

    monkeypatch.setenv("YTK_VISUAL_INDEX", "OFF")
    assert not store.visual_index_enabled()

    monkeypatch.setenv("YTK_VISUAL_INDEX", "on")
    assert store.visual_index_enabled()


def test_disabled_visual_store_never_accesses_chroma(monkeypatch):
    from ytk import store

    monkeypatch.setenv("YTK_VISUAL_INDEX", "off")
    monkeypatch.setattr(store, "_visual_collection", _unexpected_collection_access)
    monkeypatch.setattr(store, "_visual_pending_collection", _unexpected_collection_access)

    assert not store.visual_index_ok(timeout_s=0.01)
    assert store.visual_count() == 0
    assert store.visual_ids() == set()
    assert not store.update_visual_metadata("yt:item", {"title": "changed"})
    assert store.pending_visual_ids() == set()
    assert store.pending_visual_similar([0.1, 0.2]) == []
    assert store.get_profile_visual_pool() == []
    assert store.get_profile_visual_pool(pending=True) == []
    assert store.get_visual_embedding("yt:item") is None
    assert store.get_visual_metadata("yt:item") is None
    assert store.visual_similar(embedding=[0.1, 0.2]) == []

    store.upsert_visual("yt:item", [0.1, 0.2], {"source": "youtube"})
    store.upsert_pending_visual("https://example.com/item", [0.1, 0.2], {})
    store.delete_pending_visual(["https://example.com/item"])
    store.delete_visual(["yt:item"])
