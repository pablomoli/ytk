"""Memory docs are embedded as parts (#84) and phantom copies are guarded (#71)."""

import importlib

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store_mod

    importlib.reload(store_mod)
    store_mod.EMBEDDING_EPOCH = "v1"  # reload resets to the production default
    return store_mod


def _long_text(tail_marker="zanzibar sourdough telescope"):
    """~4200 chars in paragraphs; the marker lives past the 512-token cliff."""
    head = "Field notes on the renderer\n\n"
    body = "\n\n".join(
        f"Paragraph {i}: " + ("tiles and shaders and pipelines, " * 16) for i in range(7)
    )
    return head + body + f"\n\nFinal thought: {tail_marker} is the trick to remember."


def _meta(doc_id, path="/vault/second-brain/inbox/memories/x/note.md"):
    return {"doc_id": doc_id, "tags": "inbox, memories", "source_path": path}


def test_short_doc_stays_single_vector(store):
    store.upsert_doc(
        "m1", "one small note that still clears the minimum embed length floor", _meta("m1")
    )
    got = store._memories_collection().get()
    assert got["ids"] == ["m1"]


def test_long_doc_splits_into_context_prefixed_parts(store):
    store.upsert_doc("m1", _long_text(), _meta("m1"))
    got = store._memories_collection().get()
    ids = sorted(got["ids"])
    assert ids[0] == "m1" and len(ids) >= 3 and all("#" in i for i in ids[1:])
    docs = dict(zip(got["ids"], got["documents"]))
    metas = dict(zip(got["ids"], got["metadatas"]))
    for pid in ids[1:]:
        assert docs[pid].startswith("Field notes on the renderer")
        assert metas[pid]["doc_id"] == "m1"
    assert all(len(d) <= store._DOC_PART_LIMIT + 130 for d in docs.values())


def test_search_finds_doc_by_tail_content(store):
    """The point of the fix: text past the 512-token cliff is genuinely embedded."""
    store.upsert_doc("m1", _long_text(), _meta("m1"))
    store.upsert_doc(
        "m2",
        "a note about gardening tomatoes and pruning them in late summer",
        _meta("m2", path="/vault/second-brain/tools/t.md"),
    )
    hits = [r for r in store.search_all("zanzibar sourdough telescope", n=4) if r.type == "memory"]
    assert hits and hits[0].doc_id == "m1"
    ids = [h.doc_id for h in hits]
    assert len(ids) == len(set(ids)), "parts of one doc must collapse to one result"


def test_reupsert_prunes_leftover_parts(store):
    store.upsert_doc("m1", _long_text(), _meta("m1"))
    store.upsert_doc(
        "m1", "now it is short but still long enough to stay embedded as one vector", _meta("m1")
    )
    got = store._memories_collection().get()
    assert got["ids"] == ["m1"]


def test_guard_deletes_old_id_scheme_for_same_file(store):
    """A note re-indexed under a new id must not leave a phantom copy (#71)."""
    path = "/vault/second-brain/sources/instagram/reel.md"
    store.upsert_doc(
        "note_sources_instagram_reel",
        "an old-scheme row that was indexed before the id scheme changed",
        _meta("note_sources_instagram_reel", path),
    )
    store.upsert_doc(
        "instagram_reel",
        "the same note reindexed under the new id scheme with equal body",
        _meta("instagram_reel", path),
    )
    got = store._memories_collection().get()
    assert got["ids"] == ["instagram_reel"]


def test_delete_doc_removes_parts(store):
    store.upsert_doc("m1", _long_text(), _meta("m1"))
    store.delete_doc("m1")
    assert store._memories_collection().count() == 0


def test_get_content_memories_one_row_per_doc(store):
    store.upsert_doc("instagram_reel", _long_text(), _meta("instagram_reel"))
    rows = store.get_content_memories(["instagram"])
    assert [r["id"] for r in rows] == ["instagram_reel"]
