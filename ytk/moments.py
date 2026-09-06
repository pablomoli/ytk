"""Key-moment timestamp snap (#197): move a stamp to the transcript line
that says what the description says, before any grader call.

Measured 2026-09-06: most double bounces were moments 20 s to 20 min off a
line that exists. A wrong stamp is a lookup failure in a note whose whole
job is lookup, and finding the line is a text search, not a model call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enrich import KeyMoment, fmt_ts
from .enricher import EnrichmentV2

# A moment already sitting next to a matching line stays (the grader's own
# adjacency rule); only stamps with no match in that window move.
ADJACENCY_WINDOW_S = 90.0
# Merged-line window the description is matched against: the line and what
# follows it within this many seconds (a gap in the transcript is a cut, not
# a continuation).
LINES_PER_WINDOW = 3
WINDOW_SPAN_S = 20.0
# Fewer shared content words than this is coincidence, not the line.
MIN_SHARED = 2


@dataclass(frozen=True)
class Move:
    description: str
    before: str
    after: str


def _parse_ts(ts: str) -> float | None:
    parts = ts.strip().split(":")
    if not all(p.strip().isdigit() for p in parts) or not 2 <= len(parts) <= 3:
        return None
    nums = [int(p) for p in parts]
    return float(sum(n * 60**i for i, n in enumerate(reversed(nums))))


def _windows(transcript: list[dict[str, Any]]) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for i in range(len(transcript)):
        start = float(transcript[i].get("start", 0))
        chunk = [
            s
            for s in transcript[i : i + LINES_PER_WINDOW]
            if float(s.get("start", 0)) - start <= WINDOW_SPAN_S
        ]
        out.append((start, " ".join(str(s.get("text", "")) for s in chunk)))
    return out


def snap_key_moments(
    draft: EnrichmentV2, transcript: list[dict[str, Any]]
) -> tuple[EnrichmentV2, list[Move]]:
    """Return the draft with mis-stamped moments moved, and what moved."""
    from .grader import content_tokens  # the grader's matcher, so snap and check agree

    if not transcript or not draft.key_moments:
        return draft, []
    windows = _windows(transcript)
    moves: list[Move] = []
    moments: list[KeyMoment] = []
    for km in draft.key_moments:
        secs = _parse_ts(km.timestamp)
        words = content_tokens(km.description)
        if secs is None or not words:
            moments.append(km)
            continue
        near = any(
            words & content_tokens(text)
            for start, text in windows
            if abs(start - secs) <= ADJACENCY_WINDOW_S
        )
        if near:
            moments.append(km)
            continue
        best_start: float | None = None
        best_shared = 0
        for start, text in windows:
            shared = len(words & content_tokens(text))
            if shared > best_shared:
                best_start, best_shared = start, shared
        if best_start is None or best_shared < MIN_SHARED:
            moments.append(km)
            continue
        stamp = fmt_ts(best_start)
        moves.append(Move(description=km.description, before=km.timestamp, after=stamp))
        moments.append(km.model_copy(update={"timestamp": stamp}))
    if not moves:
        return draft, []
    return draft.model_copy(update={"key_moments": moments}), moves
