"""repair_frame_embeds: de-collide ![[frame-N.jpg]] embeds across the vault.

Obsidian resolves filename-only wikilinks vault-wide, so per-note frames
sharing bare frame-N.jpg basenames all render the same arbitrary file. The
repair renames assets to {key}-frame-N.jpg and rewrites embeds + image_paths.
"""

from __future__ import annotations

import pytest

from ytk.vault import repair_frame_embeds


@pytest.fixture
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    return tmp_path


def _seed(brain, source, key, n=2, ambiguous=True):
    note_dir = brain / "sources" / source
    frame_dir = note_dir / "frames" / key
    frame_dir.mkdir(parents=True)
    names = [(f"frame-{i}.jpg" if ambiguous else f"{key}-frame-{i}.jpg") for i in range(1, n + 1)]
    for i, name in enumerate(names, start=1):
        (frame_dir / name).write_bytes(f"jpeg{i}".encode())
    paths_yaml = "\n".join(f"  - sources/{source}/frames/{key}/{n_}" for n_ in names)
    embeds = "\n".join(f"![[{n_}]]" for n_ in names)
    note = note_dir / f"user-2026-07-15-{key}.md"
    note.write_text(
        f"---\nurl: https://example.com/{key}\ntype: {source}\n"
        f"image_paths:\n{paths_yaml}\n---\n\n![[{key}-thumb.jpg]]\n{embeds}\n\n## Caption\nc\n",
        encoding="utf-8",
    )
    return note, frame_dir


def test_repair_renames_files_and_rewrites_note(brain):
    note, frame_dir = _seed(brain, "instagram", "SC1")
    changed = repair_frame_embeds()
    assert changed == 1

    assert sorted(p.name for p in frame_dir.iterdir()) == [
        "SC1-frame-1.jpg",
        "SC1-frame-2.jpg",
    ]
    content = note.read_text(encoding="utf-8")
    assert "![[SC1-frame-1.jpg]]" in content
    assert "![[frame-1.jpg]]" not in content
    assert "sources/instagram/frames/SC1/SC1-frame-1.jpg" in content
    assert "frames/SC1/frame-1.jpg" not in content
    assert "![[SC1-thumb.jpg]]" in content  # untouched


def test_repair_covers_youtube_and_tiktok(brain):
    _seed(brain, "youtube", "VID1")
    _seed(brain, "tiktok", "789")
    assert repair_frame_embeds() == 2


def test_repair_is_idempotent(brain):
    _seed(brain, "instagram", "SC1")
    assert repair_frame_embeds() == 1
    assert repair_frame_embeds() == 0


def test_unique_names_left_alone(brain):
    note, frame_dir = _seed(brain, "instagram", "SC2", ambiguous=False)
    before = note.read_text(encoding="utf-8")
    assert repair_frame_embeds() == 0
    assert note.read_text(encoding="utf-8") == before
    assert sorted(p.name for p in frame_dir.iterdir()) == [
        "SC2-frame-1.jpg",
        "SC2-frame-2.jpg",
    ]
