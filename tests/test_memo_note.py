"""Memo note is written before routing and finalized after."""

from pathlib import Path
from unittest.mock import patch

from ytk.memo import finalize_memo_note, write_memo_note


def _fake_brain(tmp_path):
    return patch("ytk.memo._get_brain_path", return_value=tmp_path)


def test_write_memo_note_creates_pending_note(tmp_path):
    with _fake_brain(tmp_path):
        note = write_memo_note("test the hub filters tomorrow", Path("/tmp/x.wav"))
    assert note.parent == tmp_path / "inbox" / "memos"
    content = note.read_text()
    assert "route: pending" in content
    assert "source: voice" in content
    assert "audio: /tmp/x.wav" in content
    assert "test the hub filters tomorrow" in content


def test_write_memo_note_without_audio(tmp_path):
    with _fake_brain(tmp_path):
        note = write_memo_note("typed memo", None)
    assert "audio:" not in note.read_text()


def test_finalize_updates_route_and_appends_routed(tmp_path):
    with _fake_brain(tmp_path):
        note = write_memo_note("file an issue about filters", Path("/tmp/x.wav"))
    finalize_memo_note(
        note, "action", ["gh-issue -> pablomoli/ytk: Fix filters (https://github.com/x/1)"]
    )
    content = note.read_text()
    assert "route: action" in content
    assert "route: pending" not in content
    assert "## Routed" in content
    assert "gh-issue -> pablomoli/ytk" in content


def test_finalize_failed_routing(tmp_path):
    with _fake_brain(tmp_path):
        note = write_memo_note("some words", None)
    finalize_memo_note(note, "failed", [])
    content = note.read_text()
    assert "route: failed" in content
    assert "## Routed" not in content


def test_index_memo_note_upserts(tmp_path):
    from ytk.memo import index_memo_note

    note = tmp_path / "2026-07-05-1200-x.md"
    note.touch()
    with patch("ytk.store.upsert_memory") as ups:
        index_memo_note(note, "the transcript", "thought")
    ups.assert_called_once_with(
        "memo_2026-07-05-1200-x", "the transcript", ["memo", "thought"], str(note)
    )


def test_write_memo_note_same_minute_no_collision(tmp_path):
    with _fake_brain(tmp_path):
        a = write_memo_note("test the hub filters tomorrow morning first thing", None)
        b = write_memo_note("test the hub filters tomorrow but differently", None)
    assert a != b
    assert a.exists() and b.exists()


def test_write_memo_note_dedupes_identical_content(tmp_path):
    """The same transcript re-submitted within the window reuses the note.

    The iMessage pipeline dedupes on session identity, not content, so the
    same self-note arriving as distinct sessions would otherwise write a fresh
    memo each time. Content-hash dedup at write time is the backstop.
    """
    with _fake_brain(tmp_path):
        a = write_memo_note("why is it stupid all of a sudden", None)
        b = write_memo_note("why is it stupid all of a sudden", None)
    assert a == b
    assert len(list((tmp_path / "inbox" / "memos").glob("*.md"))) == 1


def test_write_memo_note_dedup_ignores_stale_notes(tmp_path):
    """A byte-identical note older than the window does not suppress a new one."""
    import os
    import time
    from datetime import datetime, timedelta

    with _fake_brain(tmp_path):
        old = write_memo_note("a thought worth having twice", None)
        stale = time.time() - (7 * 60 * 60)
        os.utime(old, (stale, stale))

        class _Clock:
            @staticmethod
            def now():
                return datetime.now() + timedelta(hours=7)

        with patch("ytk.memo.datetime", _Clock):
            new = write_memo_note("a thought worth having twice", None)
    assert new != old
    assert new.exists() and old.exists()
