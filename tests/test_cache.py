import json
from pathlib import Path
import pytest

from ytk.cache import file_hash, load_index_cache, save_index_cache, update_cache_entry


def _write(path: Path, content: str):
    path.write_text(content, encoding="utf-8")
    return path


def test_file_hash_strips_frontmatter(tmp_path):
    """Same body content = same hash regardless of frontmatter."""
    body = "## Summary\nThis is the content.\n"
    f1 = _write(tmp_path / "a.md", f"---\ntitle: A\ntags: [ai]\n---\n{body}")
    f2 = _write(tmp_path / "b.md", f"---\ntitle: B\ntags: [go]\n---\n{body}")
    assert file_hash(f1) == file_hash(f2)


def test_file_hash_changes_on_body_change(tmp_path):
    """Body content change produces different hash."""
    fm = "---\ntitle: X\n---\n"
    f = tmp_path / "note.md"
    _write(f, fm + "original body")
    h1 = file_hash(f)
    _write(f, fm + "changed body")
    h2 = file_hash(f)
    assert h1 != h2


def test_file_hash_no_frontmatter(tmp_path):
    """Files without frontmatter hash the full content."""
    import hashlib
    content = "just a plain note"
    f = tmp_path / "plain.md"
    _write(f, content)
    h = file_hash(f)
    assert h == hashlib.sha256(content.encode()).hexdigest()


def test_load_save_roundtrip(tmp_path, monkeypatch):
    """save then load returns the same dict."""
    cache_file = tmp_path / "index_cache.json"
    monkeypatch.setattr("ytk.cache._CACHE_PATH", cache_file)

    data = {"/vault/note.md": "abc123", "/vault/other.md": "def456"}
    save_index_cache(data)
    loaded = load_index_cache()
    assert loaded == data


def test_load_missing_cache_returns_empty(tmp_path, monkeypatch):
    """Missing cache file returns empty dict, no error."""
    monkeypatch.setattr("ytk.cache._CACHE_PATH", tmp_path / "nonexistent.json")
    assert load_index_cache() == {}


def test_update_cache_entry(tmp_path, monkeypatch):
    """update_cache_entry adds the file's hash to the cache dict."""
    cache_file = tmp_path / "index_cache.json"
    monkeypatch.setattr("ytk.cache._CACHE_PATH", cache_file)

    note = tmp_path / "note.md"
    _write(note, "---\ntitle: T\n---\nbody text")

    cache = {}
    updated = update_cache_entry(note, cache)
    assert str(note) in updated
    assert len(updated[str(note)]) == 64
