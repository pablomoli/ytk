"""Asks and the outbox (#197 P3): the single raise and answer paths.

Every ask enters through raise_ask so two invariants hold in one place:
at most one open ask per item, and every ask row has an outbox row.
answer_ask is the one place an answer becomes a transition; the acting
surface calls it synchronously (actor "owner") until P5's loop takes
the transition over.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from ytk import ledger

# Digest order (spec, Voice and consolidation): quality kinds first,
# intent after, everything else in spec table order. Unknown kinds sort last.
DIGEST_ORDER = (
    "transcript junk",
    "blind item",
    "duplicate",
    "grader bounce, twice",
    "intent missing",
    "connections",
    "stance tension",
    "routing",
    "reflex sweep",
)

# Stated guess (spec, Asks); re-sized from four weeks of real answers.
INTENT_WINDOW_DAYS = 7

# Any choice that is not a drop moves the item forward to answered.
_DROP_CHOICES = frozenset({"drop"})

# The intent-missing answer IS the take (P4): the sentence enrichment is
# built on, and a labeled example for the future intent predictor.
_INTENT_TAKE_KINDS = {"intent": "intent", "reaction": "reaction", "just want it": "reflex"}


def _open_ask_id(conn: sqlite3.Connection, item_id: int) -> int | None:
    """Open = no answer AND its outbox row unstamped. The sweep retires asks
    (retry pass, intent expiry) by stamping outbox.answered_at with no answers
    row — answers stay owner-only events (P5)."""
    row = conn.execute(
        """
        SELECT asks.id FROM asks
        LEFT JOIN answers ON answers.ask_id = asks.id
        LEFT JOIN outbox ON outbox.ask_id = asks.id
        WHERE asks.item_id = ? AND answers.id IS NULL AND outbox.answered_at IS NULL
        LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    return row["id"] if row else None


def raise_ask(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    proposal: dict[str, Any],
    actor: str = "loop",
) -> int | None:
    """Insert an ask, its outbox row, and the transition to asking.

    Returns the ask id, or None while another ask on the item is open
    (one ask per item at a time, spec order enforced by the caller).
    """
    if _open_ask_id(conn, item_id) is not None:
        return None
    kind = proposal["kind"]
    at = ledger.now()
    cur = conn.execute(
        "INSERT INTO asks (item_id, kind, proposal, created_at) VALUES (?, ?, ?, ?)",
        (item_id, kind, json.dumps(proposal), at),
    )
    ask_id = cur.lastrowid
    assert ask_id is not None
    conn.execute(
        """
        INSERT INTO outbox (kind, subkind, item_id, ask_id, created_at, payload)
        VALUES ('ask', ?, ?, ?, ?, ?)
        """,
        (kind, item_id, ask_id, at, json.dumps(proposal)),
    )
    ledger.insert_activity(
        conn,
        item_id,
        actor=actor,
        action="ask",
        from_state=ledger.item_state(conn, item_id),
        to_state="asking",
        reason=proposal.get("why"),
        at=at,
    )
    return ask_id


def raise_intent_ask(conn: sqlite3.Connection, item_id: int, *, actor: str = "loop") -> int | None:
    """The "intent missing" ask (spec, Asks): item has no take."""
    take = conn.execute("SELECT id FROM takes WHERE item_id = ? LIMIT 1", (item_id,)).fetchone()
    if take is not None:
        return None
    proposal: dict[str, Any] = {
        "kind": "intent missing",
        "why": "why this one?",
        "options": ["intent", "reaction", "just want it", "drop"],
        "window_days": INTENT_WINDOW_DAYS,
    }
    return raise_ask(conn, item_id, proposal=proposal, actor=actor)


def answer_ask(
    conn: sqlite3.Connection,
    ask_id: int,
    *,
    choice: str,
    text: str | None = None,
    surface: str | None = None,
) -> int | None:
    """Record an answer: event inserts only. Insert-only on answers (UNIQUE
    ask_id); a second answer is a no-op returning None. The transition is the
    loop's to write (loop.apply_answer) — surfaces nudge, never advance (P5,
    single writer)."""
    at = ledger.now()
    answer_id = ledger.insert_answer(conn, ask_id, choice=choice, text=text, surface=surface, at=at)
    if answer_id is None:
        return None
    conn.execute("UPDATE outbox SET answered_at = ? WHERE ask_id = ?", (at, ask_id))
    conn.commit()
    ask = conn.execute("SELECT item_id, kind FROM asks WHERE id = ?", (ask_id,)).fetchone()
    if ask["kind"] == "intent missing" and choice in _INTENT_TAKE_KINDS:
        # The intent answer IS the take (P4): a labeled event, not a transition.
        ledger.insert_take(
            conn,
            ask["item_id"],
            kind=_INTENT_TAKE_KINDS[choice],
            text=text or "",
            surface=surface,
            at=at,
        )
    return answer_id


