"""The enricher verb (#197 P4): packet + attempt -> draft note.

In: the view (#212, the same bytes the grader reads), the attempt record
(previous draft, findings in, the owner's take), the tag vocabulary, the
per-source bias. Never the rubric; the wall between writer and judge is the
design's core rule. Out: EnrichmentV2 (the legacy model plus evidence_gaps,
take_response, new_tags), persisted as a draft keyed by item+attempt so
re-runs are idempotent. One activity row per call with model, tokens,
duration_ms, view_hash and attempt.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from . import ledger
from .attempt import Attempt
from .enrich import (
    BASE_SKELETON,
    SOURCE_BIAS,
    Enrichment,
    KeyMoment,
    Recommendation,
    build_system,
    vocab_block,
)
from .evidence import evidence_dir
from .view import View

ENRICHER_MODEL = "claude-sonnet-5"


class NewTag(BaseModel):
    tag: str
    reason: str


class EnrichmentV2(Enrichment):
    """The legacy model plus the P4 contract fields."""

    evidence_gaps: list[str] = []
    take_response: str | None = None
    new_tags: list[NewTag] = []
    # Handle-titled sources (Instagram, TikTok, Pinterest) need a title the
    # thesis already implies; drafted here so it costs no extra call.
    title: str | None = None


SCHEMA_V2 = EnrichmentV2.model_json_schema()

_V2_ADDENDUM = """\

The packet
  Everything below the role text is the packet: the record you write from. It \
names its units (t:<seconds> for a transcript line, frame:NNN for a frame, sheet \
for the contact sheet) and says what is not in it. A key concept read off a frame \
and not spoken ends with the unit it was read from in brackets, e.g. \
"GaussianSplat node: the TOP that renders the splats [frame:002]"; cite only units \
the packet lists. Nothing outside the packet can be cited.

title
  At most 8 words naming the concrete subject: the tool, technique, artwork or \
claim. Keep proper nouns. No trailing period, no quotes. Never the author's handle.

evidence_gaps
  What could not be seen, copied or refined from the capture status: failed frames, \
missing transcript, truncated text. Empty list when nothing was missing. Never paper \
over a gap with confident prose.

take_response
  The owner saved this with a sentence of their own (given in the attempt header when \
present). Answer it directly in one paragraph: agree and add something, push back, or \
name what their reason misses. If they asked a question, answer it. When no take is \
given, set null; never fake one.

new_tags
  For every interest_tag NOT in the provided vocabulary, one entry naming the tag and \
one sentence on why no existing tag fits. Tags in the vocabulary need no entry.\
"""

# The version names the whole role text the writer reads: the field guide in
# enrich.py as well as the addendum, so an edit to either shows on the row.
PROMPT_VERSION = hashlib.sha256((BASE_SKELETON + _V2_ADDENDUM).encode()).hexdigest()[:12]


class EnrichmentPatch(BaseModel):
    """What a retry returns: only the fields it changed. Everything absent
    is copied from the previous draft in code, so an unnamed field cannot
    regress on a retry (2026-09-06: blind full rewrites traded one error
    for a fresh one every round, 0 of 6 grades passed)."""

    thesis: str | None = None
    summary: str | None = None
    key_concepts: list[str] | None = None
    insights: list[str] | None = None
    interest_tags: list[str] | None = None
    key_moments: list[KeyMoment] | None = None
    recommendations: list[Recommendation] | None = None
    evidence_gaps: list[str] | None = None
    take_response: str | None = None
    new_tags: list[NewTag] | None = None
    title: str | None = None


SCHEMA_PATCH = EnrichmentPatch.model_json_schema()

_PATCH_ADDENDUM = """\

