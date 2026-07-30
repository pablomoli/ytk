"""E2 (#149): the fetch layer of the index -> select -> fetch contract.
Details arrive only by explicit id, and a fetch returns the stored document
text (parts merged) — not the raw file, whose transcript is the token sink."""

import importlib

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store_mod

    importlib.reload(store_mod)
    store_mod.EMBEDDING_EPOCH = "v1"  # reload resets to the production default
    return store_mod


def _meta(doc_id, path="/vault/memories/x.md"):
    return {"doc_id": doc_id, "tags": "inbox", "source_path": path}


def test_fetch_docs_returns_stored_text_by_id(store):
    text = (
        "a note about tmux panes and capture that comfortably clears the minimum embed length floor"
    )
    store.upsert_doc("m1", text, _meta("m1"))
    got = store.fetch_docs(["m1"])
    assert got == [("m1", text)]


def test_fetch_docs_merges_parts_and_skips_unknown_ids(store):
    long_text = "Field notes header\n\n" + "\n\n".join(
        f"Paragraph {i}: " + ("tiles and shaders and pipelines, " * 16) for i in range(7)
    )
    store.upsert_doc("m1", long_text, _meta("m1"))
    got = store.fetch_docs(["m1", "no-such-id"])
    assert len(got) == 1
    doc_id, text = got[0]
    assert doc_id == "m1"
    assert "Paragraph 6" in text  # tail part present, not just the head vector
    assert len(got) == 1  # unknown id skipped, not errored
