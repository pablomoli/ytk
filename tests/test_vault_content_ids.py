"""Canonical content-note ids: ingest and reindex must derive the same id (#95)."""

from __future__ import annotations

from ytk.vault import content_note_doc_id, vault_note_doc_id


def test_content_note_id_matches_reindexer_derivation(tmp_path, monkeypatch):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    note = tmp_path / "sources" / "tiktok" / "creator-2026-07-19-some clip.md"
    note.parent.mkdir(parents=True)
    note.write_text("---\nurl: https://example.com\n---\n\nbody\n", encoding="utf-8")

    doc_id = content_note_doc_id(note)
    assert doc_id == "note_sources_tiktok_creator-2026-07-19-some_clip"
    assert doc_id == vault_note_doc_id(note, tmp_path)


def test_content_note_id_honors_frontmatter_override(tmp_path, monkeypatch):
    """id: frontmatter pins an id for good — memory atoms rely on this, and a
    content note carrying one must keep it through ingest exactly as the
    reindexer would."""
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    note = tmp_path / "sources" / "reddit" / "post.md"
    note.parent.mkdir(parents=True)
    note.write_text("---\nid: pinned_id_123\n---\n\nbody\n", encoding="utf-8")

    assert content_note_doc_id(note) == "pinned_id_123"
