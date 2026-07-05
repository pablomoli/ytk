"""Signal-strength classification for taste-profile v2 (issue #16, E1/E2).

Every consumed item carries a capture signal r, read from what the pipeline
left on disk (E1 audit, 2026-07-05):

  r=0  passive     synced from the playlist, never touched
  r=1  saved       deliberate capture (social saves, snaps)
  r=2  + thought   the user wrote something at ingest (## My take)
  r=3  + directive the thought contained an instruction that linked notes

Following Hu/Koren/Volinsky, r raises CONFIDENCE, not preference: sample
weight w = 1 + alpha * r pulls cluster centroids toward high-signal items.
alpha is a config knob (interest.alpha); E3's leave-one-out eval fits it
empirically — "a shape, not a number".

Journal notes are self-authored, not consumed content, and are already
excluded from profile gathering (interest.content_sources).
"""

from __future__ import annotations

import re
from . import vault

# folders whose presence alone proves a deliberate capture
_SAVED_SOURCES = {"instagram", "tiktok", "pinterest", "web", "screenshots"}

_DIRECTIVE_RE = re.compile(r"^Related: \[\[", re.MULTILINE)
_YT_ID_RE = re.compile(r"^url:.*(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", re.MULTILINE)


def classify(source_folder: str, text: str) -> int:
    """Signal level r for one note, from its source folder and body."""
    if _DIRECTIVE_RE.search(text):
        return 3
    if "## My take" in text:
        return 2
    if source_folder in _SAVED_SOURCES:
        return 1
    return 0


def signal_map() -> dict[str, int]:
    """Map every profile join key -> r by scanning the vault's source notes.

    Keys are redundant on purpose so callers can join however their records
    are identified: YouTube video_id, the memories doc_id (source_stem), and
    the absolute note path.
    """
    out: dict[str, int] = {}
    sources = vault._get_brain_path() / "sources"
    if not sources.exists():
        return out
    for md in sources.glob("**/*.md"):
        parent = md.parent.name
        if parent in ("thumbnails", "channels") or "frames" in md.parts:
            continue
        text = md.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        r = classify(parent, text)
        out[str(md)] = r
        out[f"{parent}_{md.stem}"] = r
        m = _YT_ID_RE.search(text)
        if m:
            out[m.group(1)] = r
    return out


def signal_levels(notes: list[dict]) -> list[int]:
    """Resolve r for each gathered profile note ({id, source_path?, ...})."""
    smap = signal_map()
    return [
        smap.get(n.get("id", ""), smap.get(n.get("source_path", ""), 0))
        for n in notes
    ]


def weights(levels: list[int], alpha: float) -> list[float]:
    """Confidence weights w = 1 + alpha * r."""
    return [1.0 + alpha * r for r in levels]
