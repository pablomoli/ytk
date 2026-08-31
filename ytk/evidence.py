"""The read verb (#197 P2): item -> evidence bundle; the quality gate may
raise an ask. Nothing is written to the corpus.

The bundle is what the enricher will see (P4). Quality flags ride with the
transcript instead of being computed and discarded, so the deterministic
gate can raise the spec's "transcript junk" and "blind item" asks without a
model call.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import asks, ledger

VISUAL_SOURCES = {"instagram", "tiktok", "pinterest"}

# Repetition fraction above which auto-captions are treated as garble. A
# stated guess (spec, Asks); re-sized once the asks table measures real
# bounce answers.
GARBLE_THRESHOLD = 0.5

# Chrome that trafilatura leaves behind on some sites (#167). Line-level and
# deterministic on purpose; the SAE fingerprint hunt is a separate rung.
BOILERPLATE = re.compile(
    r"cookie|newsletter|subscribe|sign in|log in|accept all|advertisement|share this",
    re.IGNORECASE,
)


@dataclass
class EvidenceBundle:
    source: str
    url: str
    title: str | None
    transcript: list[dict[str, Any]]
    transcript_origin: str  # api-manual | api-auto | whisper | none
    transcript_language: str | None
    transcript_status: str  # ok | no_speech | failed | none
    description: str | None = None
    caption: str | None = None  # instagram (#182)
    text: str | None = None  # web article body, boilerplate-stripped
    frames: list[str] = field(default_factory=list[str])  # file paths
    gaps: list[str] = field(default_factory=list[str])  # what could not be seen
    # P4 additions, all defaulted: P2-era bundles on disk lack them, and the
    # consumers (timestamp check, note writer) must skip rather than crash.
    media_id: str | None = None  # platform id (YouTube video id)
    uploader: str | None = None
    upload_date: str | None = None  # YYYYMMDD
    duration: float | None = None  # seconds
    thumbnail: str | None = None
    chapters: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])


def load_bundle(path: Path) -> EvidenceBundle:
    """Reload a bundle written by read_item. Unknown keys are dropped and
    missing ones default, so bundles written before a field existed load."""
    from dataclasses import fields

    raw = json.loads(Path(path).read_text())
    known = {f.name for f in fields(EvidenceBundle)}
    return EvidenceBundle(**{k: v for k, v in raw.items() if k in known})


@dataclass
class ReadResult:
    bundle_path: Path | None
    ask_id: int | None
    error: str | None = None


def garble_score(segments: list[dict[str, Any]]) -> float:
    """Fraction of lines that repeat an earlier line. Auto-caption garbage
    ("[Music]", stuck phrases) repeats; real speech does not."""
    lines = [
        str(s.get("text", "")).strip().lower() for s in segments if str(s.get("text", "")).strip()
    ]
    if not lines:
        return 0.0
    seen: set[str] = set()
    repeats = 0
    for line in lines:
        if line in seen:
            repeats += 1
        seen.add(line)
    return repeats / len(lines)


def strip_boilerplate(text: str) -> tuple[str, list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    for line in text.splitlines():
        (dropped if BOILERPLATE.search(line) else kept).append(line)
    return "\n".join(kept), dropped


def quality_asks(bundle: EvidenceBundle) -> list[dict[str, Any]]:
    """Deterministic gate. At most one ask, quality order per the spec:
    a garbled/missing transcript outranks blindness, except that a silent
    visual item with no frames is blind, not junk."""
    has_transcript = bool(bundle.transcript)
    if bundle.source in VISUAL_SOURCES and not has_transcript and not bundle.frames:
        return [
            {
                "kind": "blind item",
                "why": "visual source with no frames and no transcript",
                "options": ["retry frames", "proceed text-only", "drop"],
            }
        ]
    if bundle.source == "web":
        return []  # articles carry text, not speech
    junk_why = None
    if not has_transcript:
        if bundle.transcript_status == "no_speech":
            junk_why = "whisper heard no speech"
        else:
            junk_why = "no captions and no transcript"
    elif bundle.transcript_language and bundle.transcript_language != "en":
        junk_why = f"language is {bundle.transcript_language}, not en"
    elif (
        bundle.transcript_origin == "api-auto"
        and garble_score(bundle.transcript) > GARBLE_THRESHOLD
    ):
        junk_why = f"auto-captions garbled (repetition {garble_score(bundle.transcript):.0%})"
    if junk_why:
        return [
            {
                "kind": "transcript junk",
                "why": junk_why,
                "options": ["retry with Whisper", "keep with the warning", "drop"],
            }
        ]
    return []


def evidence_dir() -> Path:
    env = os.environ.get("YTK_EVIDENCE")
    return Path(env) if env else Path.home() / ".ytk" / "evidence"


# source -> callable(url, title) -> EvidenceBundle. Real gatherers do network
# work; tests and callers substitute per source.
GATHERERS: dict[str, Callable[[str, str | None], EvidenceBundle]] = {}


def read_item(conn: sqlite3.Connection, item_id: int, *, actor: str = "loop") -> ReadResult:
    """Gather evidence for one captured item. On gate failure the item moves
    to asking with one ask row; on gatherer failure the attempt is recorded
    with no transition so a retry can re-run it."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    gatherer = GATHERERS.get(row["source"])
    if gatherer is None:
        return ReadResult(bundle_path=None, ask_id=None, error=f"no gatherer for {row['source']}")
    try:
        bundle = gatherer(row["url"], row["title"])
    except Exception as exc:
        ledger.insert_activity(
            conn,
            item_id,
            actor=actor,
            action="read",
            to_state=None,
            reason=f"read failed: {exc}",
        )
        return ReadResult(bundle_path=None, ask_id=None, error=str(exc))
    out = evidence_dir() / f"{item_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(bundle), indent=1))
    conn.execute("UPDATE items SET payload_ref = ? WHERE id = ?", (str(out), item_id))
    if bundle.title and not row["title"]:
        # #200: Add-box captures arrive titleless; the ask card must not
        # show a raw URL.
        conn.execute("UPDATE items SET title = ? WHERE id = ?", (bundle.title, item_id))
    ledger.insert_activity(
        conn,
        item_id,
        actor=actor,
        action="read",
        from_state=ledger.item_state(conn, item_id),
        to_state="read",
        output_ref=str(out),
    )
    quality = quality_asks(bundle)
    if quality:
        ask_id = asks.raise_ask(conn, item_id, proposal=quality[0], actor=actor)
        return ReadResult(bundle_path=out, ask_id=ask_id)
    # Quality passed; intent comes second (spec order). No take, no note.
    ask_id = asks.raise_intent_ask(conn, item_id, actor=actor)
    return ReadResult(bundle_path=out, ask_id=ask_id)


