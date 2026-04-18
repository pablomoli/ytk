"""SQLite wrapper for tracking processed videos in the ytk ingestion pipeline."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


_DB_PATH = Path.home() / ".ytk" / "ytk.db"
_conn: sqlite3.Connection | None = None

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS videos (
    video_id     TEXT PRIMARY KEY,
    title        TEXT,
    added_at     TEXT,
    processed_at TEXT,
    status       TEXT,
    skip_reason  TEXT
)
"""


def _get_conn() -> sqlite3.Connection:
    """Return the cached SQLite connection, creating it on first call."""
    global _conn
    if _conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute(_CREATE_TABLE)
        _conn.commit()
    return _conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_processed(video_id: str) -> bool:
    """Return True if the video has a 'processed' record in the database."""
    row = _get_conn().execute(
        "SELECT status FROM videos WHERE video_id = ?", (video_id,)
    ).fetchone()
    return row is not None and row["status"] == "processed"


def mark_processed(video_id: str, title: str) -> None:
    """Insert or replace a video record with status 'processed'."""
    conn = _get_conn()
    conn.execute(
        """\
        INSERT INTO videos (video_id, title, added_at, processed_at, status, skip_reason)
        VALUES (?, ?, ?, ?, 'processed', NULL)
        ON CONFLICT(video_id) DO UPDATE SET
            title        = excluded.title,
            processed_at = excluded.processed_at,
            status       = 'processed',
            skip_reason  = NULL
        """,
        (video_id, title, _now(), _now()),
    )
    conn.commit()


def mark_skipped(video_id: str, title: str, reason: str) -> None:
    """Insert or replace a video record with status 'skipped'."""
    conn = _get_conn()
    conn.execute(
        """\
        INSERT INTO videos (video_id, title, added_at, processed_at, status, skip_reason)
        VALUES (?, ?, ?, NULL, 'skipped', ?)
        ON CONFLICT(video_id) DO UPDATE SET
            title       = excluded.title,
            status      = 'skipped',
            skip_reason = excluded.skip_reason
        """,
        (video_id, title, _now(), reason),
    )
    conn.commit()


def mark_failed(video_id: str, title: str, reason: str) -> None:
    """Insert or replace a video record with status 'failed'."""
    conn = _get_conn()
    conn.execute(
        """\
        INSERT INTO videos (video_id, title, added_at, processed_at, status, skip_reason)
        VALUES (?, ?, ?, NULL, 'failed', ?)
        ON CONFLICT(video_id) DO UPDATE SET
            title       = excluded.title,
            status      = 'failed',
            skip_reason = excluded.skip_reason
        """,
        (video_id, title, _now(), reason),
    )
    conn.commit()


def get_all(status: str | None = None) -> list[dict]:
    """
    Return all video records as plain dicts.
    If status is given, filter to that status ('processed', 'skipped', 'failed').
    """
    conn = _get_conn()
    if status is not None:
        rows = conn.execute(
            "SELECT * FROM videos WHERE status = ? ORDER BY added_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM videos ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]
