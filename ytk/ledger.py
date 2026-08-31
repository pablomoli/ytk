"""Curator-engine ledger (#197): SQLite WAL store under ~/.ytk.

Schema is fixed by docs/architecture/curator-engine.md ("Ledger and plans",
locked 2026-08-30). Transitions are activity rows; an item's state is its
last activity row with a non-null to_state.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Append-only list; PRAGMA user_version counts applied entries. Never edit a
# shipped migration — add the next one.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE items (
        id          INTEGER PRIMARY KEY,
        source      TEXT NOT NULL,
        url         TEXT NOT NULL,
        title       TEXT,
        provenance  TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        payload_ref TEXT,
        lease_until TEXT,
        tick_count  INTEGER NOT NULL DEFAULT 0,
        UNIQUE (source, url)
    );

    CREATE TABLE activity (
        id          INTEGER PRIMARY KEY,
        item_id     INTEGER NOT NULL REFERENCES items(id),
        at          TEXT NOT NULL,
        actor       TEXT NOT NULL,
        action      TEXT NOT NULL,
        from_state  TEXT,
        to_state    TEXT,
        inputs      TEXT,
        output_ref  TEXT,
        model       TEXT,
        tokens      INTEGER,
        duration_ms INTEGER,
        reason      TEXT,
        detail      TEXT
    );
    CREATE INDEX activity_item ON activity(item_id, id);

    CREATE TABLE takes (
        id         INTEGER PRIMARY KEY,
        item_id    INTEGER NOT NULL REFERENCES items(id),
        kind       TEXT NOT NULL,
        text       TEXT,
        written_at TEXT NOT NULL,
        surface    TEXT
    );

    CREATE TABLE asks (
        id         INTEGER PRIMARY KEY,
        item_id    INTEGER NOT NULL REFERENCES items(id),
        kind       TEXT NOT NULL,
        proposal   TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE answers (
        id      INTEGER PRIMARY KEY,
        ask_id  INTEGER NOT NULL UNIQUE REFERENCES asks(id),
        choice  TEXT NOT NULL,
        text    TEXT,
        at      TEXT NOT NULL,
        surface TEXT
    );

    CREATE TABLE outbox (
        id           INTEGER PRIMARY KEY,
        kind         TEXT NOT NULL,
        subkind      TEXT,
        item_id      INTEGER REFERENCES items(id),
        ask_id       INTEGER REFERENCES asks(id),
        created_at   TEXT NOT NULL,
        payload      TEXT,
        presented_at TEXT,
        answered_at  TEXT
    );

    CREATE TABLE snapshots (
        id         INTEGER PRIMARY KEY,
        item_id    INTEGER NOT NULL REFERENCES items(id),
        at         TEXT NOT NULL,
        before_ref TEXT,
        after_ref  TEXT
    );
    """,
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def insert_item(
    conn: sqlite3.Connection,
    *,
    source: str,
    url: str,
    title: str | None = None,
    provenance: str = "captured",
    captured_at: str | None = None,
    payload_ref: str | None = None,
) -> int | None:
    """Insert a capture; returns the item id, or None when (source, url) exists."""
    cur = conn.execute(
        """
        INSERT INTO items (source, url, title, provenance, captured_at, payload_ref)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (source, url) DO NOTHING
        """,
        (source, url, title, provenance, captured_at or _now(), payload_ref),
    )
    conn.commit()
    return cur.lastrowid if cur.rowcount else None


def insert_activity(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    actor: str,
    action: str,
    from_state: str | None = None,
    to_state: str | None = None,
    inputs: str | None = None,
    output_ref: str | None = None,
    model: str | None = None,
    tokens: int | None = None,
    duration_ms: int | None = None,
    reason: str | None = None,
    detail: str | None = None,
    at: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO activity (item_id, at, actor, action, from_state, to_state,
                              inputs, output_ref, model, tokens, duration_ms, reason, detail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id,
            at or _now(),
            actor,
            action,
            from_state,
            to_state,
            inputs,
            output_ref,
            model,
            tokens,
            duration_ms,
            reason,
            detail,
        ),
    )
    conn.commit()
    assert cur.lastrowid is not None
    return cur.lastrowid


