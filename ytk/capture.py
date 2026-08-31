"""The capture verb (#197 P2): a URL becomes a ledger row and nothing else.

Every surface that used to run fetch -> enrich -> vault write now stops here;
the corpus is written only after the item passes the owner (first law).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import capture_log, ledger

# One paste put 5M chars in the queue (#132); a take is a sentence or a
# caption, never a document.
TEXT_CAP = 65_536


@dataclass
class CaptureResult:
    item_id: int
    take_id: int | None
    duplicate: bool


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
) -> CaptureResult:
    """Insert the item (no-op on duplicate), attach a take when the owner said
    something, log the attempt. Writes nothing to the vault."""
    item_id = ledger.insert_item(conn, source=source, url=url, title=title, provenance=surface)
    duplicate = item_id is None
    if duplicate:
        row = conn.execute(
            "SELECT id FROM items WHERE source = ? AND url = ?", (source, url)
        ).fetchone()
        item_id = row["id"]
    else:
        ledger.insert_activity(conn, item_id, actor=actor, action="capture", to_state="captured")
    take_id = None
    if text:
        take_id = ledger.insert_take(
            conn, item_id, kind=take_kind, text=text[:TEXT_CAP], surface=surface
        )
    if log:
        capture_log.log_capture(
            surface, url, source=source, outcome="duplicate" if duplicate else "captured"
        )
    return CaptureResult(item_id=item_id, take_id=take_id, duplicate=duplicate)
