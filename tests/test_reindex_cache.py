from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest


def _make_note(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_reindex_skips_cached_files(tmp_path, monkeypatch):
    """Files whose hash is already in cache are not re-embedded."""
    from ytk import cache as cache_mod

    note = _make_note(tmp_path / "projects" / "note.md", "---\ntitle: T\n---\nbody")
    cached_hash = cache_mod.file_hash(note)

    monkeypatch.setattr("ytk.cache._CACHE_PATH", tmp_path / "cache.json")
    cache_mod.save_index_cache({str(note): cached_hash})

    with patch("ytk.vault._get_vault_path", return_value=tmp_path), \
         patch("ytk.vault.upsert_doc") as mock_upsert:
        from ytk.vault import reindex_vault
        count = reindex_vault(force=False)

    mock_upsert.assert_not_called()
    assert count == 0


def test_reindex_embeds_changed_files(tmp_path, monkeypatch):
    """Files with a stale hash are re-embedded and cache updated."""
    from ytk import cache as cache_mod

    note = _make_note(tmp_path / "projects" / "note.md", "---\ntitle: T\n---\nbody")

    monkeypatch.setattr("ytk.cache._CACHE_PATH", tmp_path / "cache.json")
    cache_mod.save_index_cache({str(note): "stale_hash_value"})

    with patch("ytk.vault._get_vault_path", return_value=tmp_path), \
         patch("ytk.vault.upsert_doc") as mock_upsert:
        from ytk.vault import reindex_vault
        count = reindex_vault(force=False)

    mock_upsert.assert_called_once()
    assert count == 1


def test_reindex_force_skips_cache(tmp_path, monkeypatch):
    """force=True re-embeds all files regardless of cache."""
    from ytk import cache as cache_mod

    note = _make_note(tmp_path / "projects" / "note.md", "---\ntitle: T\n---\nbody")
    monkeypatch.setattr("ytk.cache._CACHE_PATH", tmp_path / "cache.json")
    cache_mod.save_index_cache({str(note): cache_mod.file_hash(note)})

    with patch("ytk.vault._get_vault_path", return_value=tmp_path), \
         patch("ytk.vault.upsert_doc") as mock_upsert:
        from ytk.vault import reindex_vault
        count = reindex_vault(force=True)

    mock_upsert.assert_called_once()
    assert count == 1
