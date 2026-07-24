"""Slides live in sources/instagram/slides/ — nothing flat beside the notes."""

from __future__ import annotations

import pytest

import ytk.vault as vault_mod
from ytk.enrich import Enrichment
from ytk.instagram import InstagramPost
from ytk.vault import relocate_instagram_slides, write_instagram_note


@pytest.fixture
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: tmp_path)
    return tmp_path


def _enrichment():
    return Enrichment(
        thesis="t",
        summary="s",
        key_concepts=[],
        insights=[],
        interest_tags=["x"],
        key_moments=[],
    )


def test_writer_saves_slides_into_slides_subdir(brain, monkeypatch):
    saved = []

    def fake_save(url, dest):
        final = dest.with_suffix(".jpg")
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(b"img")
        saved.append(final)
        return final

    monkeypatch.setattr(vault_mod, "_save_image", fake_save)
    post = InstagramPost(
        url="https://www.instagram.com/p/CAR1/",
        username="u",
        timestamp="2026-07-15",
        caption="c",
        images=["https://cdn.example/1.jpg", "https://cdn.example/2.jpg"],
        media_kind="carousel",
    )
    path = write_instagram_note(post, _enrichment())

    slide_dir = brain / "sources" / "instagram" / "slides"
    assert (slide_dir / "CAR1-img-1.jpg").exists()
    assert (slide_dir / "CAR1-img-2.jpg").exists()
    content = path.read_text(encoding="utf-8")
    assert "sources/instagram/slides/CAR1-img-1.jpg" in content
    assert "![[CAR1-img-1.jpg]]" in content
    # nothing flat beside the notes
    flat = [p for p in (brain / "sources" / "instagram").iterdir() if p.suffix == ".jpg"]
    assert flat == []


def test_relocate_moves_flat_slides_and_rewrites_notes(brain):
    note_dir = brain / "sources" / "instagram"
    note_dir.mkdir(parents=True)
    (note_dir / "SC9-img-1.jpg").write_bytes(b"a")
    (note_dir / "SC9-img-2.jpg").write_bytes(b"b")
    note = note_dir / "u-2026-07-15-SC9.md"
    note.write_text(
        "---\nurl: https://www.instagram.com/p/SC9/\ntype: instagram\n"
        "image_paths:\n  - sources/instagram/SC9-img-1.jpg\n"
        "  - sources/instagram/SC9-img-2.jpg\n---\n\n"
        "![[SC9-img-1.jpg]]\n![[SC9-img-2.jpg]]\n\n## Caption\nc\n",
        encoding="utf-8",
    )

    assert relocate_instagram_slides() == 1

    slide_dir = note_dir / "slides"
    assert (slide_dir / "SC9-img-1.jpg").read_bytes() == b"a"
    assert not (note_dir / "SC9-img-1.jpg").exists()
    content = note.read_text(encoding="utf-8")
    assert "sources/instagram/slides/SC9-img-1.jpg" in content
    assert "sources/instagram/SC9-img-1.jpg" not in content.replace(
        "sources/instagram/slides/SC9-img-1.jpg", ""
    )
    assert "![[SC9-img-1.jpg]]" in content  # embeds untouched, filename same


def test_relocate_is_idempotent(brain):
    note_dir = brain / "sources" / "instagram"
    note_dir.mkdir(parents=True)
    (note_dir / "SC9-img-1.jpg").write_bytes(b"a")
    note = note_dir / "u-2026-07-15-SC9.md"
    note.write_text(
        "---\nurl: u\ntype: instagram\nimage_paths:\n"
        "  - sources/instagram/SC9-img-1.jpg\n---\n\n## Caption\nc\n",
        encoding="utf-8",
    )
    assert relocate_instagram_slides() == 1
    assert relocate_instagram_slides() == 0


def test_relocate_ignores_thumbnails_and_frames(brain):
    note_dir = brain / "sources" / "instagram"
    (note_dir / "thumbnails").mkdir(parents=True)
    (note_dir / "frames" / "SC").mkdir(parents=True)
    (note_dir / "thumbnails" / "SC-thumb.jpg").write_bytes(b"t")
    (note_dir / "frames" / "SC" / "SC-frame-1.jpg").write_bytes(b"f")
    assert relocate_instagram_slides() == 0
    assert (note_dir / "thumbnails" / "SC-thumb.jpg").exists()
    assert (note_dir / "frames" / "SC" / "SC-frame-1.jpg").exists()


def test_relocate_aborts_before_changes_on_destination_collision(brain):
    note_dir = brain / "sources" / "instagram"
    slide_dir = note_dir / "slides"
    slide_dir.mkdir(parents=True)
    source = note_dir / "SC9-img-1.jpg"
    source.write_bytes(b"source")
    destination = slide_dir / source.name
    destination.write_bytes(b"different")
    note = note_dir / "u-2026-07-15-SC9.md"
    original = (
        "---\nurl: u\ntype: instagram\nimage_paths:\n  - sources/instagram/SC9-img-1.jpg\n---\n"
    )
    note.write_text(original, encoding="utf-8")

    with pytest.raises(FileExistsError, match="differs"):
        relocate_instagram_slides()

    assert source.read_bytes() == b"source"
    assert destination.read_bytes() == b"different"
    assert note.read_text(encoding="utf-8") == original


