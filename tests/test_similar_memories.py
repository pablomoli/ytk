"""R1 (#150): neighbor-aware remember — surface similar existing memories at
write time. Never deletes, never merges; the writer decides."""

import importlib

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store_mod

    importlib.reload(store_mod)
    store_mod.EMBEDDING_EPOCH = "v1"  # reload resets to the production default
    return store_mod


def _meta(doc_id, path):
    return {"doc_id": doc_id, "tags": "inbox, memories", "source_path": path}


def seed(store):
    store.upsert_doc(
        "m-encoder",
        "the encoder migration to Qwen3 landed; query embeddings only, rollback window open",
        _meta("m-encoder", "/vault/memories/encoder.md"),
    )
    store.upsert_doc(
        "m-tomatoes",
        "gardening tomatoes and pruning them in late summer keeps the vines healthy",
        _meta("m-tomatoes", "/vault/memories/tomatoes.md"),
    )
    store.upsert_doc(
        "m-hub",
        "the hub must be kickstarted after reinstall or it serves stale code",
        _meta("m-hub", "/vault/memories/hub.md"),
    )


def test_similar_memories_ranks_the_related_note_first(store):
    seed(store)
    hits = store.similar_memories("Qwen3 encoder migration status and rollback", n=2)
    assert hits[0].doc_id == "m-encoder"
    assert hits[0].source_path == "/vault/memories/encoder.md"
    assert 0.0 <= hits[0].similarity <= 1.0
    assert hits[0].similarity > hits[-1].similarity or len(hits) == 1
    assert "encoder migration" in hits[0].excerpt


def test_similar_memories_excludes_a_doc_id(store):
    seed(store)
    hits = store.similar_memories("Qwen3 encoder migration status", n=3, exclude_doc_id="m-encoder")
    assert all(h.doc_id != "m-encoder" for h in hits)


def test_similar_memories_empty_store_returns_nothing(store):
    assert store.similar_memories("anything at all") == []


def test_append_to_note_adds_dated_section_and_keeps_frontmatter(tmp_path, monkeypatch):
    from ytk.vault import append_to_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    note = tmp_path / "inbox" / "memories" / "2026-07-01-encoder-abc123.md"
    note.parent.mkdir(parents=True)
    note.write_text("---\nid: memory_x\ndate: 2026-07-01\n---\n\noriginal text\n", encoding="utf-8")

    path = append_to_note(
        "inbox/memories/2026-07-01-encoder-abc123.md", "an update: rollback closed"
    )

    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\nid: memory_x\n")  # frontmatter untouched
    assert "original text" in content
    assert "an update: rollback closed" in content
    assert content.index("original text") < content.index("an update")  # append, not overwrite


def test_append_to_note_rejects_paths_outside_the_brain(tmp_path, monkeypatch):
    from ytk.vault import append_to_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path / "brain")
    (tmp_path / "brain").mkdir()
    with pytest.raises(ValueError):
        append_to_note("../outside.md", "nope")


def test_append_to_note_rejects_missing_note(tmp_path, monkeypatch):
    from ytk.vault import append_to_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    with pytest.raises(FileNotFoundError):
        append_to_note("inbox/memories/no-such-note.md", "text")
