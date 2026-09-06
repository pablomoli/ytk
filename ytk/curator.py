"""The advance function (#197 P4): answered/read-with-take -> kept.

One function the P5 loop can absorb whole; until then the acting surface
calls it (CLI synchronously, hub from its background job). Per advance:
up to two enrich+grade rounds; the second bounce raises the "grader
bounce, twice" ask through asks.raise_ask and the item waits. A pass
transitions to enriched (the grader alone suffices, per the lifecycle),
lands the note, and records kept.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from . import asks, grader, ledger, loop, rubric
from . import attempt as attempt_mod
from .enricher import EnrichmentV2, draft_path, enrich_item
from .evidence import load_bundle
from .view import View, ensure_view

# Rounds per advance call. "Grader bounce, twice" (spec, Asks) is the ask
# trigger; the owner's "say what is wrong" buys exactly one more round.
MAX_ROUNDS = 2
# Lifetime model calls (enrich + grade + connect rows with tokens) an item
# may spend before the loop stops and asks. Measured 2026-09-06: three
# items ran 18 to 22 calls because every "say what is wrong" reset the
# two-round budget; the daily token ceiling then froze the whole queue
# instead of the one runaway item. Eight is four full rounds.
ITEM_CALL_CAP = 8
# Kinds whose "accept as is" lands the last draft without a model call.
_ACCEPT_KINDS = ("grader bounce, twice", "budget spent")


@dataclass
class AdvanceResult:
    item_id: int
    outcome: str  # kept | asked | skipped | error
    note_path: Path | None = None
    ask_id: int | None = None
    detail: str | None = None


def neighbor_cosine(draft: EnrichmentV2, exclude_media_id: str | None) -> float | None:
    """Similarity to the closest corpus doc, via Chroma (kernel 1 is P7).
    None skips the near-dup check rather than failing the draft on an
    unavailable store."""
    try:
        from . import store

        results = store.search_videos(
            f"{draft.thesis}\n\n{draft.summary}", n=3, rerank=False, actor="grader"
        )
        for r in results:
            if exclude_media_id and r.video_id == exclude_media_id:
                continue
            return 1.0 - r.distance
    except Exception:
        return None
    return None


def _vocab() -> list[str]:
    try:
        from .enrich import tag_vocabulary

        return tag_vocabulary()
    except Exception:
        return []


def _latest_take(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM takes WHERE item_id = ? ORDER BY id DESC LIMIT 1", (item_id,)
    ).fetchone()


def latest_take(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    """Public door for the headless verbs; tests patch the private names."""
    return _latest_take(conn, item_id)


def tag_vocab() -> list[str]:
    return _vocab()


def _last_answered_ask(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT asks.kind, answers.choice, answers.text FROM asks
        JOIN answers ON answers.ask_id = asks.id
        WHERE asks.item_id = ? ORDER BY answers.id DESC LIMIT 1
        """,
        (item_id,),
    ).fetchone()


def _last_findings(conn: sqlite3.Connection, item_id: int) -> list[dict[str, Any]]:
    """The bounces of the latest grade, as findings for the next attempt."""
    row = conn.execute(
        "SELECT detail FROM activity WHERE item_id = ? AND action = 'grade' ORDER BY id DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    if row is None or not row["detail"]:
        return []
    try:
        detail: object = json.loads(row["detail"])
    except ValueError:
        return []
    if not isinstance(detail, dict):
        return []
    bounces = cast("dict[str, object]", detail).get("bounces")
    if not isinstance(bounces, list):
        return []
    return [cast("dict[str, Any]", b) for b in cast("list[object]", bounces) if isinstance(b, dict)]


def _finding_lines(findings: list[dict[str, Any]]) -> list[str]:
    return [f"{f.get('check', '')}: {f.get('detail', '')}" for f in findings]


def model_calls(conn: sqlite3.Connection, item_id: int) -> int:
    """Lifetime model calls on the item: every activity row that reports tokens."""
    row = conn.execute(
        "SELECT count(*) AS n FROM activity WHERE item_id = ? AND tokens IS NOT NULL", (item_id,)
    ).fetchone()
    return int(row["n"])


def _raise_budget_ask(
    conn: sqlite3.Connection, item_id: int, calls: int, *, view: View, attempt_n: int
) -> int | None:
    return asks.raise_ask(
        conn,
        item_id,
        proposal={
            "kind": "budget spent",
            "why": f"{calls} model calls spent on this item; the loop stops here",
            "options": ["accept as is", "drop"],
            "bounces": [],
            "view_hash": view.view_hash,
            "attempt": attempt_n,
        },
        actor="loop",
    )


def _next_attempt(conn: sqlite3.Connection, item_id: int) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM activity WHERE item_id = ? AND action = 'enrich'", (item_id,)
    ).fetchone()
    return int(row["n"]) + 1


