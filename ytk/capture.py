"""The capture verb (#197 P2): a URL becomes a ledger row and nothing else.

Every surface that used to run fetch -> enrich -> vault write now stops here;
the corpus is written only after the item passes the owner (first law).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import asks, capture_log, ledger
from .reels import canonical_url

# One paste put 5M chars in the queue (#132); a take is a sentence or a
# caption, never a document.
TEXT_CAP = 65_536

# States before enrichment: a take written here still reaches the enricher.
_PRE_ENRICH = ("captured", "read", "asking", "answered", "parked")


@dataclass
class CaptureResult:
    item_id: int
    take_id: int | None
    duplicate: bool
    # "answered" | "revived" on a deliberate re-capture, else None
    reclaimed: str | None = None


def find_item(conn: sqlite3.Connection, source: str, url: str) -> int | None:
    """The item holding this content under any URL shape (youtu.be and
    watch?v=, share links with tracking params)."""
    row = conn.execute(
        "SELECT id FROM items WHERE source = ? AND url = ?", (source, url)
    ).fetchone()
    if row:
        return row["id"]
    key = canonical_url(url)
    hint = key.removeprefix("youtube:")
    for row in conn.execute(
        "SELECT id, url FROM items WHERE source = ? AND instr(url, ?) > 0 ORDER BY id",
        (source, hint),
    ):
        if canonical_url(row["url"]) == key:
            return row["id"]
    return None


def capture(
    conn: sqlite3.Connection,
    *,
    source: str,
    url: str,
    surface: str,
    title: str | None = None,
    text: str | None = None,
    take_kind: str = "intent",
    actor: str = "owner",
    log: bool = True,
    deliberate: bool = False,
) -> CaptureResult:
    """Insert the item (no-op on duplicate), attach a take when the owner said
    something, log the attempt. Writes nothing to the vault.

    `deliberate` is the call site's word that the owner chose this URL: a
    silent capture then carries a reflex take (the choice is the sentence),
    and a re-capture answers the item's open intent ask or revives it from
    dropped. Passive surfaces (playlist sync, feed, reels --all) leave it
    False and the intent ask stays theirs."""
    item_id = find_item(conn, source, url)
    duplicate = item_id is not None
    if item_id is None:
        item_id = ledger.insert_item(conn, source=source, url=url, title=title, provenance=surface)
        if item_id is None:  # a concurrent capture won the insert
            item_id = find_item(conn, source, url)
            assert item_id is not None
            duplicate = True
        else:
            ledger.insert_activity(
                conn, item_id, actor=actor, action="capture", to_state="captured"
            )
    # Agent-written takes stay distinguishable from the owner's own words.
    take_surface = "agent" if actor == "agent" else surface
    take_id = None
    reclaimed = None
    if duplicate and deliberate:
        reclaimed, take_id = _reclaim(
            conn, item_id, text=text, take_kind=take_kind, surface=take_surface
        )
    elif text:
        take_id = ledger.insert_take(
            conn, item_id, kind=take_kind, text=text[:TEXT_CAP], surface=take_surface
        )
    elif deliberate:
        take_id = ledger.insert_take(conn, item_id, kind="reflex", text="", surface=take_surface)
    if log:
        capture_log.log_capture(
            surface, url, source=source, outcome="duplicate" if duplicate else "captured"
        )
    return CaptureResult(item_id=item_id, take_id=take_id, duplicate=duplicate, reclaimed=reclaimed)


def _latest_take(conn: sqlite3.Connection, item_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM takes WHERE item_id = ? ORDER BY id DESC LIMIT 1", (item_id,)
    ).fetchone()
    return row["id"] if row else None


def _reclaim(
    conn: sqlite3.Connection, item_id: int, *, text: str | None, take_kind: str, surface: str
) -> tuple[str | None, int | None]:
    """A deliberate capture of an item that already exists. The owner's
    choice outranks the silence a passive surface left behind; it never
    adds a second note to a kept item."""
    note = text[:TEXT_CAP] if text else None
    state = ledger.item_state(conn, item_id)
    if state == "dropped":
        # Dropped is terminal: the loop never picks it, so a surface writing
        # the re-capture races nothing, exactly like a first capture.
        take_id = ledger.insert_take(
            conn, item_id, kind="intent" if note else "reflex", text=note or "", surface=surface
        )
        ledger.insert_activity(
            conn,
            item_id,
            actor="owner",
            action="revive",
            from_state="dropped",
            to_state="captured",
            reason="deliberate capture",
        )
        return "revived", take_id
    ask = conn.execute(
        """
        SELECT asks.id FROM asks
        LEFT JOIN answers ON answers.ask_id = asks.id
        LEFT JOIN outbox ON outbox.ask_id = asks.id
        WHERE asks.item_id = ? AND asks.kind = 'intent missing'
          AND answers.id IS NULL AND outbox.answered_at IS NULL
        """,
        (item_id,),
    ).fetchone()
    if ask is not None:
        # answer_ask writes the take; the loop applies the answer.
        asks.answer_ask(
            conn,
            ask["id"],
            choice="intent" if note else "just want it",
            text=note,
            surface=surface,
        )
        return "answered", _latest_take(conn, item_id)
    if note:
        return None, ledger.insert_take(conn, item_id, kind=take_kind, text=note, surface=surface)
    if state in _PRE_ENRICH and _latest_take(conn, item_id) is None:
        return None, ledger.insert_take(conn, item_id, kind="reflex", text="", surface=surface)
    return None, None
