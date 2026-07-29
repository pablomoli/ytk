"""R5 (#150): capture dates come from the note, not the filesystem.

A2 (docs/assets/memory-field/a2-mtime-divergence.png) showed a single mass
rewrite restamped 3,343 mtimes on 2026-05-02 — mtime is a sync artifact, so
every age decision must prefer the note's own capture stamp."""

from __future__ import annotations

import os
from datetime import datetime


def write(path, text=""):
    path.write_text(text, encoding="utf-8")
    return path


def test_capture_date_prefers_captured_frontmatter(tmp_path):
    from ytk.vault import note_capture_date

    p = write(tmp_path / "2026-03-01-note.md", "---\ncaptured: 2026-02-01\ndate: 2026-01-01\n---\n")
    assert note_capture_date(p) == datetime(2026, 2, 1)


def test_capture_date_falls_back_to_dated_filename(tmp_path):
    from ytk.vault import note_capture_date

    p = write(tmp_path / "2026-03-01-some-memory-abc123.md", "no frontmatter")
    assert note_capture_date(p) == datetime(2026, 3, 1)


def test_capture_date_falls_back_to_frontmatter_date(tmp_path):
    from ytk.vault import note_capture_date

    p = write(tmp_path / "undated-name.md", "---\ndate: 2026-04-15\n---\nbody")
    assert note_capture_date(p) == datetime(2026, 4, 15)


def test_capture_date_last_resort_is_mtime(tmp_path):
    from ytk.vault import note_capture_date

    p = write(tmp_path / "undated-name.md", "no stamps anywhere")
    stamp = datetime(2026, 6, 1).timestamp()
    os.utime(p, (stamp, stamp))
    assert note_capture_date(p) == datetime.fromtimestamp(stamp)


def test_stale_memories_uses_capture_date_not_mtime(tmp_path):
    from ytk.vault import stale_memories

    now = datetime(2026, 7, 29)
    # captured in January, but mtime says yesterday (the mass-rewrite shape):
    # date-aware gc must call it stale where mtime-gc would keep it forever
    old_note = write(tmp_path / "2026-01-05-old-decision-aaaaaa.md", "---\ndate: 2026-01-05\n---\n")
    fresh = now.timestamp() - 3600
    os.utime(old_note, (fresh, fresh))
    # captured recently, but an ancient mtime (restored backup): must be kept
    new_note = write(tmp_path / "2026-07-20-new-decision-bbbbbb.md", "---\ndate: 2026-07-20\n---\n")
    ancient = datetime(2025, 1, 1).timestamp()
    os.utime(new_note, (ancient, ancient))

    stale = stale_memories(tmp_path, days=90, now=now)
    assert [p.name for p in stale] == ["2026-01-05-old-decision-aaaaaa.md"]


def test_video_note_carries_captured_stamp(tmp_path, monkeypatch):
    from ytk.enrich import Enrichment
    from ytk.vault import write_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    monkeypatch.setattr("ytk.vault._save_image", lambda url, dest: None)
    path = write_note(
        {
            "id": "dQw4w9WgXcQ",
            "title": "T",
            "url": "https://youtu.be/dQw4w9WgXcQ",
            "uploader": "U",
            "upload_date": "20260101",
            "duration": 10,
        },
        Enrichment(
            thesis="t",
            summary="s",
            key_concepts=[],
            insights=[],
            interest_tags=["x"],
            key_moments=[],
        ),
        [],
    )
    content = path.read_text()
    assert f"captured: {datetime.now():%Y-%m-%d}" in content
    assert "date: 2026-01-01" in content  # upload date unchanged — different fact
