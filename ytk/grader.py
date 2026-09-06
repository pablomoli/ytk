"""The grader (#197 P4): judges drafts, never shares a prompt with the
enricher.

Layer one, this file's deterministic_checks: code only, runs on every
draft, spends no model call, bounces with the failing check named. It reads
the view's grounding_text and unit ids and nothing else (#212). Layer two
(grade_model, below) runs only after layer one passes: Opus reads the
rubric, the draft, the same packet the writer read, and the attempt header
that says what it asked for last round.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from .sdk import StructuredResult

from .attempt import Attempt
from .enricher import EnrichmentV2
from .view import View, split_cites

# From the rubric's "What I do not want", frozen into code so the check is
# deterministic; the model layer reads the live rubric for everything else.
BANNED_WORDS = ("explores", "delves", "dives into", "journey", "landscape")
BANNED_OPENINGS = ("the video", "in this", "this talk")

# Adjacency window around a key moment's timestamp. Auto-caption starts
# drift a few seconds; a minute-and-a-half catches restated points too.
ADJACENCY_WINDOW_S = 90.0

# Concept floor per media length; a stated guess (like GARBLE_THRESHOLD),
# re-sized once bounce answers measure where the owner disagrees.
MIN_CONCEPTS = 1

# Near-duplicate ceiling on cosine similarity to the closest corpus doc.
# Measured 2026-08-31 over the live ytk_videos collection, 442 representative
# vectors: nearest-neighbor similarity p50 0.560, p99 0.839, max 0.851 (two
# distinct videos on one topic). 0.90 clears every distinct pair in the
# corpus; only a re-capture or rewrite of the same content trips it.
NEAR_DUP_BASELINE = 0.90


class Bounce(BaseModel):
    check: str  # deterministic check name, or the rubric item (model layer)
    detail: str
    where: str | None = None


_WORD = re.compile(r"[a-z0-9][a-z0-9'-]{3,}")
_STOP = frozenset(
    [
        "this",
        "that",
        "with",
        "from",
        "have",
        "they",
        "were",
        "been",
        "what",
        "when",
        "your",
        "there",
        "their",
        "will",
        "would",
        "could",
        "should",
        "about",
        "into",
        "over",
        "under",
        "very",
        "just",
        "like",
        "also",
    ]
)


def _fold(text: str) -> str:
    """Accents off before the ASCII word regex sees the text: Whisper writes
    "omertà", the draft writes "omerta", and the word regex would otherwise
    cut the accented form to "omert" (item 758)."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


# Longest first; a stem keeps at least four characters so short words are
# left whole. Item 212 (2026-09-06): "inheritance" in the draft bounced
# against "inherits" in the transcript, two Sonnet calls for a suffix.
_SUFFIXES = (
    "ations",
    "ation",
    "ances",
    "ance",
    "ences",
    "ence",
    "ments",
    "ment",
    "ings",
    "ing",
    "ers",
    "ies",
    "ed",
    "er",
    "es",
    "ly",
    "s",
)


def _stem(word: str) -> str:
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 4:
            return word[: -len(suf)]
    return word


def _tokens(text: str) -> set[str]:
    # Hyphens split before matching (#201): "Empirical-field framing" must
    # meet the transcript's "empirical field" — a near-verbatim coinage is
    # not a hallucination. Applies to both sides, so evidence hyphens also
    # ground unhyphenated draft phrasing. Suffixes come off both sides too.
    return {
        _stem(w) for w in _WORD.findall(_fold(text).lower().replace("-", " ")) if w not in _STOP
    }


# Public name for cross-module callers (the moment snap in moments.py).
content_tokens = _tokens


def _parse_ts(ts: str) -> float | None:
    parts = ts.strip().split(":")
    if not all(p.strip().isdigit() for p in parts) or not 2 <= len(parts) <= 3:
        return None
    nums = [int(p) for p in parts]
    return float(sum(n * 60**i for i, n in enumerate(reversed(nums))))