def backfill_outbox(conn: sqlite3.Connection) -> int:
    """Give P2-era asks (inserted before the outbox path existed) their
    outbox rows. Idempotent; answered asks arrive already stamped."""
    rows = conn.execute(
        """
        SELECT asks.id, asks.item_id, asks.kind, asks.proposal, asks.created_at,
               answers.at AS answered_at
        FROM asks
        LEFT JOIN outbox ON outbox.ask_id = asks.id
        LEFT JOIN answers ON answers.ask_id = asks.id
        WHERE outbox.id IS NULL
        """
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT INTO outbox (kind, subkind, item_id, ask_id, created_at, payload, answered_at)
            VALUES ('ask', ?, ?, ?, ?, ?, ?)
            """,
            (
                row["kind"],
                row["item_id"],
                row["id"],
                row["created_at"],
                row["proposal"],
                row["answered_at"],
            ),
        )
    conn.commit()
    return len(rows)


def open_outbox(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Open rows in digest order: asks by kind, quality first, oldest first
    within a kind. The render that follows is the delivery view."""
    rows = conn.execute(
        """
        SELECT outbox.*, items.title, items.url, items.source
        FROM outbox
        LEFT JOIN items ON items.id = outbox.item_id
        WHERE outbox.answered_at IS NULL
        """
    ).fetchall()

    def key(row: sqlite3.Row) -> tuple[int, str]:
        sub = row["subkind"]
        rank = DIGEST_ORDER.index(sub) if sub in DIGEST_ORDER else len(DIGEST_ORDER)
        return (rank, row["created_at"])

    return [dict(r) for r in sorted(rows, key=key)]


def parked_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """The digest's one parked line: "N parked, oldest from <date>"."""
    row = conn.execute(
        """
        SELECT count(*) AS n, min(items.captured_at) AS oldest FROM items
        WHERE (SELECT to_state FROM activity
               WHERE item_id = items.id AND to_state IS NOT NULL
               ORDER BY id DESC LIMIT 1) = 'parked'
        """
    ).fetchone()
    return {"count": row["n"], "oldest": row["oldest"]}


def mark_presented(conn: sqlite3.Connection, outbox_ids: list[int]) -> None:
    """Stamp seen-without-answering, once: the first render is the zero
    point of the answer-latency instrument and later renders keep it."""
    at = ledger.now()
    conn.executemany(
        "UPDATE outbox SET presented_at = ? WHERE id = ? AND presented_at IS NULL",
        [(at, oid) for oid in outbox_ids],
    )
    conn.commit()


def ask_context(conn: sqlite3.Connection, item_id: int | None, kind: str | None) -> dict[str, Any]:
    """What a card needs to be answerable, attached at render time so
    already-open asks gain it without a re-raise (live catch 2026-08-31:
    the bounce card asked the owner to judge a draft it did not show).
    Title and thumbnail come from the evidence bundle when the items row
    lacks them; bounce asks also carry the latest draft and every grader
    objection."""
    import json as _json
    from pathlib import Path

    ctx: dict[str, Any] = {"thumbnail": None, "draft": None, "objections": None}
    if item_id is None:
        return ctx
    item = conn.execute("SELECT title, payload_ref FROM items WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        return ctx
    bundle: dict[str, Any] = {}
    if item["payload_ref"]:
        try:
            loaded: object = _json.loads(Path(item["payload_ref"]).read_text())
            if isinstance(loaded, dict):
                bundle = dict(cast("dict[str, Any]", loaded))
        except (OSError, ValueError):
            bundle = {}
    if not item["title"] and bundle.get("title"):
        ctx["title"] = bundle["title"]
    ctx["thumbnail"] = bundle.get("thumbnail")
    if kind != "grader bounce, twice":
        return ctx
    draft_row = conn.execute(
        """
        SELECT output_ref FROM activity
        WHERE item_id = ? AND action = 'enrich' AND output_ref IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    if draft_row and Path(draft_row["output_ref"]).exists():
        try:
            raw: object = _json.loads(Path(draft_row["output_ref"]).read_text())
            if isinstance(raw, dict):
                draft = dict(cast("dict[str, Any]", raw))
                ctx["draft"] = {
                    k: draft.get(k)
                    for k in ("thesis", "summary", "key_concepts", "insights", "take_response")
                }
        except (OSError, ValueError):
            pass
    grade_row = conn.execute(
        """
        SELECT detail FROM activity
        WHERE item_id = ? AND action = 'grade' AND detail IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    if grade_row:
        try:
            detail: object = _json.loads(grade_row["detail"])
        except ValueError:
            detail = None
        if isinstance(detail, dict):
            typed_detail = cast("dict[str, Any]", detail)
            objections: list[dict[str, Any]] = []
            bounces = cast("list[dict[str, Any]]", typed_detail.get("bounces") or [])
            for b in bounces:
                objections.append({"check": b.get("check"), "detail": b.get("detail")})
            spots = cast("list[dict[str, Any]]", typed_detail.get("spot_checks") or [])
            for s in spots:
                if not s.get("grounded", True):
                    objections.append(
                        {"check": "ungrounded claim", "detail": s.get("claim") or s.get("detail")}
                    )
            ctx["objections"] = objections
    return ctx
