"""The enricher verb (#197 P4): evidence bundle + owner's take -> draft note.

In: the bundle from `read`, the take (kind and text), the tag vocabulary,
the per-source bias. Never the rubric — the wall between writer and judge
is the design's core rule. Out: EnrichmentV2 (the legacy model plus
evidence_gaps, take_response, new_tags), persisted as a draft keyed by
item+attempt so re-runs are idempotent. One activity row per call with
model, tokens, duration_ms.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from . import ledger
from .enrich import (
    SOURCE_BIAS,
    Enrichment,
    KeyMoment,
    Recommendation,
    build_system,
    description_block,
    fmt_ts,
    vocab_block,
)
from .evidence import EvidenceBundle, evidence_dir, load_bundle

ENRICHER_MODEL = "claude-sonnet-5"

# Frames shown to the model per enrich call. Measured 2026-08-31 (item 756,
# four ~60KB reel frames): 4 frames fail structured output 5-attempts-deep,
# 3/3 reproductions; 2 and 1 succeed. The bundle keeps every frame — the
# note embeds them all; only the model call is capped.
ENRICH_MAX_FRAMES = 2


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

title
  At most 8 words naming the concrete subject: the tool, technique, artwork or \
claim. Keep proper nouns. No trailing period, no quotes. Never the author's handle.

evidence_gaps
  What could not be seen, copied or refined from the capture status: failed frames, \
missing transcript, truncated text. Empty list when nothing was missing. Never paper \
over a gap with confident prose.

take_response
  The owner saved this with a sentence of their own (given below when present). Answer \
it directly in one paragraph: agree and add something, push back, or name what their \
reason misses. If they asked a question, answer it. When no take is given, set null — \
never fake one.

new_tags
  For every interest_tag NOT in the provided vocabulary, one entry naming the tag and \
one sentence on why no existing tag fits. Tags in the vocabulary need no entry.\
"""

_TAKE_BLOCK = """
The owner's take (kind: {kind}). This sentence is the reason the item is in
the library; the response to it is the reason the note exists:
{text}
"""

_FEEDBACK_BLOCK = """
A previous draft was returned. Fix exactly what is named, keep what was not:
{items}
"""

PROMPT_VERSION = hashlib.sha256(
    (_V2_ADDENDUM + _TAKE_BLOCK + _FEEDBACK_BLOCK).encode()
).hexdigest()[:12]


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

This is a RETRY. Below is your previous draft and the grader's findings. Return \
ONLY the fields you change, each complete as it should now read; omit every field \
you keep. Fix exactly what the findings name. The evidence excerpts are the parts \
of the transcript around the timestamps in play; treat them as the record.\
"""

PATCH_PROMPT_VERSION = hashlib.sha256(
    (_V2_ADDENDUM + _PATCH_ADDENDUM + _TAKE_BLOCK).encode()
).hexdigest()[:12]

# Seconds of transcript shown either side of every timestamp a retry is about.
PATCH_WINDOW_S = 120.0
_TS_IN_TEXT = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b")


def _cited_seconds(texts: list[str]) -> set[float]:
    out: set[float] = set()
    for t in texts:
        for m in _TS_IN_TEXT.findall(t):
            parts = [int(x) for x in m.split(":")]
            out.add(float(sum(n * 60**i for i, n in enumerate(reversed(parts)))))
    return out


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


def build_patch_prompt(
    bundle: EvidenceBundle,
    previous: EnrichmentV2,
    feedback: list[str],
    take_kind: str | None,
    take_text: str | None,
) -> str:
    """Previous draft + findings + transcript windows around every cited
    timestamp (the findings' and the draft's own moments). The whole
    transcript only when nothing is cited."""
    cited = _cited_seconds(feedback + [m.timestamp for m in previous.key_moments])
    parts: list[str] = [f"Title: {bundle.title or ''}"]
    if bundle.duration:
        parts.append(f"Duration: {int(bundle.duration)}s")
    if bundle.description:
        parts.append(description_block(bundle.description).strip())
    if bundle.caption:
        parts.append(f"Caption:\n{bundle.caption}")
    if bundle.transcript and cited:
        keep = [
            s
            for s in bundle.transcript
            if any(abs(float(s.get("start", 0)) - c) <= PATCH_WINDOW_S for c in cited)
        ]
        lines = "\n".join(f"[{fmt_ts(float(s.get('start', 0)))}] {s.get('text', '')}" for s in keep)
        parts.append(
            f"Evidence excerpts (transcript, {len(keep)} of {len(bundle.transcript)} lines):\n{lines}"
        )
    else:
        parts.append(_transcript_block(bundle))
    if take_text:
        parts.append(_TAKE_BLOCK.format(kind=take_kind or "intent", text=take_text).strip())
    parts.append("Previous draft:\n" + previous.model_dump_json(indent=1))
    parts.append("Grader findings:\n" + "\n".join(f"- {f}" for f in feedback))
    parts.append(vocab_block().strip())
    return "\n\n".join(parts)


@dataclass
class EnrichResult:
    draft: EnrichmentV2
    draft_path: Path


