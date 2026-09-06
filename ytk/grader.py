"""The grader (#197 P4): judges drafts, never shares a prompt with the
enricher.

Layer one, this file's deterministic_checks: code only, runs on every
draft, spends no model call, bounces with the failing check named. Layer
two (grade_model, below) runs only after layer one passes: Opus reads the
rubric, the draft and the evidence, and spot-checks summary claims.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from .sdk import StructuredResult

from .enrich import fmt_ts
from .enricher import ENRICH_MAX_FRAMES, EnrichmentV2
from .evidence import EvidenceBundle

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


def _tokens(text: str) -> set[str]:
    # Hyphens split before matching (#201): "Empirical-field framing" must
    # meet the transcript's "empirical field" — a near-verbatim coinage is
    # not a hallucination. Applies to both sides, so evidence hyphens also
    # ground unhyphenated draft phrasing.
    return {w for w in _WORD.findall(_fold(text).lower().replace("-", " ")) if w not in _STOP}


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


def _moment_checks(draft: EnrichmentV2, bundle: EvidenceBundle) -> list[Bounce]:
    if not bundle.transcript or not bundle.duration:
        return []
    out: list[Bounce] = []
    for km in draft.key_moments:
        secs = _parse_ts(km.timestamp)
        if secs is None or secs > bundle.duration:
            out.append(
                Bounce(
                    check="key moment timestamp",
                    detail=f"{km.timestamp} outside 0..{int(bundle.duration)}s",
                    where=km.description[:80],
                )
            )
            continue
        window = " ".join(
            str(s.get("text", ""))
            for s in bundle.transcript
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


def _evidence_text(bundle: EvidenceBundle) -> str:
    transcript = " ".join(str(s.get("text", "")) for s in bundle.transcript)
    return " ".join(
        t for t in (transcript, bundle.description, bundle.caption, bundle.text, bundle.title) if t
    )


def _concept_checks(draft: EnrichmentV2, bundle: EvidenceBundle) -> list[Bounce]:
    out: list[Bounce] = []
    if len(draft.key_concepts) < MIN_CONCEPTS:
        out.append(
            Bounce(
                check="concept count",
                detail=f"{len(draft.key_concepts)} concepts; floor is {MIN_CONCEPTS}",
            )
        )
    evidence_tokens = _tokens(_evidence_text(bundle))
    for concept in draft.key_concepts:
        name = concept.split(":", 1)[0]
        name_tokens = _tokens(name)
        if name_tokens and not (name_tokens & evidence_tokens):
            out.append(
                Bounce(
                    check="concept grounding",
                    detail=f"'{name.strip()}' not findable in transcript or description",
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
    bundle: EvidenceBundle,
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
    out += _moment_checks(draft, bundle)
    out += _concept_checks(draft, bundle)
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

Always spot-check three claims from the summary against the evidence
(fewer only if the summary has fewer claims). A claim you cannot locate in
the evidence is grounded=false and MUST also produce a bounce with
check="grounding", passed=false.

The owner's rubric:

{rubric}
"""

GRADER_PROMPT_VERSION = hashlib.sha256(_GRADE_SYSTEM.encode()).hexdigest()[:12]

# Evidence cap for the grading prompt. 80k cut a two-hour lecture at 1:08
# and the grader bounced the whole back half as ungrounded (item 215,
# 2026-09-06); the enricher had read all of it. 400k chars is about 100k
# tokens, inside the judge's window; past it the cut is announced.
_EVIDENCE_CAP = 400_000
_TRUNCATION_NOTE = (
    "\n\n[Evidence cut at {cap} characters. Claims about content after this point cannot be "
    "checked here: do not bounce them as ungrounded, and skip them in spot-checks.]"
)


def _render_evidence(bundle: EvidenceBundle) -> str:
    parts: list[str] = [f"Title: {bundle.title or ''}"]
    if bundle.description:
        parts.append(f"Description:\n{bundle.description}")
    if bundle.caption:
        parts.append(f"Caption:\n{bundle.caption}")
    if bundle.text:
        parts.append(f"Body:\n{bundle.text}")
    if bundle.transcript:
        # Timestamped like the enricher's view: the rubric's key-moment rule
        # ("sit next to matching transcript text") is unjudgeable without them.
        lines = "\n".join(
            f"[{fmt_ts(float(s.get('start', 0)))}] {s.get('text', '')}" for s in bundle.transcript
        )
        parts.append(f"Transcript:\n{lines}")
    if bundle.gaps:
        parts.append("Not seen at capture:\n" + "\n".join(f"- {g}" for g in bundle.gaps))
    text = "\n\n".join(parts)
    if len(text) > _EVIDENCE_CAP:
        return text[:_EVIDENCE_CAP] + _TRUNCATION_NOTE.format(cap=_EVIDENCE_CAP)
    return text


def grade_model(
    draft: EnrichmentV2,
    bundle: EvidenceBundle,
    rubric_text: str,
    *,
    take_text: str | None,
) -> tuple[ModelVerdict, StructuredResult]:
    """One Opus call: rubric + draft + evidence in, verdict out. Returns the
    verdict and the StructuredResult so the caller's activity row carries
    the usage fields."""
    from . import sdk  # deferred: claude_agent_sdk costs ~120ms (#146)

    system = _GRADE_SYSTEM.format(rubric=rubric_text)
    take_block = (
        f"The owner's take, which the draft must answer:\n{take_text}\n\n" if take_text else ""
    )
    user = (
        f"{take_block}The draft note:\n{draft.model_dump_json(indent=1)}\n\n"
        f"The evidence it was written from:\n{_render_evidence(bundle)}"
    )
    # The judge sees the same capped frames the writer saw (item 756: the
    # grader bounced visually-grounded claims it was never shown).
    frame_paths = [f for f in bundle.frames if Path(f).exists()][:ENRICH_MAX_FRAMES]
    add_dirs: list[str] = []
    if frame_paths:
        user += "\n\nExtracted frames:\n" + "\n".join(f"  {f}" for f in frame_paths)
        add_dirs = sorted({str(Path(f).parent) for f in frame_paths})
    res = sdk.call_structured(
        system, user, ModelVerdict.model_json_schema(), add_dirs=add_dirs, model=GRADER_MODEL
    )
    return ModelVerdict.model_validate(res.data), res