def _banned_phrasing(draft: EnrichmentV2) -> list[Bounce]:
    out: list[Bounce] = []
    for field in ("thesis", "summary"):
        text = getattr(draft, field)
        lowered = text.lower()
        hits = [w for w in BANNED_WORDS if w in lowered]
        if any(lowered.startswith(o) for o in BANNED_OPENINGS):
            hits.append("opening")
        if hits:
            out.append(Bounce(check="banned phrasing", detail=", ".join(hits), where=field))
    return out


def _moment_checks(draft: EnrichmentV2, view: View) -> list[Bounce]:
    if not view.transcript or not view.duration:
        return []
    span = view.transcript_span()
    out: list[Bounce] = []
    for km in draft.key_moments:
        secs = _parse_ts(km.timestamp)
        if secs is None or secs > view.duration:
            out.append(
                Bounce(
                    check="key moment timestamp",
                    detail=f"{km.timestamp} outside 0..{int(view.duration)}s",
                    where=km.description[:80],
                )
            )
            continue
        if span is not None and secs > span[1] + ADJACENCY_WINDOW_S:
            # Past the cut: not in the packet, so unverifiable here, and the
            # writer was told not to cite it.
            out.append(
                Bounce(
                    check="cites outside the packet",
                    detail=f"t:{int(secs)} is past the shown transcript (ends t:{int(span[1])})",
                    where=km.description[:80],
                )
            )
            continue
        window = " ".join(
            str(s.get("text", ""))
            for s in view.transcript
            if abs(float(s.get("start", 0)) - secs) <= ADJACENCY_WINDOW_S
        )
        if not (_tokens(km.description) & _tokens(window)):
            out.append(
                Bounce(
                    check="key moment adjacency",
                    detail=f"no transcript match near {km.timestamp}",
                    where=km.description[:80],
                )
            )
    return out


def _concept_checks(draft: EnrichmentV2, view: View) -> list[Bounce]:
    out: list[Bounce] = []
    if len(draft.key_concepts) < MIN_CONCEPTS:
        out.append(
            Bounce(
                check="concept count",
                detail=f"{len(draft.key_concepts)} concepts; floor is {MIN_CONCEPTS}",
            )
        )
    evidence_tokens = _tokens(view.grounding_text)
    for concept in draft.key_concepts:
        text, cites = split_cites(concept)
        name = text.split(":", 1)[0]
        unknown = [c for c in cites if not view.has_unit(c)]
        if unknown:
            out.append(
                Bounce(
                    check="cites unknown unit",
                    detail=f"'{name.strip()}' cites {', '.join(unknown)}, not in the packet",
                )
            )
            continue
        if any(c.startswith("frame:") or c == "sheet" for c in cites):
            # Read off a frame: the spell-checker cannot see it, the teacher
            # opens it. Never ungrounded here.
            continue
        name_tokens = _tokens(name)
        if name_tokens and not (name_tokens & evidence_tokens):
            out.append(
                Bounce(
                    check="concept grounding",
                    detail=f"'{name.strip()}' not findable in the packet",
                )
            )
    return out


def _tag_checks(draft: EnrichmentV2, vocab: list[str]) -> list[Bounce]:
    known = set(vocab)
    reasons = {t.tag for t in draft.new_tags if t.reason.strip()}
    missing = [
        t
        for t in draft.interest_tags
        # {kind}-rec tags are derived in code from recommendations, not chosen
        if t not in known and t not in reasons and not t.endswith("-rec")
    ]
    if missing:
        return [
            Bounce(
                check="tag vocabulary",
                detail=f"not in vocabulary and no reason given: {', '.join(missing)}",
            )
        ]
    return []


