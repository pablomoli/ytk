"""Curator-engine ledger (#197, P1): schema, migrations, event-table constraints.

The binding schema is docs/architecture/curator-engine.md, "Ledger and plans".
"""

from __future__ import annotations

import sqlite3

import pytest

from ytk import ledger

TABLES = {"items", "activity", "takes", "asks", "answers", "outbox", "snapshots"}


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "ledger.db"
    monkeypatch.setenv("YTK_LEDGER", str(path))
    return path


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r["name"] for r in rows if not r["name"].startswith("sqlite_")}


def test_connect_creates_all_tables(db_path):
    conn = ledger.connect()
    assert table_names(conn) >= TABLES
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(ledger.MIGRATIONS)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_duplicate_capture_is_a_noop(db_path):
    conn = ledger.connect()
    first = ledger.insert_item(conn, source="youtube", url="https://y/1", title="t")
    dup = ledger.insert_item(conn, source="youtube", url="https://y/1", title="t again")
    assert first is not None
    assert dup is None
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 1


def test_state_is_last_activity_row_with_to_state(db_path):
    conn = ledger.connect()
    item = ledger.insert_item(conn, source="web", url="https://w/1")
    assert ledger.item_state(conn, item) is None
    ledger.insert_activity(conn, item, actor="loop", action="capture", to_state="captured")
    ledger.insert_activity(
        conn, item, actor="loop", action="read", from_state="captured", to_state="read"
    )
    ledger.insert_activity(conn, item, actor="grader", action="note", to_state=None)
    assert ledger.item_state(conn, item) == "read"


def test_double_answer_is_a_noop(db_path):
    conn = ledger.connect()
    item = ledger.insert_item(conn, source="web", url="https://w/1")
    ask = conn.execute(
        "INSERT INTO asks (item_id, kind, proposal, created_at) VALUES (?, ?, '{}', ?)",
        (item, "intent missing", "2026-08-30T00:00:00+00:00"),
    ).lastrowid
    first = ledger.insert_answer(conn, ask, choice="drop", surface="hub")
    dup = ledger.insert_answer(conn, ask, choice="keep", surface="hub")
    assert first is not None
    assert dup is None
    row = conn.execute("SELECT choice FROM answers WHERE ask_id = ?", (ask,)).fetchone()
    assert row["choice"] == "drop"


@pytest.fixture()
def brain(tmp_path):
    root = tmp_path / "vault" / "second-brain"
    yt = root / "sources" / "youtube"
    web = root / "sources" / "web"
    yt.mkdir(parents=True)
    web.mkdir(parents=True)
    (yt / "talk.md").write_text(
        "---\nurl: https://www.youtube.com/watch?v=abc\ntitle: A talk\ncaptured: 2026-05-01\n---\n\nbody\n"
    )
    (web / "note.md").write_text("---\ntitle: A page\n---\n\nbody\n")
    return root


def test_grandfather_imports_every_note_once(db_path, brain):
    conn = ledger.connect()
    result = ledger.grandfather(conn, brain)
    assert result.imported == {"youtube": 1, "web": 1}
    assert result.skipped == []
    rows = conn.execute("SELECT * FROM items ORDER BY source").fetchall()
    assert [r["source"] for r in rows] == ["web", "youtube"]
    yt = next(r for r in rows if r["source"] == "youtube")
    assert yt["url"] == "https://www.youtube.com/watch?v=abc"
    assert yt["title"] == "A talk"
    assert yt["provenance"] == "grandfathered"
    assert yt["captured_at"].startswith("2026-05-01")
    web = next(r for r in rows if r["source"] == "web")
    assert web["url"] == "note://sources/web/note.md"  # no url frontmatter
    assert web["captured_at"]  # birthtime fallback, still stamped
    for r in rows:
        assert ledger.item_state(conn, r["id"]) == "kept-unlabeled"
    assert conn.execute("SELECT count(*) FROM asks").fetchone()[0] == 0
    # Idempotent: a rerun imports nothing and duplicates nothing.
    assert ledger.grandfather(conn, brain).imported == {}
    assert conn.execute("SELECT count(*) FROM activity").fetchone()[0] == 2


def test_grandfather_names_same_run_duplicates(db_path, brain):
    (brain / "sources" / "youtube" / "z-talk-again.md").write_text(
        "---\nurl: https://www.youtube.com/watch?v=abc\ntitle: Same video twice\n---\n"
    )
    conn = ledger.connect()
    result = ledger.grandfather(conn, brain)
    assert result.imported == {"youtube": 1, "web": 1}
    assert result.skipped == ["sources/youtube/z-talk-again.md"]
    # A rerun reports nothing: every row pre-exists, no same-run collision.
    rerun = ledger.grandfather(conn, brain)
    assert rerun.imported == {}
    assert rerun.skipped == ["sources/youtube/z-talk-again.md"]


def test_grandfather_refuses_missing_sources_tree(db_path, tmp_path):
    conn = ledger.connect()
    with pytest.raises(RuntimeError):
        ledger.grandfather(conn, tmp_path / "gone")


def test_reopen_preserves_data_and_reruns_nothing(db_path):
    conn = ledger.connect()
    conn.execute(
        "INSERT INTO items (source, url, title, provenance, captured_at)"
        " VALUES ('youtube', 'https://y/1', 't', 'grandfathered', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()
    conn2 = ledger.connect()
    assert conn2.execute("SELECT count(*) FROM items").fetchone()[0] == 1
    assert conn2.execute("PRAGMA user_version").fetchone()[0] == len(ledger.MIGRATIONS)
