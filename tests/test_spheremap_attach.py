import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_map import _content_alignment, _frontmatter_image, _vault_rel


def _points():
    return [
        {"t": "a", "c": "youtube", "c3": [0, 0, 1]},
        {"t": "b", "c": "memory"},
        {"t": "c", "c": "instagram", "c3": [1, 0, 0]},
    ]


def _meta():
    return [
        {"title": "a", "cat": "youtube"},
        {"title": "b", "cat": "memory"},
        {"title": "c", "cat": "instagram"},
    ]


def test_alignment_returns_content_indices():
    assert _content_alignment(_points(), _meta(), {"youtube", "instagram"}) == [0, 2]


def test_alignment_rejects_count_drift():
    with pytest.raises(SystemExit):
        _content_alignment(_points()[:2], _meta(), {"youtube", "instagram"})


def test_alignment_rejects_title_drift():
    meta = _meta()
    meta[0]["title"] = "renamed since map build"
    with pytest.raises(SystemExit):
        _content_alignment(_points(), meta, {"youtube", "instagram"})


def test_vault_rel_strips_prefix_up_to_second_brain():
    path = (
        "/Users/melocoton/Library/Mobile Documents/iCloud~md~obsidian/Documents/"
        "Vault/second-brain/sources/youtube/thumbnails/x-thumb.jpg"
    )
    assert _vault_rel(path) == "sources/youtube/thumbnails/x-thumb.jpg"


def test_vault_rel_returns_none_without_second_brain_marker():
    assert _vault_rel("/tmp/some/other/path/x-thumb.jpg") is None


def test_vault_rel_leaves_already_relative_path_unchanged():
    assert _vault_rel("sources/youtube/thumbnails/x-thumb.jpg") == (
        "sources/youtube/thumbnails/x-thumb.jpg"
    )


def test_frontmatter_image_returns_first_entry(tmp_path):
    note = tmp_path / "x.md"
    note.write_text(
        "---\n"
        "url: https://example.com\n"
        "image_paths:\n"
        "  - sources/youtube/thumbnails/x-thumb.jpg\n"
        "  - sources/youtube/frames/x/0.jpg\n"
        "---\n\n"
        "body\n"
    )
    assert _frontmatter_image(note) == "sources/youtube/thumbnails/x-thumb.jpg"


def test_frontmatter_image_missing_field_returns_none(tmp_path):
    note = tmp_path / "y.md"
    note.write_text("---\nurl: https://example.com\ntitle: y\n---\n\nbody\n")
    assert _frontmatter_image(note) is None


def test_frontmatter_image_no_frontmatter_returns_none(tmp_path):
    note = tmp_path / "z.md"
    note.write_text("just a body, no frontmatter fences\n")
    assert _frontmatter_image(note) is None


def test_frontmatter_image_unclosed_fence_returns_none(tmp_path):
    note = tmp_path / "w.md"
    note.write_text(
        "---\n"
        "url: https://example.com\n"
        "image_paths:\n"
        "  - sources/youtube/thumbnails/w-thumb.jpg\n"
        "\n"
        "body without a closing fence\n"
    )
    assert _frontmatter_image(note) is None
