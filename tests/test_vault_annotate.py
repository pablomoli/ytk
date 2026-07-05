"""Tests for ingest-hub annotation: bucket tags, My take sections, daily digest."""

from __future__ import annotations

import pytest


SAMPLE_NOTE = """---
url: https://www.instagram.com/reel/abc/
username: someone
date: 2026-07-01
title: A reel about spice racks
tags:
  - 3d-printing
  - organization
type: instagram
---

## Summary
A spice rack that spins.
"""

NOTE_NO_TAGS = """---
url: https://example.com/article
title: An article
type: web
---

Body text.
"""


@pytest.fixture
def note(tmp_path, monkeypatch):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    d = tmp_path / "sources" / "instagram"
    d.mkdir(parents=True)
    p = d / "someone-2026-07-01-abc.md"
    p.write_text(SAMPLE_NOTE, encoding="utf-8")
    return p


def test_annotate_adds_bucket_tag_and_take_section(note):
    from ytk.vault import annotate_note

    annotate_note(note, bucket="build-idea", thought="I could make this for my desk.")
    text = note.read_text(encoding="utf-8")
    assert "  - build-idea\n" in text
    assert text.index("- build-idea") < text.index("type: instagram")
    assert "## My take" in text
    assert "I could make this for my desk." in text


def test_annotate_bucket_only_no_empty_section(note):
    from ytk.vault import annotate_note

    annotate_note(note, bucket="design", thought="")
    text = note.read_text(encoding="utf-8")
    assert "  - design\n" in text
    assert "## My take" not in text


def test_annotate_no_duplicate_tag_and_appends_second_take(note):
    from ytk.vault import annotate_note

    annotate_note(note, bucket="design", thought="first thought")
    annotate_note(note, bucket="design", thought="second thought")
    text = note.read_text(encoding="utf-8")
    assert text.count("- design") == 1
    assert text.count("## My take") == 1
    assert "first thought" in text and "second thought" in text


def test_annotate_note_without_tags_block(tmp_path, monkeypatch):
    from ytk.vault import annotate_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    p = tmp_path / "note.md"
    p.write_text(NOTE_NO_TAGS, encoding="utf-8")
    annotate_note(p, bucket="music", thought="")
    text = p.read_text(encoding="utf-8")
    assert "tags:\n  - music\n" in text
    assert text.index("tags:") < text.index("---", 4)  # inside frontmatter


def test_annotate_normalizes_bucket(note):
    from ytk.vault import annotate_note

    annotate_note(note, bucket="Anime Recs", thought="")
    assert "  - anime-recs\n" in note.read_text(encoding="utf-8")


def test_append_daily_digest_creates_and_appends(tmp_path, monkeypatch, note):
    from ytk.vault import append_daily_digest

    line_path = append_daily_digest(note, bucket="build-idea",
                                    thought="I could make this for my desk, honestly.")
    assert line_path.parent.name == "inbox"
    text = line_path.read_text(encoding="utf-8")
    assert "[[someone-2026-07-01-abc]]" in text
    assert "#build-idea" in text
    assert "I could make this" in text

    append_daily_digest(note, bucket="music", thought="")
    text = line_path.read_text(encoding="utf-8")
    assert text.count("[[someone-2026-07-01-abc]]") == 2


def test_append_daily_digest_truncates_long_thoughts(tmp_path, monkeypatch, note):
    from ytk.vault import append_daily_digest

    path = append_daily_digest(note, bucket="b", thought="x" * 300)
    line = [l for l in path.read_text().splitlines() if "[[" in l][0]
    assert len(line) < 200