def item_state(conn: sqlite3.Connection, item_id: int) -> str | None:
    row = conn.execute(
        """
        SELECT to_state FROM activity
        WHERE item_id = ? AND to_state IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    return row["to_state"] if row else None


def insert_answer(
    conn: sqlite3.Connection,
    ask_id: int,
    *,
    choice: str,
    text: str | None = None,
    surface: str | None = None,
    at: str | None = None,
) -> int | None:
    """Insert-only; returns the answer id, or None when the ask is already answered."""
    cur = conn.execute(
        """
        INSERT INTO answers (ask_id, choice, text, at, surface)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (ask_id) DO NOTHING
        """,
        (ask_id, choice, text, at or _now(), surface),
    )
    conn.commit()
    return cur.lastrowid if cur.rowcount else None


SOURCES = ("youtube", "instagram", "web", "tiktok")


def _note_captured_at(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        head = fh.read(1500)
    m = re.search(r"^captured: (\d{4}-\d{2}-\d{2})", head, re.MULTILINE)
    if m:
        return datetime.fromisoformat(m.group(1)).replace(tzinfo=UTC).isoformat()
    # Older notes predate the stamp; birth time is the reliable fallback on macOS.
    return datetime.fromtimestamp(path.stat().st_birthtime, tz=UTC).isoformat()


def _note_frontmatter_value(path: Path, key: str) -> str | None:
    with open(path, encoding="utf-8", errors="replace") as fh:
        head = fh.read(1500)
    m = re.search(rf"^{key}: (.+)$", head, re.MULTILINE)
    return m.group(1).strip().strip('"') if m else None


@dataclass
class GrandfatherResult:
    imported: dict[str, int]
    skipped: list[str]  # notes whose (source, url) another note claimed this run


def grandfather(conn: sqlite3.Connection, brain_root: Path) -> GrandfatherResult:
    """Give every existing source note an items row and one kept-unlabeled
    activity row. No asks. Idempotent via UNIQUE(source, url).

    Refuses an absent or empty sources tree: the vault is iCloud and can
    stall mid-run, and importing zero notes must not look like success.
    """
    notes = {s: sorted((brain_root / "sources" / s).glob("*.md")) for s in SOURCES}
    if not any(notes.values()):
        raise RuntimeError(f"no source notes under {brain_root / 'sources'} — vault stalled?")
    imported: dict[str, int] = {}
    skipped: list[str] = []
    for source, paths in notes.items():
        for path in paths:
            rel = path.relative_to(brain_root)
            url = _note_frontmatter_value(path, "url") or f"note://{rel}"
            item_id = insert_item(
                conn,
                source=source,
                url=url,
                title=_note_frontmatter_value(path, "title") or path.stem,
                provenance="grandfathered",
                captured_at=_note_captured_at(path),
                payload_ref=str(rel),
            )
            if item_id is None:
                # The row held by a different note is a vault duplicate worth
                # naming; the same note again is just an idempotent rerun.
                row = conn.execute(
                    "SELECT payload_ref FROM items WHERE source = ? AND url = ?", (source, url)
                ).fetchone()
                if row["payload_ref"] != str(rel):
                    skipped.append(str(rel))
                continue
            insert_activity(
                conn,
                item_id,
                actor="loop",
                action="grandfather",
                to_state="kept-unlabeled",
                reason="grandfather import (P1)",
            )
            imported[source] = imported.get(source, 0) + 1
    return GrandfatherResult(imported=imported, skipped=skipped)


def ledger_path() -> Path:
    env = os.environ.get("YTK_LEDGER")
    return Path(env) if env else Path.home() / ".ytk" / "ledger.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the ledger, applying any pending migrations. Callers own the handle."""
    path = path or ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    applied = conn.execute("PRAGMA user_version").fetchone()[0]
    for script in MIGRATIONS[applied:]:
        conn.executescript(script)
        applied += 1
        conn.execute(f"PRAGMA user_version = {applied}")
    conn.commit()
    return conn