def test_relocate_interruption_keeps_old_path_valid_and_rerun_recovers(brain, monkeypatch):
    note_dir = brain / "sources" / "instagram"
    note_dir.mkdir(parents=True)
    source = note_dir / "SC9-img-1.jpg"
    source.write_bytes(b"slide")
    note = note_dir / "u-2026-07-15-SC9.md"
    original = (
        "---\nurl: u\ntype: instagram\nimage_paths:\n  - sources/instagram/SC9-img-1.jpg\n---\n"
    )
    note.write_text(original, encoding="utf-8")
    real_replace = vault_mod.os.replace

    def interrupt_note_replace(src, dst):
        if dst == note:
            raise OSError("simulated interruption")
        real_replace(src, dst)

    monkeypatch.setattr(vault_mod.os, "replace", interrupt_note_replace)
    with pytest.raises(OSError, match="simulated interruption"):
        relocate_instagram_slides()

    destination = note_dir / "slides" / source.name
    assert source.exists()  # old frontmatter still resolves
    assert destination.read_bytes() == b"slide"
    assert note.read_text(encoding="utf-8") == original
    assert not list(note_dir.rglob("*.tmp"))

    monkeypatch.setattr(vault_mod.os, "replace", real_replace)
    assert relocate_instagram_slides() == 1
    assert not source.exists()
    assert destination.exists()
    assert "sources/instagram/slides/SC9-img-1.jpg" in note.read_text()


def test_relocate_removes_only_verified_duplicate_reel_cover(brain):
    note_dir = brain / "sources" / "instagram"
    thumbs = note_dir / "thumbnails"
    thumbs.mkdir(parents=True)
    duplicate = note_dir / "REEL-img-1.jpg"
    duplicate.write_bytes(b"same cover")
    thumb = thumbs / "REEL-thumb.jpg"
    thumb.write_bytes(b"same cover")
    note = note_dir / "u-2026-07-15-REEL.md"
    note.write_text(
        "---\nurl: u\ntype: instagram\nimage_paths:\n"
        "  - sources/instagram/thumbnails/REEL-thumb.jpg\n---\n",
        encoding="utf-8",
    )

    assert relocate_instagram_slides() == 0
    assert not duplicate.exists()
    assert thumb.read_bytes() == b"same cover"


def test_relocate_preserves_ambiguous_unreferenced_image(brain):
    note_dir = brain / "sources" / "instagram"
    thumbs = note_dir / "thumbnails"
    thumbs.mkdir(parents=True)
    orphan = note_dir / "UNKNOWN-img-1.jpg"
    orphan.write_bytes(b"unknown")
    (thumbs / "UNKNOWN-thumb.jpg").write_bytes(b"different")

    with pytest.raises(RuntimeError, match="not a verified duplicate"):
        relocate_instagram_slides()
    assert orphan.read_bytes() == b"unknown"


def test_visual_cover_discovery_finds_slides_subdir(brain, monkeypatch, tmp_path):
    import ytk.visual as visual_mod

    vault_root = tmp_path / "vroot"
    sources = vault_root / "second-brain" / "sources"
    (sources / "youtube").mkdir(parents=True)
    slide_dir = sources / "instagram" / "slides"
    slide_dir.mkdir(parents=True)
    (slide_dir / "SC5-img-1.jpg").write_bytes(b"x")
    (sources / "instagram" / "u-2026-07-15-SC5.md").write_text(
        "---\nurl: https://www.instagram.com/p/SC5/\ntitle: hi\n---\n", encoding="utf-8"
    )
    monkeypatch.setattr(visual_mod, "_vault", lambda: vault_root)

    items = visual_mod.iter_covers()
    ig = [i for i in items if i.item_id == "ig:SC5"]
    assert len(ig) == 1
    assert ig[0].image_path == slide_dir / "SC5-img-1.jpg"


def test_visual_cover_discovery_supports_webp_and_prefers_slides(monkeypatch, tmp_path):
    import ytk.visual as visual_mod

    vault_root = tmp_path / "vroot"
    instagram = vault_root / "second-brain" / "sources" / "instagram"
    slides = instagram / "slides"
    slides.mkdir(parents=True)
    (instagram / "SC5-img-1.webp").write_bytes(b"legacy")
    organized = slides / "SC5-img-1.webp"
    organized.write_bytes(b"organized")
    (instagram / "u-2026-07-15-SC5.md").write_text(
        "---\nurl: https://www.instagram.com/p/SC5/\ntitle: hi\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(visual_mod, "_vault", lambda: vault_root)

    ig = [i for i in visual_mod.iter_covers() if i.item_id == "ig:SC5"]
    assert len(ig) == 1
    assert ig[0].image_path == organized


def test_skip_existing_visual_index_refreshes_metadata_without_embedding(monkeypatch, tmp_path):
    import ytk.store as store_mod
    import ytk.visual as visual_mod

    image = tmp_path / "slides" / "SC5-img-1.jpg"
    image.parent.mkdir()
    image.write_bytes(b"x")
    item = visual_mod.CoverItem(
        item_id="ig:SC5",
        image_path=image,
        source="instagram",
        title="title",
        url="https://instagram.com/p/SC5/",
        note_path="note.md",
    )
    updates = []
    monkeypatch.setattr(visual_mod, "iter_covers", lambda: [item])
    monkeypatch.setattr(store_mod, "visual_ids", lambda: {"ig:SC5"})
    monkeypatch.setattr(
        store_mod,
        "update_visual_metadata",
        lambda item_id, metadata: updates.append((item_id, metadata)) or True,
    )
    monkeypatch.setattr(
        visual_mod,
        "embed_images",
        lambda paths: pytest.fail("existing covers must not be re-embedded"),
    )

    assert visual_mod.index_covers(skip_existing=True) == 0
    assert updates == [
        (
            "ig:SC5",
            {
                "source": "instagram",
                "title": "title",
                "url": "https://instagram.com/p/SC5/",
                "image_path": str(image),
                "note_path": "note.md",
            },
        )
    ]
