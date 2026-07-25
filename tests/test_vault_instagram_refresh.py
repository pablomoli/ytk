"""refresh_instagram_note: atomic in-place upgrade preserving user metadata."""

from __future__ import annotations

import pytest

import ytk.vault as vault_mod
from ytk.enrich import Enrichment
from ytk.instagram import InstagramPost
from ytk.vault import refresh_instagram_note, write_instagram_note


@pytest.fixture
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    return tmp_path


def _post(**overrides):
    base = {
        "url": "https://www.instagram.com/reel/SC123/",
        "username": "elif.codes",
        "timestamp": "2026-07-15",
        "caption": "Comment judge",
        "images": [],
        "media_kind": "video",
    }
    base.update(overrides)
    return InstagramPost(**base)


def _enrichment(thesis="old thesis", tags=("ai-coding",)):
    return Enrichment(
        thesis=thesis,
        summary="s",
        key_concepts=[],
        insights=[],
        interest_tags=list(tags),
        key_moments=[],
    )


def _seed_v1_note(brain):
    """A schema-1 hollow reel note, as the old pipeline wrote it."""
    path = write_instagram_note(_post(), _enrichment())
    # simulate pre-schema note: strip the capture stamp the new writer adds
    content = path.read_text(encoding="utf-8")
    content = content.replace("media: video\ncapture_schema: 2\nframes: 0\ntranscript: none\n", "")
    path.write_text(content, encoding="utf-8")
    return path


def test_refresh_replaces_generated_content_at_same_path(brain):
    old_path = _seed_v1_note(brain)
    new_path = refresh_instagram_note(
        _post(),
        _enrichment(thesis="new thesis"),
        transcript_segments=[{"start": 0, "duration": 1.0, "text": "hello"}],
        transcript_status="ok",
        frame_bytes=[b"f1"],
    )
    assert new_path == old_path
    content = new_path.read_text(encoding="utf-8")
    assert "new thesis" in content
    assert "old thesis" not in content
    assert "capture_schema: 2" in content
    assert "transcript: ok" in content
    assert "[0:00] hello" in content


def test_refresh_unions_old_tags_including_slop(brain):
    old_path = _seed_v1_note(brain)
    content = old_path.read_text(encoding="utf-8")
    old_path.write_text(content.replace("tags:\n", "tags:\n  - slop?\n"), encoding="utf-8")
    new_path = refresh_instagram_note(
        _post(), _enrichment(tags=("build-idea",)), transcript_status="ok"
    )
    content = new_path.read_text(encoding="utf-8")
    assert "  - slop?" in content
    assert "  - build-idea" in content
    assert "  - ai-coding" in content  # original enrichment tag survives too


def test_refresh_preserves_user_sections(brain):
    old_path = _seed_v1_note(brain)
    with old_path.open("a", encoding="utf-8") as f:
        f.write("\n## My take\n\nthis one matters for the judge project\n")
    new_path = refresh_instagram_note(_post(), _enrichment(thesis="new"), transcript_status="ok")
    content = new_path.read_text(encoding="utf-8")
    assert "## My take" in content
    assert "this one matters for the judge project" in content
    assert content.count("## My take") == 1


def test_refresh_is_idempotent(brain):
    _seed_v1_note(brain)
    kwargs = {
        "transcript_segments": [{"start": 0, "duration": 1.0, "text": "x"}],
        "transcript_status": "ok",
        "frame_bytes": [b"f"],
    }
    p1 = refresh_instagram_note(_post(), _enrichment(thesis="n"), **kwargs)
    first = p1.read_text(encoding="utf-8")
    p2 = refresh_instagram_note(_post(), _enrichment(thesis="n"), **kwargs)
    assert p2.read_text(encoding="utf-8") == first


def test_failed_refresh_leaves_original_byte_for_byte(brain, monkeypatch):
    old_path = _seed_v1_note(brain)
    original = old_path.read_bytes()

    def boom(url, dest):
        raise RuntimeError("cdn down")

    monkeypatch.setattr(vault_mod, "_save_image", boom)
    with pytest.raises(RuntimeError):
        refresh_instagram_note(
            _post(thumbnail_url="https://cdn.example/t.jpg"),
            _enrichment(thesis="new"),
            transcript_status="ok",
        )
    assert old_path.read_bytes() == original


def test_refresh_replaces_stale_frames(brain):
    _seed_v1_note(brain)
    frame_dir = brain / "sources" / "instagram" / "frames" / "SC123"
    frame_dir.mkdir(parents=True)
    for i in (1, 2, 3):
        (frame_dir / f"frame-{i}.jpg").write_bytes(b"stale")

    refresh_instagram_note(
        _post(), _enrichment(), transcript_status="ok", frame_bytes=[b"new1", b"new2"]
    )
    files = sorted(p.name for p in frame_dir.iterdir())
    assert files == ["SC123-frame-1.jpg", "SC123-frame-2.jpg"]
    assert (frame_dir / "SC123-frame-1.jpg").read_bytes() == b"new1"


def test_refresh_without_existing_note_writes_new(brain):
    path = refresh_instagram_note(_post(), _enrichment(), transcript_status="ok")
    assert path.exists()
    assert "capture_schema: 2" in path.read_text(encoding="utf-8")
