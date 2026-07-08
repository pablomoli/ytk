"""Screenshot capture into the vault — shared by `ytk snap` (clipboard via
pngpaste) and the hub's POST /api/snap (phone screenshots over Tailscale)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def _write_lossless_webp(image_bytes: bytes, dest_stem: Path) -> Path:
    """Encode a screenshot to lossless WebP at ``dest_stem.webp``.

    Lossless keeps text and sharp UI edges pixel-exact (a screenshot's whole
    point) while still shrinking PNGs markedly in the iCloud-synced vault. Bytes
    PIL cannot decode fall back to a verbatim ``.png`` write so nothing is lost.
    """
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            im.load()
            out = dest_stem.with_suffix(".webp")
            im.save(out, format="WEBP", lossless=True, method=4)
            return out
    except Exception:
        out = dest_stem.with_suffix(".png")
        out.write_bytes(image_bytes)
        return out


def save_snap(image_bytes: bytes, text: str = "", tags: list[str] | None = None) -> Path:
    """Persist an image as a screenshot memory: lossless WebP + note in
    second-brain/sources/screenshots/, indexed into ytk_memories and
    ytk_visual. Returns the note path. Visual indexing failure is non-fatal."""
    from .store import upsert_memory
    from .vault import _get_brain_path
    from .visual import embed_cover_for_save

    tags = tags or []
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    shots_dir = _get_brain_path() / "sources" / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    img_path = _write_lossless_webp(image_bytes, shots_dir / ts)

    note_path = shots_dir / f"{ts}.md"
    note_path.write_text(
        "---\n"
        f"date: {datetime.now().strftime('%Y-%m-%d')}\n"
        "type: screenshot\n"
        f"tags: [{', '.join(tags)}]\n"
        "---\n\n"
        f"![[{img_path.name}]]\n\n"
        f"{text}\n"
    )

    upsert_memory(f"shot_{ts}", text or f"screenshot {ts}", tags, str(note_path))
    embed_cover_for_save(img_path, f"shot:{ts}", {
        "source": "screenshot",
        "title": text[:80],
        "url": "",
        "note_path": str(note_path),
    })
    return note_path