def draft_path(item_id: int, attempt: int) -> Path:
    return evidence_dir() / "drafts" / f"{item_id}-{attempt}.json"


def _bias_source(bundle: EvidenceBundle) -> str:
    """Map a bundle to the closest SOURCE_BIAS key. Instagram video captures
    carry a whisper transcript; carousels do not. Pinterest reads like a
    caption+image post."""
    if bundle.source == "instagram":
        return "instagram_reel" if bundle.transcript_origin == "whisper" else "instagram"
    if bundle.source == "pinterest":
        return "instagram"
    return bundle.source if bundle.source in SOURCE_BIAS else "web"


def _transcript_block(bundle: EvidenceBundle) -> str:
    if not bundle.transcript:
        return f"Transcript: (none — status {bundle.transcript_status})"
    lines = "\n".join(
        f"[{fmt_ts(float(s.get('start', 0)))}] {s.get('text', '')}" for s in bundle.transcript
    )
    return f"Transcript (origin {bundle.transcript_origin}):\n{lines}"


def build_user_prompt(
    bundle: EvidenceBundle,
    take_kind: str | None,
    take_text: str | None,
    feedback: list[str] | None = None,
) -> str:
    parts: list[str] = [f"Title: {bundle.title or ''}"]
    if bundle.uploader:
        parts.append(f"Uploader: {bundle.uploader}")
    if bundle.duration:
        parts.append(f"Duration: {int(bundle.duration)}s")
    if bundle.chapters:
        rows = "\n".join(
            f"  {fmt_ts(float(c.get('start_time') or 0))} — {c.get('title', '')}"
            for c in bundle.chapters
        )
        parts.append(f"Chapters:\n{rows}")
    if bundle.description:
        parts.append(description_block(bundle.description).strip())
    if bundle.caption:
        parts.append(f"Caption:\n{bundle.caption}")
    if bundle.text:
        parts.append(f"Body:\n{bundle.text}")
    parts.append(_transcript_block(bundle))
    if bundle.gaps:
        parts.append("Capture status — not seen:\n" + "\n".join(f"- {g}" for g in bundle.gaps))
    if take_text:
        parts.append(_TAKE_BLOCK.format(kind=take_kind or "intent", text=take_text).strip())
    if feedback:
        parts.append(_FEEDBACK_BLOCK.format(items="\n".join(f"- {f}" for f in feedback)).strip())
    parts.append(vocab_block().strip())
    return "\n\n".join(p for p in parts if p)


def _latest_take(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM takes WHERE item_id = ? ORDER BY id DESC LIMIT 1", (item_id,)
    ).fetchone()


def enrich_item(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    attempt: int,
    feedback: list[str] | None = None,
    previous: EnrichmentV2 | None = None,
    actor: str = "enricher",
) -> EnrichResult:
    """Run one enrichment attempt and record it. The draft lands on disk
    before the activity row references it. With `previous` and `feedback`
    the call is a patch: the model returns only what it changes."""
    from . import sdk  # deferred: claude_agent_sdk costs ~120ms (#146)
    from .moments import snap_key_moments

    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    bundle_path = Path(row["payload_ref"])
    bundle = load_bundle(bundle_path)
    take = _latest_take(conn, item_id)
    take_kind = take["kind"] if take else None
    take_text = take["text"] if take else None

    patching = previous is not None and bool(feedback)
    if patching:
        assert previous is not None and feedback is not None
        system = build_system(_bias_source(bundle)) + _V2_ADDENDUM + _PATCH_ADDENDUM
        user = build_patch_prompt(bundle, previous, feedback, take_kind, take_text)
        schema = SCHEMA_PATCH
    else:
        system = build_system(_bias_source(bundle)) + _V2_ADDENDUM
        user = build_user_prompt(bundle, take_kind, take_text, feedback)
        schema = SCHEMA_V2
    frame_paths = [p for p in bundle.frames if Path(p).exists()][:ENRICH_MAX_FRAMES]
    if frame_paths:
        user += "\n\nExtracted frames:\n" + "\n".join(f"  {p}" for p in frame_paths)
    add_dirs = sorted({str(Path(p).parent) for p in frame_paths})

    res = sdk.call_structured(system, user, schema, add_dirs=add_dirs, model=ENRICHER_MODEL)
    if patching:
        assert previous is not None
        draft = merge_patch(previous, EnrichmentPatch.model_validate(res.data))
    else:
        draft = EnrichmentV2.model_validate(res.data)
    draft, moves = snap_key_moments(draft, bundle.transcript)

    out = draft_path(item_id, attempt)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(draft.model_dump_json(indent=1))

    inputs: dict[str, Any] = {
        "evidence_hash": hashlib.sha256(bundle_path.read_bytes()).hexdigest()[:12],
        "take_id": take["id"] if take else None,
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
        reason=f"attempt {attempt}"
        + (" (patch)" if patching else " (after bounce)" if feedback else "")
        + (f", snapped {len(moves)}" if moves else ""),
        detail=json.dumps({"usage": res.usage}) if res.usage else None,
    )
    return EnrichResult(draft=draft, draft_path=out)
