"""Key-moment timestamp snap (#197): move a stamp to the transcript line
that says what the description says, before any grader call.

Measured 2026-09-06: most double bounces were moments 20 s to 20 min off a
line that exists. A wrong stamp is a lookup failure in a note whose whole
job is lookup, and finding the line is a text search, not a model call.

check_anchors reads every transcript citation (key moments and [t:N] cites)
against the span it cites and reports ok / moved / unsupported. It is a
measurement, not wired into the curator: scripts/replay_anchor_check.py
holds the replay that decided that.
"""

from __future__ import annotations

import math
import re
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


# --- anchor check: every transcript citation against its cited span --------
#
# The snap above moves a moment only when nothing in the adjacency window
# matches; this check reads the cited span itself, so a cite that sits next
# to a line saying none of the claim moves to the line that does.

# Below this many seconds a move lands inside the cited span's own lines.
MIN_MOVE_S = 3.0
# Cited-time slack: "5:48" cites the line that started at 5:47.6.
CITE_SLACK_S = 1.0

_LIST_FIELDS = ("key_concepts", "insights", "evidence_gaps")
_PROSE_FIELDS = ("thesis", "summary", "take_response")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_T_CITE = re.compile(r"\[t:(\d+)\]")
_FRAME_CITE = re.compile(r"\[(?:frame:\d{3}|sheet)\]")


@dataclass(frozen=True)
class Anchor:
    field: str  # key_moments, key_concepts, summary, ...
    index: int  # list position, or sentence position in a prose field
    claim: str
    cited: str  # as written: "5:48" for a moment, "t:348" for a cite
    cited_s: float
    verdict: str  # ok | moved | unsupported
    after: str | None  # the new anchor, same form as cited, when moved
    cited_shared: int  # claim words in the cited span
    best_shared: int  # claim words in the best span within the window
    cited_score: float  # the same, IDF-weighted
    best_score: float


@dataclass(frozen=True)
class AnchorReport:
    anchors: list[Anchor]
    frame_cites: int  # [frame:NNN] and [sheet] cites: not checkable from text

    @property
    def moved(self) -> list[Anchor]:
        return [a for a in self.anchors if a.verdict == "moved"]

    @property
    def unsupported(self) -> list[Anchor]:
        return [a for a in self.anchors if a.verdict == "unsupported"]


def _citations(draft: EnrichmentV2) -> tuple[list[tuple[str, int, str, str, float]], int]:
    """(field, index, claim, cited, seconds) for every transcript citation,
    plus the count of frame and sheet cites."""
    from .view import strip_cites

    out: list[tuple[str, int, str, str, float]] = []
    frames = 0
    for i, km in enumerate(draft.key_moments):
        secs = _parse_ts(km.timestamp)
        if secs is not None:
            out.append(("key_moments", i, km.description, km.timestamp, secs))
    units: list[tuple[str, int, str]] = []
    for field in _LIST_FIELDS:
        units += [(field, i, s) for i, s in enumerate(getattr(draft, field) or [])]
    for field in _PROSE_FIELDS:
        text = getattr(draft, field) or ""
        units += [(field, i, s) for i, s in enumerate(_SENTENCE.split(text))]
    for field, i, text in units:
        frames += len(_FRAME_CITE.findall(text))
        claim = strip_cites(text)
        for m in _T_CITE.finditer(text):
            out.append((field, i, claim, f"t:{m.group(1)}", float(m.group(1))))
    return out, frames


def _idf(token_sets: list[set[str]]) -> dict[str, float]:
    df: dict[str, int] = {}
    for toks in token_sets:
        for t in toks:
            df[t] = df.get(t, 0) + 1
    n = len(token_sets)
    return {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}


def check_anchors(
    draft: EnrichmentV2,
    transcript: list[dict[str, Any]],
    *,
    window_s: float = ADJACENCY_WINDOW_S,
) -> AnchorReport:
    """Read each transcript citation's claim against the span it cites.
    moved: the cited span shares no content word with the claim and a span
    within window_s shares MIN_SHARED or more (IDF-weighted pick, so a name
    said in every line counts for little). unsupported: no span within the
    window shares MIN_SHARED. Pure: no I/O."""
    from .grader import content_tokens

    cites, frames = _citations(draft)
    if not transcript:
        return AnchorReport([], frames)
    windows = _windows(transcript)
    starts = [s for s, _ in windows]
    toks = [content_tokens(t) for _, t in windows]
    line_toks = [content_tokens(str(s.get("text", ""))) for s in transcript]
    idf = _idf(line_toks)

    def score(words: set[str], i: int) -> float:
        return sum(idf.get(w, 0.0) for w in words & toks[i])

    out: list[Anchor] = []
    for field, index, claim, cited, secs in cites:
        words = content_tokens(claim)
        at = max((i for i, s in enumerate(starts) if s <= secs + CITE_SLACK_S), default=0)
        near = [i for i, s in enumerate(starts) if abs(s - secs) <= window_s] or [at]
        best = max(near, key=lambda i: (score(words, i), -abs(starts[i] - secs)))
        cited_shared = len(words & toks[at])
        best_shared = len(words & toks[best])
        verdict, after = "ok", None
        if best_shared < MIN_SHARED:
            verdict = "unsupported"
        elif cited_shared == 0:
            # The best span is up to LINES_PER_WINDOW lines: land on the line
            # inside it that carries the most of the claim.
            span = [
                j
                for j in range(best, min(best + LINES_PER_WINDOW, len(transcript)))
                if starts[j] - starts[best] <= WINDOW_SPAN_S
            ]
            line = max(span, key=lambda j: (sum(idf.get(w, 0.0) for w in words & line_toks[j]), -j))
            new = starts[line]
            if abs(new - secs) >= MIN_MOVE_S:
                verdict = "moved"
                after = fmt_ts(new) if field == "key_moments" else f"t:{int(new)}"
        out.append(
            Anchor(
                field,
                index,
                claim,
                cited,
                secs,
                verdict,
                after,
                cited_shared,
                best_shared,
                score(words, at),
                score(words, best),
            )
        )
    return AnchorReport(out, frames)