def deterministic_checks(
    draft: EnrichmentV2,
    view: View,
    *,
    vocab: list[str],
    take_kind: str | None,
    take_text: str | None,
    neighbor_cosine: float | None = None,
) -> list[Bounce]:
    """Every check, every draft, no model call. An empty list is a pass.
    neighbor_cosine is the caller-measured similarity to the closest corpus
    document (None skips the check — e.g. Chroma unavailable)."""
    out: list[Bounce] = []
    out += _banned_phrasing(draft)
    out += _moment_checks(draft, view)
    out += _concept_checks(draft, view)
    out += _tag_checks(draft, vocab)
    if neighbor_cosine is not None and neighbor_cosine > NEAR_DUP_BASELINE:
        out.append(
            Bounce(
                check="near duplicate",
                detail=f"cosine {neighbor_cosine:.3f} above baseline {NEAR_DUP_BASELINE}",
            )
        )
    if take_text and take_kind != "reflex" and not (draft.take_response or "").strip():
        out.append(
            Bounce(check="take response", detail="a take exists but the draft has no response")
        )
    return out


# --- model layer (Opus, after the deterministic layer passes) --------------

GRADER_MODEL = "claude-opus-5"


class SpotCheck(BaseModel):
    claim: str
    grounded: bool
    where: str  # where in the evidence it was (not) found


class ModelVerdict(BaseModel):
    passed: bool
    bounces: list[Bounce] = []
    spot_checks: list[SpotCheck] = []


_GRADE_SYSTEM = """\
You are the grader for a personal reference library. A separate writer drafted
the note below from the evidence; you judge the draft against the owner's
rubric and nothing else. You never rewrite the draft.

Return passed=true only when the draft holds up against every rubric section.
Walk every rubric section in order and return a bounce for EVERY section that
fails, all in this one verdict: check = the rubric section name, detail = what
fell short, where = the place in the draft. A verdict that names one failing
section while another also fails is a wrong verdict; the writer fixes what is
named and nothing else, so an unnamed failure costs a whole extra round. Quote
the rubric section exactly; a wrong bounce is fixed by the owner editing the
rubric, so the bounce must point at the words that produced it.

The packet is the whole record, and it is the same packet the writer read. It
names its units (t:<seconds>, frame:NNN, sheet) and says what is not in it.
Open every frame the packet shows before judging a claim about what is on
screen; a concept that cites a frame is checked against that frame. What the
packet says is not in it cannot be checked here: never bounce it as
ungrounded. When a finding rests on evidence, name the unit in `where`.

The attempt header lists the findings requested last round. Judge whether each
one was addressed. A change you asked for is not a new objection: do not
bounce this round for doing what last round's findings demanded.

Always spot-check three claims from the summary against the evidence
(fewer only if the summary has fewer claims). A claim you cannot locate in
the evidence is grounded=false and MUST also produce a bounce with
check="grounding", passed=false.

The owner's rubric:

{rubric}
"""

GRADER_PROMPT_VERSION = hashlib.sha256(_GRADE_SYSTEM.encode()).hexdigest()[:12]


def build_prompt(draft: EnrichmentV2, view: View, attempt: Attempt) -> str:
    """Packet, attempt header, then the draft. The packet bytes are the ones
    the writer received (pinned by test)."""
    return "\n\n".join(
        (view.rendered, attempt.rendered(), "The draft note:\n" + draft.model_dump_json(indent=1))
    )


def grade_model(
    draft: EnrichmentV2,
    view: View,
    attempt: Attempt,
    rubric_text: str,
) -> tuple[ModelVerdict, StructuredResult]:
    """One Opus call: rubric + packet + attempt + draft in, verdict out.
    Returns the verdict and the StructuredResult so the caller's activity
    row carries the usage fields."""
    from . import sdk  # deferred: claude_agent_sdk costs ~120ms (#146)

    system = _GRADE_SYSTEM.format(rubric=rubric_text)
    user = build_prompt(draft, view, attempt)
    res = sdk.call_structured(
        system, user, ModelVerdict.model_json_schema(), add_dirs=view.mounts, model=GRADER_MODEL
    )
    return ModelVerdict.model_validate(res.data), res
