# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
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

import math
import re
from collections import Counter
from datetime import UTC, datetime

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
    return [smap.get(n.get("id", ""), smap.get(n.get("source_path", ""), 0)) for n in notes]


def weights(levels: list[int], alpha: float) -> list[float]:
    """Confidence weights w = 1 + alpha * r."""
    return [1.0 + alpha * r for r in levels]


def _parse_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def recency_factor(captured_at: str, now: datetime, half_life_days: float) -> float:
    """Exponential capture-time decay; unknown legacy dates remain neutral.

    Unknown is deliberately not guessed from publication date: an old video
    saved today is fresh evidence of current interest. Unknown records can
    retain their cluster influence but cannot establish claim freshness.
    """
    captured = _parse_utc(captured_at)
    if captured is None:
        return 1.0
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    age_days = max(0.0, (now.astimezone(UTC) - captured).total_seconds() / 86400)
    return 0.5 ** (age_days / half_life_days)


def day_batch_factors(captured_at: list[str]) -> list[float]:
    """1/sqrt(number of notes captured the same day); unknown dates undamped.

    A heavy ingest day is one day of attention, not N independent acts of
    interest: seventeen same-day saves weigh ~4x a single-save day, not 17x,
    so one binge cannot swing the profile's theme weights.
    """
    days = [ts[:10] if ts else "" for ts in captured_at]
    counts = Counter(d for d in days if d)
    return [1.0 / math.sqrt(counts[d]) if d else 1.0 for d in days]


def decayed_weights(
    levels: list[int],
    captured_at: list[str],
    alpha: float,
    half_life_days: float,
    now: datetime,
) -> list[float]:
    """Confidence x recency x batch dampening:
    (1 + alpha*r) * 0.5**(age/half-life) / sqrt(same-day batch size)."""
    if len(levels) != len(captured_at):
        raise ValueError("levels and captured_at must have matching lengths")
    batch = day_batch_factors(captured_at)
    return [
        (1.0 + alpha * r) * recency_factor(ts, now, half_life_days) * b
        for r, ts, b in zip(levels, captured_at, batch)
    ]
