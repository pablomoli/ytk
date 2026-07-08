"""Screenshots persist as lossless WebP to shrink the synced vault without quality loss."""

import io
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from ytk import snap
from ytk import visual


def _screenshot_png() -> bytes:
    """A PNG with sharp text-like edges — the case lossy WebP would blur."""
    im = Image.new("RGB", (120, 40), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([2, 2, 40, 30], outline=(0, 0, 0))
    d.line([50, 5, 50, 35], fill=(0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_save_snap_writes_lossless_webp(tmp_path, monkeypatch):
    brain = tmp_path / "second-brain"
    png = _screenshot_png()
    with patch("ytk.vault._get_brain_path", return_value=brain), \
         patch("ytk.store.upsert_memory"), \
         patch("ytk.visual.embed_cover_for_save", return_value=True):
        note = snap.save_snap(png, text="a screenshot")
    imgs = list((brain / "sources" / "screenshots").glob("*.webp"))
    assert len(imgs) == 1, "screenshot should be saved as .webp"
    # lossless: decoded pixels identical to the source
    with Image.open(imgs[0]) as saved, Image.open(io.BytesIO(png)) as src:
        assert saved.format == "WEBP"
        assert saved.convert("RGB").tobytes() == src.convert("RGB").tobytes()
    # note embeds the webp by name
    assert imgs[0].name in note.read_text()


def test_iter_covers_finds_webp_screenshots(tmp_path, monkeypatch):
    vault = tmp_path
    shots = vault / "second-brain" / "sources" / "screenshots"
    shots.mkdir(parents=True)
    (shots / "20260708-000000.webp").write_bytes(b"x")
    (shots / "20260708-000000.md").write_text("---\ntype: screenshot\n---\n")
    with patch("ytk.visual._vault", return_value=vault):
        covers = visual.iter_covers()
    shot_ids = [c.item_id for c in covers if c.source == "screenshot"]
    assert "shot:20260708-000000" in shot_ids