This is a RETRY. The attempt header carries your previous draft and the findings \
requested. Return ONLY the fields you change, each complete as it should now read; \
omit every field you keep. Fix exactly what the findings name, against the packet.\
"""

PATCH_PROMPT_VERSION = hashlib.sha256(
    (BASE_SKELETON + _V2_ADDENDUM + _PATCH_ADDENDUM).encode()
).hexdigest()[:12]

_PROSE_FIELDS = ("thesis", "summary", "take_response", "title")


def _unwrap_prose(field: str, value: str, fallback: str | None) -> str | None:
    """A prose field that arrives as a JSON object (item 761: the patch put
    {"summary": ..., "insights": [...]} into `summary`) yields its own key
    when present, else the previous value. Never a blob in the note."""
    text = value.strip()
    if not text.startswith("{"):
        return value
    try:
        parsed: object = json.loads(text)
    except ValueError:
        return fallback
    if isinstance(parsed, dict):
        inner = cast("dict[str, object]", parsed).get(field)
        if isinstance(inner, str) and inner.strip() and not inner.strip().startswith("{"):
            return inner
    return fallback


def merge_patch(previous: EnrichmentV2, patch: EnrichmentPatch) -> EnrichmentV2:
    changes = patch.model_dump(exclude_none=True)
    prev = previous.model_dump()
    for field in _PROSE_FIELDS:
        if field in changes and isinstance(changes[field], str):
            fixed = _unwrap_prose(field, changes[field], prev.get(field))
            if fixed is None:
                del changes[field]
            else:
                changes[field] = fixed
    return EnrichmentV2.model_validate({**prev, **changes})


@dataclass
class EnrichResult:
    draft: EnrichmentV2
    draft_path: Path


def draft_path(item_id: int, attempt: int) -> Path:
    return evidence_dir() / "drafts" / f"{item_id}-{attempt}.json"


def _bias_source(view: View) -> str:
    """Map a view to the closest SOURCE_BIAS key. Instagram video captures
    carry a whisper transcript; carousels do not. Pinterest reads like a
    caption+image post."""
    if view.source == "instagram":
        return "instagram_reel" if view.transcript_origin == "whisper" else "instagram"
    if view.source == "pinterest":
        return "instagram"
    return view.source if view.source in SOURCE_BIAS else "web"


def build_prompt(view: View, attempt: Attempt) -> str:
    """Packet, then the attempt header, then the vocabulary. The packet bytes
    are the same ones the grader receives (pinned by test)."""
    return "\n\n".join(p for p in (view.rendered, attempt.rendered(), vocab_block().strip()) if p)


def enrich_item(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    view: View,
    attempt: Attempt,
    actor: str = "enricher",
) -> EnrichResult:
    """Run one enrichment attempt and record it. The draft lands on disk
    before the activity row references it. With a previous draft and
    findings on the attempt the call is a patch: the model returns only what
    it changes."""
    from . import sdk  # deferred: claude_agent_sdk costs ~120ms (#146)
    from .moments import snap_key_moments

    patching = attempt.previous_draft is not None and bool(attempt.findings_in)
    system = build_system(_bias_source(view)) + _V2_ADDENDUM
    if patching:
        system += _PATCH_ADDENDUM
    user = build_prompt(view, attempt)
    schema = SCHEMA_PATCH if patching else SCHEMA_V2

    res = sdk.call_structured(system, user, schema, add_dirs=view.mounts, model=ENRICHER_MODEL)
    if patching:
        assert attempt.previous_draft is not None
        previous = EnrichmentV2.model_validate(attempt.previous_draft)
        draft = merge_patch(previous, EnrichmentPatch.model_validate(res.data))
    else:
        draft = EnrichmentV2.model_validate(res.data)
    draft, moves = snap_key_moments(draft, view.transcript)

    out = draft_path(item_id, attempt.n)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(draft.model_dump_json(indent=1))

    inputs: dict[str, Any] = {
        "evidence_hash": view.bundle_hash,
        "view_hash": view.view_hash,
        "attempt": attempt.n,
        "take_id": attempt.take.get("id") if attempt.take else None,
        "prompt_version": PATCH_PROMPT_VERSION if patching else PROMPT_VERSION,
        "mode": "patch" if patching else "draft",
        "snapped": [f"{m.before}->{m.after}" for m in moves],
    }
    ledger.insert_activity(
        conn,
        item_id,
        actor=actor,
        action="enrich",
        from_state=ledger.item_state(conn, item_id),
        to_state=None,
        inputs=json.dumps(inputs),
        output_ref=str(out),
        model=res.model,
        tokens=res.tokens,
        duration_ms=res.duration_ms,
        reason=f"attempt {attempt.n}"
        + (" (patch)" if patching else "")
        + (f", snapped {len(moves)}" if moves else ""),
        detail=json.dumps({"usage": res.usage}) if res.usage else None,
    )
    return EnrichResult(draft=draft, draft_path=out)
