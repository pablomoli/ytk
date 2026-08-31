"""Rubric loading (#197 P4): owner-owned file, versioned by hash so every
grade row names the version it was judged under."""

import pytest

from ytk import rubric


def test_env_seam_wins(tmp_path, monkeypatch):
    p = tmp_path / "rubric.md"
    p.write_text("# Rubric\n\nBe dense.\n")
    monkeypatch.setenv("YTK_RUBRIC", str(p))
    assert rubric.rubric_path() == p


def test_load_returns_text_and_stable_hash(tmp_path, monkeypatch):
    p = tmp_path / "rubric.md"
    p.write_text("# Rubric\n\nBe dense.\n")
    monkeypatch.setenv("YTK_RUBRIC", str(p))
    r1 = rubric.load()
    r2 = rubric.load()
    assert r1.text.startswith("# Rubric")
    assert r1.hash == r2.hash
    assert len(r1.hash) == 12
    p.write_text("# Rubric\n\nBe denser.\n")
    assert rubric.load().hash != r1.hash


def test_missing_rubric_is_a_loud_error(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_RUBRIC", str(tmp_path / "absent.md"))
    with pytest.raises(FileNotFoundError):
        rubric.load()
