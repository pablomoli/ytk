"""#87 fixes: what reaches the embedding index and what stays out.

Three defects from the 2026-07-17 audit (issue comment):
  - tiny junk texts (test memos) were embedded as retrieval cards
  - project-memory MOC index.md files embed byte-identical boilerplate
  - YouTube annotations never reached any embedding (reindex_vault skips
    sources/youtube; store.upsert embeds enrichment text only)
"""

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    # patch the chroma path instead of reloading (see test_store_epochs)
    import ytk.store as store_mod

    monkeypatch.setattr(store_mod, "_CHROMA_PATH", tmp_path / "chroma")
    monkeypatch.setattr(store_mod, "_client", None)
    return store_mod


# --- minimum-length guard -------------------------------------------------


def test_upsert_doc_skips_tiny_text(store):
    store.upsert_doc("tiny", "good good", {"doc_id": "tiny", "source_path": "/v/t.md"})
    assert store._memories_collection().get(where={"doc_id": "tiny"})["ids"] == []


def test_upsert_doc_tiny_text_clears_stale_vectors(store):
    meta = {"doc_id": "shrunk", "source_path": "/v/s.md"}
    store.upsert_doc("shrunk", "a note long enough to be worth finding later on", meta)
    assert store._memories_collection().get(where={"doc_id": "shrunk"})["ids"]
    # note later edited down to junk: its old vector must not linger
    store.upsert_doc("shrunk", "ok", meta)
    assert store._memories_collection().get(where={"doc_id": "shrunk"})["ids"] == []


def test_upsert_doc_keeps_normal_text(store):
    store.upsert_doc(
        "norm",
        "a normal memory note about chroma internals and dedup",
        {"doc_id": "norm", "source_path": "/v/n.md"},
    )
    assert store._memories_collection().get(where={"doc_id": "norm"})["ids"] == ["norm"]


# --- MOC index.md exclusion ----------------------------------------------


def test_reindex_skips_memory_moc_index_files(store, tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    atoms = brain / "inbox" / "memories" / "someproject"
    atoms.mkdir(parents=True)
    (brain / "inbox" / "memories" / "index.md").write_text(
        "# Memory MOC\n\n- [[someproject/index]]\n", encoding="utf-8"
    )
    (atoms / "index.md").write_text(
        "# someproject\n\n- [[purpose]]\n- [[tech]]\n- [[state]]\n", encoding="utf-8"
    )
    (atoms / "purpose.md").write_text(
        "This project exists to test that real atoms still get indexed properly.", encoding="utf-8"
    )

    import ytk.vault as vault

    monkeypatch.setattr(vault, "_get_brain_path", lambda: brain)
    monkeypatch.setattr("ytk.cache.load_index_cache", lambda: {})
    monkeypatch.setattr("ytk.cache.save_index_cache", lambda cache: None)

    vault.reindex_vault(force=True)

    ids = store._memories_collection().get(include=[])["ids"]
    assert any("purpose" in i for i in ids)
    assert not any(i.endswith("_index") for i in ids)


def test_reindex_skips_archived_memories(store, tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    archive = brain / "inbox" / "memories" / "archived"
    archive.mkdir(parents=True)
    (archive / "old.md").write_text(
        "An archived memory that must not return to the searchable index.",
        encoding="utf-8",
    )

    import ytk.vault as vault

    monkeypatch.setattr(vault, "_get_brain_path", lambda: brain)
    monkeypatch.setattr("ytk.cache.load_index_cache", lambda: {})
    monkeypatch.setattr("ytk.cache.save_index_cache", lambda cache: None)

    assert vault.reindex_vault(force=True) == 0
    assert store._memories_collection().count() == 0


# --- YouTube takes reach the index ---------------------------------------


def _seed_video(store, video_id="vidtake"):
    from ytk.enrich import Enrichment

    store.upsert(
        {"id": video_id, "title": "T", "url": "u", "uploader": "x", "upload_date": "20260101"},
        Enrichment(
            thesis="A talk about reranking.",
            summary="Summary here.",
            key_concepts=[],
            insights=[],
            interest_tags=[],
            key_moments=[],
        ),
        segments=[],
    )


def test_append_video_take_embeds_thought(store):
    _seed_video(store)
    store.append_video_take("vidtake", "reminded me of my hub latency budget")
    doc = store._videos_collection().get(ids=["vidtake"], include=["documents"])["documents"][0]
    assert "My take: reminded me of my hub latency budget" in doc
    assert doc.startswith("A talk about reranking.")


def test_append_video_take_is_idempotent_per_thought(store):
    _seed_video(store)
    store.append_video_take("vidtake", "same thought")
    store.append_video_take("vidtake", "same thought")
    doc = store._videos_collection().get(ids=["vidtake"], include=["documents"])["documents"][0]
    assert doc.count("same thought") == 1


def test_append_video_take_missing_video_is_noop(store):
    store.append_video_take("nosuchvid", "thought")  # must not raise


def test_hub_embed_take_routes_youtube_only(monkeypatch, tmp_path):
    from ytk.ui import hub

    calls = []
    monkeypatch.setattr(
        "ytk.store.append_video_take", lambda vid, thought: calls.append((vid, thought))
    )

    yt = tmp_path / "sources" / "youtube" / "note.md"
    ig = tmp_path / "sources" / "instagram" / "note.md"
    hub._embed_take(yt, "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "neat trick")
    hub._embed_take(ig, "https://www.instagram.com/reel/abc/", "not a video take")
    hub._embed_take(yt, "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "   ")
    assert calls == [("dQw4w9WgXcQ", "neat trick")]
