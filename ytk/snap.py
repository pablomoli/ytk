"""Screenshot capture into the vault — shared by `ytk snap` (clipboard via
pngpaste) and the hub's POST /api/snap (phone screenshots over Tailscale)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def save_snap(image_bytes: bytes, text: str = "", tags: list[str] | None = None) -> Path:
    """Persist an image as a screenshot memory: PNG + note in
    second-brain/sources/screenshots/, indexed into ytk_memories and
    ytk_visual. Returns the note path. Visual indexing failure is non-fatal."""
    from .store import upsert_memory
    from .vault import _get_brain_path
    from .visual import embed_cover_for_save

    tags = tags or []
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    shots_dir = _get_brain_path() / "sources" / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    img_path = shots_dir / f"{ts}.png"
    img_path.write_bytes(image_bytes)

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
