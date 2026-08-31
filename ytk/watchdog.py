"""The breaker, outside the process (#197 P5).

com.ytk.watchdog (launchd, every 5 minutes) runs `ytk loop watchdog-run`,
which reads ~/.ytk/loop-health.json — the loop's own honest numbers — plus
the kill file and the ledger, and on a trip writes ~/.ytk/loop.inert. The
loop checks that flag before every transition and cannot clear it; only
`ytk loop resume` can. Living in a separate process means the loop cannot
disable its own breaker.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from . import loop

# Stated guesses (spec, The loop), re-sized from the activity table.
RATE_LIMIT_TRIP = 3  # rate-limit errors in the trailing hour
ERROR_TRIP = 5  # loop errors in the trailing hour
TOKEN_CEILING = 300_000  # tokens since UTC midnight (~8 items/day measures ~100k)


def evaluate(conn: sqlite3.Connection, health: dict[str, Any]) -> str | None:
    """First tripped rule wins; None means healthy. Missing health fields
    read as zero — a silent loop is the stale-tick problem, not this one."""
    if loop.kill_path().exists():
        return "kill file present"
    if int(health.get("rate_limit_hits_last_hour", 0) or 0) >= RATE_LIMIT_TRIP:
        return f"{health.get('rate_limit_hits_last_hour')} rate-limit errors in the last hour"
    if int(health.get("errors_last_hour", 0) or 0) >= ERROR_TRIP:
        return f"{health.get('errors_last_hour')} errors in the last hour"
    stuck = conn.execute(
        "SELECT id FROM items WHERE tick_count > ? LIMIT 1", (loop.STUCK_TICKS,)
    ).fetchone()
    if stuck:
        return f"item {stuck['id']} stuck past the loop's own park rule"
    if int(health.get("tokens_today", 0) or 0) >= TOKEN_CEILING:
        return f"daily token ceiling reached ({health.get('tokens_today')})"
    return None


def run_once() -> str | None:
    """One watchdog pass: evaluate and, on a trip, write the inert flag.
    Never clears an existing flag — resume is the owner's verb."""
    from . import ledger

    conn = ledger.connect()
    try:
        reason = evaluate(conn, loop.read_health())
    finally:
        conn.close()
    if reason is not None and not loop.inert_path().exists():
        loop.inert_path().parent.mkdir(parents=True, exist_ok=True)
        loop.inert_path().write_text(f"tripped: {reason}")
    return reason
