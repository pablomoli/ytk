"""P5 breaker (#197): com.ytk.watchdog evaluates health from outside the hub
process, trips to inert, and only `ytk loop resume` clears it."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from ytk import ledger, loop, watchdog
from ytk.cli import cli


@pytest.fixture
def conn():
    c = ledger.connect()
    yield c
    c.close()


def _item(conn) -> int:
    item_id = ledger.insert_item(conn, source="youtube", url="https://y/wd", title="W")
    assert item_id is not None
    return item_id


HEALTHY = {
    "rate_limit_hits_last_hour": 0,
    "errors_last_hour": 0,
    "tokens_today": 1000,
}


class TestEvaluate:
    def test_healthy_returns_none(self, conn):
        assert watchdog.evaluate(conn, HEALTHY) is None

    def test_kill_file_trips(self, conn):
        loop.kill_path().parent.mkdir(parents=True, exist_ok=True)
        loop.kill_path().write_text("")
        reason = watchdog.evaluate(conn, HEALTHY)
        assert reason is not None and "kill" in reason

    def test_rate_limit_trips_at_three(self, conn):
        reason = watchdog.evaluate(conn, dict(HEALTHY, rate_limit_hits_last_hour=3))
        assert reason is not None and "rate" in reason

    def test_error_rate_trips_at_five(self, conn):
        reason = watchdog.evaluate(conn, dict(HEALTHY, errors_last_hour=5))
        assert reason is not None and "error" in reason

    def test_token_ceiling_trips(self, conn):
        reason = watchdog.evaluate(conn, dict(HEALTHY, tokens_today=watchdog.TOKEN_CEILING))
        assert reason is not None and "token" in reason

    def test_unparked_stuck_item_trips(self, conn):
        item_id = _item(conn)
        conn.execute("UPDATE items SET tick_count = 4 WHERE id = ?", (item_id,))
        conn.commit()
        reason = watchdog.evaluate(conn, HEALTHY)
        assert reason is not None and "stuck" in reason

    def test_missing_health_fields_do_not_trip(self, conn):
        assert watchdog.evaluate(conn, {}) is None


class TestRunOnce:
    def test_trip_writes_inert_with_reason(self, conn):
        loop.write_health(**dict(HEALTHY, rate_limit_hits_last_hour=5))
        reason = watchdog.run_once()
        assert reason is not None
        assert loop.inert_path().exists()
        assert "rate" in loop.inert_path().read_text()

    def test_healthy_run_never_clears_an_existing_inert(self):
        loop.inert_path().parent.mkdir(parents=True, exist_ok=True)
        loop.inert_path().write_text("tripped earlier")
        loop.write_health(**HEALTHY)
        watchdog.run_once()
        assert loop.inert_path().exists()
        assert loop.inert_path().read_text() == "tripped earlier"


class TestLoopCli:
    def test_status_prints_health(self):
        loop.write_health(last_tick_at="2026-08-31T13:00:00+00:00", items_advanced=2)
        result = CliRunner().invoke(cli, ["loop", "status"])
        assert result.exit_code == 0, result.output
        assert "advanced" in result.output

    def test_kill_then_resume(self):
        result = CliRunner().invoke(cli, ["loop", "kill"])
        assert result.exit_code == 0
        assert loop.kill_path().exists()
        loop.inert_path().write_text("tripped: kill file present")
        result = CliRunner().invoke(cli, ["loop", "resume"])
        assert result.exit_code == 0
        assert not loop.inert_path().exists()
        assert "kill" in result.output  # warns the kill file is still there

    def test_resume_without_inert_is_calm(self):
        result = CliRunner().invoke(cli, ["loop", "resume"])
        assert result.exit_code == 0

    def test_watchdog_run_command_trips(self):
        loop.write_health(**dict(HEALTHY, errors_last_hour=9))
        result = CliRunner().invoke(cli, ["loop", "watchdog-run"])
        assert result.exit_code == 0, result.output
        assert loop.inert_path().exists()
