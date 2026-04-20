from __future__ import annotations


_BASE_META = {
    "id": "dQw4w9WgXcQ",
    "title": "Test Video Title",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "uploader": "TestChannel",
    "upload_date": "20260101",
    "duration": 213,
}

_BASE_ENRICHMENT_KWARGS = dict(
    thesis="A test thesis.",
    summary="A test summary.",
    key_concepts=["concept: explanation"],
    insights=["insight one"],
    interest_tags=["test"],
    key_moments=[],
)


def _enrichment():
    from ytk.enrich import Enrichment
    return Enrichment(**_BASE_ENRICHMENT_KWARGS)


def test_write_note_creates_file(tmp_path, monkeypatch):
    from ytk.vault import write_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    monkeypatch.setattr("ytk.vault._save_image", lambda url, dest: None)

    path = write_note({**_BASE_META}, _enrichment(), [])

    assert path.exists()
    assert path.parent == tmp_path / "sources" / "youtube"
    content = path.read_text()
    assert "url: https://www.youtube.com/watch?v=dQw4w9WgXcQ" in content
    assert "## Thesis" in content
    assert "A test thesis." in content


def test_write_note_saves_thumbnail(tmp_path, monkeypatch):
    from ytk.vault import write_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)

    saved = []

    def fake_save(url, dest):
        p = dest.with_suffix(".jpg")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"thumb")
        saved.append((url, p))
        return p

    monkeypatch.setattr("ytk.vault._save_image", fake_save)

    meta = {**_BASE_META, "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg"}
    path = write_note(meta, _enrichment(), [])

    assert len(saved) == 1
    assert saved[0][0] == "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg"

    thumb_path = tmp_path / "sources" / "youtube" / "thumbnails" / "dQw4w9WgXcQ-thumb.jpg"
    assert thumb_path.exists()

    content = path.read_text()
    assert "![[dQw4w9WgXcQ-thumb.jpg]]" in content
    assert "image_paths:" in content
    assert "sources/youtube/thumbnails/dQw4w9WgXcQ-thumb.jpg" in content


def test_write_note_no_thumbnail_empty_image_paths(tmp_path, monkeypatch):
    from ytk.vault import write_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    monkeypatch.setattr("ytk.vault._save_image", lambda url, dest: None)

    path = write_note({**_BASE_META}, _enrichment(), [])
    content = path.read_text()

    assert "image_paths: []" in content
    assert "![[" not in content


def test_write_note_saves_frames(tmp_path, monkeypatch):
    from ytk.vault import write_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    monkeypatch.setattr("ytk.vault._save_image", lambda url, dest: None)

    frame_bytes = [b"\xff\xd8frame1", b"\xff\xd8frame2"]
    path = write_note({**_BASE_META}, _enrichment(), [], frame_bytes=frame_bytes)

    frame_dir = tmp_path / "sources" / "youtube" / "frames" / "dQw4w9WgXcQ"
    assert (frame_dir / "frame-1.jpg").read_bytes() == b"\xff\xd8frame1"
    assert (frame_dir / "frame-2.jpg").read_bytes() == b"\xff\xd8frame2"

    content = path.read_text()
    assert "![[frame-1.jpg]]" in content
    assert "![[frame-2.jpg]]" in content
    assert "frames/dQw4w9WgXcQ/frame-1.jpg" in content


def test_write_note_thumbnail_and_frames_combined(tmp_path, monkeypatch):
    from ytk.vault import write_note

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)

    def fake_save(url, dest):
        p = dest.with_suffix(".jpg")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"img")
        return p

    monkeypatch.setattr("ytk.vault._save_image", fake_save)

    meta = {**_BASE_META, "thumbnail": "https://i.ytimg.com/thumb.jpg"}
    path = write_note(meta, _enrichment(), [], frame_bytes=[b"\xff\xd8frame"])

    content = path.read_text()
    assert "![[dQw4w9WgXcQ-thumb.jpg]]" in content
    assert "![[frame-1.jpg]]" in content
    # Thumbnail comes first in image_paths
    idx_thumb = content.index("dQw4w9WgXcQ-thumb.jpg")
    idx_frame = content.index("frame-1.jpg")
    assert idx_thumb < idx_frame


def test_write_note_raises_on_duplicate(tmp_path, monkeypatch):
    from ytk.vault import write_note, NoteAlreadyExists

    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    monkeypatch.setattr("ytk.vault._save_image", lambda url, dest: None)

    write_note({**_BASE_META}, _enrichment(), [])

    import pytest
    with pytest.raises(NoteAlreadyExists):
        write_note({**_BASE_META}, _enrichment(), [])
