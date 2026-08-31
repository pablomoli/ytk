"""CLI wiring for the curator ledger (#197 P1) and the hub single-instance lock (#38)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ytk import hublock, ledger
from ytk.cli import cli


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_LEDGER", str(tmp_path / "ledger.db"))
    root = tmp_path / "vault"
    yt = root / "second-brain" / "sources" / "youtube"
    yt.mkdir(parents=True)
    (yt / "talk.md").write_text("---\nurl: https://y/1\ntitle: T\ncaptured: 2026-05-01\n---\n")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(root))
    return tmp_path


def test_ledger_grandfather_imports_and_reports(env):
    result = CliRunner().invoke(cli, ["ledger", "grandfather"])
    assert result.exit_code == 0, result.output
    assert "youtube" in result.output and "1" in result.output
    conn = ledger.connect()
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 1
    rerun = CliRunner().invoke(cli, ["ledger", "grandfather"])
    assert rerun.exit_code == 0
    assert "0" in rerun.output


def test_ledger_status_counts_tables(env):
    CliRunner().invoke(cli, ["ledger", "grandfather"])
    result = CliRunner().invoke(cli, ["ledger", "status"])
    assert result.exit_code == 0, result.output
    assert "items" in result.output
    assert "kept-unlabeled" in result.output


def test_ui_exits_quietly_when_lock_held(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_HUB_LOCK", str(tmp_path / "hub.lock"))
    held = hublock.acquire()
    assert held is not None
    with patch("uvicorn.run") as run:
        result = CliRunner().invoke(cli, ["ui"])
    assert result.exit_code == 0, result.output
    run.assert_not_called()
    held.close()


def test_ui_takes_lock_before_serving(tmp_path, monkeypatch):
    monkeypatch.setenv("YTK_HUB_LOCK", str(tmp_path / "hub.lock"))
    lock_free_at_serve: list[bool] = []
    with (
        patch("ytk.chroma_runtime.runtime_config", return_value=MagicMock(mode="embedded")),
        patch(
            "uvicorn.run",
            side_effect=lambda *a, **k: lock_free_at_serve.append(hublock.acquire() is not None),
        ),
    ):
        result = CliRunner().invoke(cli, ["ui"])
    assert result.exit_code == 0, result.output
    assert lock_free_at_serve == [False]


def test_ledger_backfill_outbox_reports_created_rows(env):
    import json

    conn = ledger.connect()
    item_id = ledger.insert_item(conn, source="youtube", url="https://y/orphan", title="O")
    conn.execute(
        "INSERT INTO asks (item_id, kind, proposal, created_at) VALUES (?, ?, ?, ?)",
        (item_id, "transcript junk", json.dumps({"kind": "transcript junk"}), ledger.now()),
    )
    conn.commit()
    conn.close()
    result = CliRunner().invoke(cli, ["ledger", "backfill-outbox"])
    assert result.exit_code == 0
    assert "1" in result.output
    conn = ledger.connect()
    assert conn.execute("SELECT count(*) FROM outbox").fetchone()[0] == 1
    conn.close()