def retry_parked(conn: sqlite3.Connection, item_id: int, *, actor: str = "sweep") -> bool:
    """Re-run the deterministic gate on a parked item (#197 P5 sweep).

    Auto-captions arrive days after upload and frame extraction recovers, so
    a re-gather can clear what parked the item. A pass writes the fresh
    bundle, retires the stale quality ask, and returns the item to read with
    no new ask (spec, Parked); a fail records the attempt and stays parked.
    """
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    gatherer = GATHERERS.get(row["source"])
    if gatherer is None:
        return False
    try:
        bundle = gatherer(row["url"], row["title"])
    except Exception as exc:
        ledger.insert_activity(
            conn, item_id, actor=actor, action="retry-read", reason=f"retry failed: {exc}"
        )
        return False
    if quality_asks(bundle):
        ledger.insert_activity(
            conn, item_id, actor=actor, action="retry-read", reason="gate still failing"
        )
        return False
    out = evidence_dir() / f"{item_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(bundle), indent=1))
    conn.execute("UPDATE items SET payload_ref = ? WHERE id = ?", (str(out), item_id))
    conn.execute(
        """
        UPDATE outbox SET answered_at = ? WHERE answered_at IS NULL AND ask_id IN
            (SELECT id FROM asks WHERE item_id = ?)
        """,
        (ledger.now(), item_id),
    )
    ledger.insert_activity(
        conn,
        item_id,
        actor=actor,
        action="read",
        from_state=ledger.item_state(conn, item_id),
        to_state="read",
        output_ref=str(out),
        reason="retry gate passed",
    )
    # Quality cleared; the funnel continues in spec order — a takeless item
    # still owes the owner its "why this one?".
    asks.raise_intent_ask(conn, item_id, actor=actor)
    return True
