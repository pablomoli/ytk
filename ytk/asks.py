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
from typing import Any

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


def _open_ask_id(conn: sqlite3.Connection, item_id: int) -> int | None:
    row = conn.execute(
        """
        SELECT asks.id FROM asks
        LEFT JOIN answers ON answers.ask_id = asks.id
        WHERE asks.item_id = ? AND answers.id IS NULL
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
    """Record an answer and advance the item. Insert-only on answers
    (UNIQUE ask_id); a second answer is a no-op returning None."""
    at = ledger.now()
    answer_id = ledger.insert_answer(conn, ask_id, choice=choice, text=text, surface=surface, at=at)
    if answer_id is None:
        return None
    conn.execute("UPDATE outbox SET answered_at = ? WHERE ask_id = ?", (at, ask_id))
    item_id = conn.execute("SELECT item_id FROM asks WHERE id = ?", (ask_id,)).fetchone()["item_id"]
    to_state = "dropped" if choice in _DROP_CHOICES else "answered"
    ledger.insert_activity(
        conn,
        item_id,
        actor="owner",
        action="answer",
        from_state=ledger.item_state(conn, item_id),
        to_state=to_state,
        reason=choice,
        detail=json.dumps({"ask_id": ask_id, "text": text}) if text else None,
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