def _last_draft(conn: sqlite3.Connection, item_id: int) -> EnrichmentV2 | None:
    row = conn.execute(
        """
        SELECT output_ref FROM activity
        WHERE item_id = ? AND action = 'enrich' AND output_ref IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    if row is None or not Path(row["output_ref"]).exists():
        return None
    return EnrichmentV2.model_validate_json(Path(row["output_ref"]).read_text())


def _grade_inputs(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    view: View,
    attempt_n: int,
    rubric_hash: str | None,
    prompt_version: str | None,
) -> str:
    """The grade row names the packet it read. A grade over a different
    packet than its draft is the fault #212 exists for, so it is refused
    here rather than recorded."""
    row = conn.execute(
        "SELECT inputs FROM activity WHERE item_id = ? AND action = 'enrich' ORDER BY id DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    drafted = json.loads(row["inputs"]).get("view_hash") if row and row["inputs"] else None
    if drafted is not None and drafted != view.view_hash:
        raise RuntimeError(f"grade would read packet {view.view_hash} but the draft read {drafted}")
    take = _latest_take(conn, item_id)
    return json.dumps(
        {
            "evidence_hash": view.bundle_hash,
            "view_hash": view.view_hash,
            "attempt": attempt_n,
            "take_id": take["id"] if take else None,
            "rubric_hash": rubric_hash,
            "prompt_version": prompt_version,
        }
    )


def _land(
    conn: sqlite3.Connection,
    item_id: int,
    draft: EnrichmentV2,
    *,
    actor: str,
    reason: str,
) -> Path:
    """Write and index the note, record kept. Idempotent via the writer's
    url lookup."""
    from . import vault
    from .notes import effective_title, index_note, snapshot_note, write_curator_note

    loop.stamp_stage("land", "writing the note")
    item = conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item_id,)).fetchone()
    bundle = load_bundle(Path(item["payload_ref"]))
    take = _latest_take(conn, item_id)
    # A re-intake lands over the note it replaces; the vault is iCloud, not
    # git, so the snapshots row is the only undo.
    existing = vault.find_note_by_url(bundle.url, 0.0)
    if existing is not None and existing.exists():
        snapshot_note(conn, item_id, existing)
    note = write_curator_note(
        bundle, take["kind"] if take else None, take["text"] if take else None, draft
    )
    index_note(note, bundle, draft)
    # The card and the ledger row stop reading as the author's handle.
    conn.execute(
        "UPDATE items SET title = ? WHERE id = ?", (effective_title(bundle, draft), item_id)
    )
    ledger.insert_activity(
        conn,
        item_id,
        actor=actor,
        action="keep",
        from_state=ledger.item_state(conn, item_id),
        to_state="kept",
        output_ref=str(note),
        reason=reason,
    )
    # Connect runs only on fresh landings (owner decision 2026-08-31): the
    # grandfathered kept pile is excluded structurally, no selector needed.
    # A connect failure never un-lands the note.
    try:
        from . import connect

        connect.propose(
            conn,
            item_id,
            draft.thesis,
            draft.summary,
            exclude_media_id=bundle.media_id,
            exclude_url=bundle.url,
            note_path=note,
            key_concepts=draft.key_concepts,
            take=take["text"] if take else None,
        )
    except Exception as exc:
        ledger.insert_activity(
            conn, item_id, actor="connect", action="connect-error", reason=str(exc)[:300]
        )
    return note


def advance_item(conn: sqlite3.Connection, item_id: int, *, actor: str = "loop") -> AdvanceResult:
    """Advance one item through enrich -> grade -> land. Safe to call on any
    item; ineligible states are a stated no-op."""
    state = ledger.item_state(conn, item_id)
    take = _latest_take(conn, item_id)
    if state not in ("answered", "read") or (state == "read" and take is None):
        return AdvanceResult(item_id, "skipped", detail=f"state {state} not advanceable")
    item = conn.execute("SELECT payload_ref FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item["payload_ref"] or not Path(item["payload_ref"]).exists():
        return AdvanceResult(item_id, "error", detail="no evidence bundle on disk")
    view = ensure_view(item_id, Path(item["payload_ref"]))
    take_rec = {"id": take["id"], "kind": take["kind"], "text": take["text"]} if take else None

    findings: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    answered = _last_answered_ask(conn, item_id)
    if answered is not None and answered["kind"] in _ACCEPT_KINDS:
        if answered["choice"] == "accept as is":
            draft = _last_draft(conn, item_id)
            if draft is None:
                return AdvanceResult(item_id, "error", detail="no draft to accept")
            note = _land(conn, item_id, draft, actor=actor, reason="owner accepted as is")
            return AdvanceResult(item_id, "kept", note_path=note)
        if answered["text"]:
            # The owner's line plus the findings that raised the ask: a
            # one-word answer must not drop the grader's own list.
            findings = [
                {"check": "the owner says", "detail": answered["text"]},
                *_last_findings(conn, item_id),
            ]
            last = _last_draft(conn, item_id)
            previous = last.model_dump() if last is not None else None

    rub = rubric.load()
    vocab = _vocab()
    n = 0
    for _ in range(MAX_ROUNDS):
        spent = model_calls(conn, item_id)
        n = _next_attempt(conn, item_id)
        if spent >= ITEM_CALL_CAP:
            ask_id = _raise_budget_ask(conn, item_id, spent, view=view, attempt_n=n - 1)
            return AdvanceResult(item_id, "asked", ask_id=ask_id)
        att = attempt_mod.open_attempt(
            item_id, n, view, take=take_rec, previous=previous, findings_in=findings
        )
        loop.stamp_stage("enrich", f"attempt {n}")
        enriched = enrich_item(conn, item_id, view=view, attempt=att)
        draft = enriched.draft
        att.record_draft(enriched.draft_path)
        previous = draft.model_dump()

        loop.stamp_stage("checks")
        bounces = grader.deterministic_checks(
            draft,
            view,
            vocab=vocab,
            take_kind=take["kind"] if take else None,
            take_text=take["text"] if take else None,
            neighbor_cosine=neighbor_cosine(draft, load_bundle(Path(view.bundle_path)).media_id),
        )
        if bounces:
            findings = [b.model_dump() for b in bounces]
            ledger.insert_activity(
                conn,
                item_id,
                actor="grader",
                action="grade",
                from_state=ledger.item_state(conn, item_id),
                to_state=None,
                inputs=_grade_inputs(
                    conn, item_id, view=view, attempt_n=n, rubric_hash=None, prompt_version=None
                ),
                reason=f"bounce: {bounces[0].check}",
                detail=json.dumps({"layer": "deterministic", "bounces": findings}),
            )
            att.close({"layer": "deterministic", "passed": False, "bounces": findings})
            continue

        loop.stamp_stage("grade", "against the rubric")
        verdict, res = grader.grade_model(draft, view, att, rub.text)
        passed = verdict.passed and not any(not s.grounded for s in verdict.spot_checks)
        outcome = {
            "layer": "model",
            "passed": passed,
            "bounces": [b.model_dump() for b in verdict.bounces],
            "spot_checks": [s.model_dump() for s in verdict.spot_checks],
        }
        ledger.insert_activity(
            conn,
            item_id,
            actor="grader",
            action="grade",
            from_state=ledger.item_state(conn, item_id),
            to_state="enriched" if passed else None,
            inputs=_grade_inputs(
                conn,
                item_id,
                view=view,
                attempt_n=n,
                rubric_hash=rub.hash,
                prompt_version=grader.GRADER_PROMPT_VERSION,
            ),
            output_ref=str(draft_path(item_id, n)),
            model=res.model,
            tokens=res.tokens,
            duration_ms=res.duration_ms,
            reason="pass"
            if passed
            else f"bounce: {verdict.bounces[0].check if verdict.bounces else 'ungrounded claim'}",
            detail=json.dumps(outcome),
        )
        att.close(outcome)
        if passed:
            note = _land(conn, item_id, draft, actor=actor, reason="grader pass")
            return AdvanceResult(item_id, "kept", note_path=note)
        findings = [b.model_dump() for b in verdict.bounces] or [
            {"check": "grounding", "detail": "ungrounded claim"}
        ]

    lines = _finding_lines(findings)
    ask_id = asks.raise_ask(
        conn,
        item_id,
        proposal={
            "kind": "grader bounce, twice",
            "why": (lines or ["two grader bounces"])[0][:200],
            "options": ["accept as is", "say what is wrong", "drop"],
            "bounces": lines,
            "view_hash": view.view_hash,
            "attempt": n,
        },
        actor="grader",
    )
    return AdvanceResult(item_id, "asked", ask_id=ask_id)
