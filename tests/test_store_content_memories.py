"""Tests for the content-memory accessor used by the synthesis engine."""

from __future__ import annotations

import importlib


def test_get_content_memories_filters_by_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store

    importlib.reload(store)
    store.EMBEDDING_EPOCH = "v1"  # reload resets to the production default

    store.upsert_doc(
        "note_sources_instagram_reel_a",
        "## Caption\nhi\n## Thesis\nA boxing footwork drill.\n## Summary\nx",
        {
            "doc_id": "note_sources_instagram_reel_a",
            "tags": "boxing, mma",
            "source_path": "/p/a.md",
        },
    )
    store.upsert_doc(
        "note_session_b",
        "## Current Understanding\nproject stuff",
        {"doc_id": "note_session_b", "tags": "ytk", "source_path": "/p/b.md"},
    )

    rows = store.get_content_memories(["instagram", "tiktok", "web"])
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "note_sources_instagram_reel_a"
    assert row["thesis"] == "A boxing footwork drill."
    assert row["tags"] == ["boxing", "mma"]
    assert len(row["embedding"]) > 10
    assert row["title"] == ""


def test_get_content_memories_ignores_retired_bare_scheme(tmp_path, monkeypatch):
    """Bare ingest-time ids ({source}_{stem60}) are a retired scheme (#95):
    the migration renamed every live record, ingest now writes the canonical
    path-derived id, and the accessor no longer dual-matches. A bare id
    appearing again would mean a writer regressed — it must NOT be counted."""
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    import ytk.store as store

    importlib.reload(store)
    store.EMBEDDING_EPOCH = "v1"

    store.upsert_doc(
        "instagram_reel_bare",
        "## Caption\nhi\n## Thesis\nA stray bare-scheme record.\n## Summary\nx",
        {"doc_id": "instagram_reel_bare", "tags": "boxing", "source_path": "/p/bare.md"},
    )
    store.upsert_doc(
        "note_sources_instagram_reel_c",
        "## Caption\nhi\n## Thesis\nA neon shader breakdown.\n## Summary\nx",
        {"doc_id": "note_sources_instagram_reel_c", "tags": "shaders", "source_path": "/p/c.md"},
    )
    store.upsert_doc(
        "note_projects_ytk_session",  # wiki/project notes must stay excluded
        "## Current Understanding\nproject stuff that is long enough to embed",
        {"doc_id": "note_projects_ytk_session", "tags": "ytk", "source_path": "/p/d.md"},
    )

    rows = store.get_content_memories(["instagram", "tiktok"])
    assert [r["id"] for r in rows] == ["note_sources_instagram_reel_c"]
    assert rows[0]["source"] == "instagram"
