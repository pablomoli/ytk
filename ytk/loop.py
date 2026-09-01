"""The curator loop (#197 P5): the single writer of ledger transitions.

Hosted as one worker thread in the hub process. Surfaces insert event rows
and nudge; the loop advances items, runs the idle sweep, and writes
loop-health.json each tick for the out-of-process watchdog. The inert flag
is written by the watchdog and cleared only by `ytk loop resume`.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

# Stated guesses (spec, The loop), re-sized from the activity table later.
TICK_MAX_ITEMS = 10
TICK_MAX_SECONDS = 600
LEASE_MINUTES = 15


def health_path() -> Path:
    env = os.environ.get("YTK_LOOP_HEALTH")
    return Path(env) if env else Path.home() / ".ytk" / "loop-health.json"


def kill_path() -> Path:
    env = os.environ.get("YTK_LOOP_KILL")
    return Path(env) if env else Path.home() / ".ytk" / "loop.kill"


def inert_path() -> Path:
    env = os.environ.get("YTK_LOOP_INERT")
    return Path(env) if env else Path.home() / ".ytk" / "loop.inert"


def read_health() -> dict[str, Any]:
    try:
        loaded: object = json.loads(health_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    typed = cast("dict[str, Any]", loaded)
    return dict(typed)


def write_health(**fields: Any) -> None:
    """Merge-write: each writer touches only its own fields, so the tick and
    the sweep can stamp independently."""
    merged = read_health() | fields
    path = health_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=1))


# ---------------------------------------------------------------------------
# Tick: one advanceable item at a time, single writer of transitions
# ---------------------------------------------------------------------------

# Last non-null to_state per item; NULL lease or an expired one is pickable.
_STATE_CTE = """
WITH state AS (
    SELECT item_id, to_state FROM (
        SELECT item_id, to_state,
               row_number() OVER (PARTITION BY item_id ORDER BY id DESC) AS rn
        FROM activity WHERE to_state IS NOT NULL
    ) WHERE rn = 1
)
"""

_UNLEASED = "(items.lease_until IS NULL OR items.lease_until < :now)"


@dataclass
class Pick:
    item_id: int
    action: str  # "answer" | "read" | "advance"
    answer_id: int | None = None


@dataclass
class TickStats:
    advanced: int = 0
    errors: int = 0
    stopped: str = ""  # "idle" | "budget" | "inert"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def next_advanceable(conn: sqlite3.Connection) -> Pick | None:
    """Priority per spec: answers first (answer order), then items already at
    answered, then captures newest first, then read-with-take. Parked retries
    are the sweep's duty, not the tick selector's."""
    now = {"now": _now()}
    row = conn.execute(
        _STATE_CTE
        + """
        SELECT answers.id AS answer_id, asks.item_id FROM answers
        JOIN asks ON asks.id = answers.ask_id
        JOIN state ON state.item_id = asks.item_id
        JOIN items ON items.id = asks.item_id
        WHERE state.to_state IN ('asking', 'parked')
          -- an answer applies only to the item's latest ask; a consumed
          -- answer to a superseded ask must never re-apply (live catch)
          AND asks.id = (SELECT max(a2.id) FROM asks a2 WHERE a2.item_id = asks.item_id)
          AND """
        + _UNLEASED
        + " ORDER BY answers.id LIMIT 1",
        now,
    ).fetchone()
    if row:
        return Pick(item_id=row["item_id"], action="answer", answer_id=row["answer_id"])
    row = conn.execute(
        _STATE_CTE
        + """
        SELECT items.id FROM items JOIN state ON state.item_id = items.id
        WHERE state.to_state = 'answered' AND """
        + _UNLEASED
        + " ORDER BY items.id LIMIT 1",
        now,
    ).fetchone()
    if row:
        return Pick(item_id=row["id"], action="advance")
    row = conn.execute(
        _STATE_CTE
        + """
        SELECT items.id FROM items JOIN state ON state.item_id = items.id
        WHERE state.to_state = 'captured' AND """
        + _UNLEASED
        + " ORDER BY items.captured_at DESC LIMIT 1",
        now,
    ).fetchone()
    if row:
        return Pick(item_id=row["id"], action="read")
    row = conn.execute(
        _STATE_CTE
        + """
        SELECT items.id FROM items JOIN state ON state.item_id = items.id
        WHERE state.to_state = 'read' AND """
        + _UNLEASED
        + """
          AND EXISTS (SELECT 1 FROM takes WHERE takes.item_id = items.id)
        ORDER BY items.id LIMIT 1""",
        now,
    ).fetchone()
    if row:
        return Pick(item_id=row["id"], action="advance")
    return None


def apply_answer(conn: sqlite3.Connection, item_id: int, answer_id: int) -> None:
    """The owner's decision becomes the transition (asking -> answered or
    dropped). Written by the loop thread; the actor on record is the owner,
    who made the call."""
    from . import ledger

    row = conn.execute(
        """
        SELECT answers.choice, answers.text, answers.ask_id FROM answers
        WHERE answers.id = ?
        """,
        (answer_id,),
    ).fetchone()
    to_state = "dropped" if row["choice"] == "drop" else "answered"
    ledger.insert_activity(
        conn,
        item_id,
        actor="owner",
        action="answer",
        from_state=ledger.item_state(conn, item_id),
        to_state=to_state,
        reason=row["choice"],
        detail=json.dumps({"ask_id": row["ask_id"], "text": row["text"]}) if row["text"] else None,
    )


def lease(conn: sqlite3.Connection, item_id: int) -> bool:
    """Take the lease BEFORE the side effect (spec: crash mid-transition).
    Compare-and-set on an unleased row; the loser of a race gets False."""
    until = (datetime.now(UTC) + timedelta(minutes=LEASE_MINUTES)).isoformat()
    cur = conn.execute(
        """
        UPDATE items SET lease_until = ?, tick_count = tick_count + 1
        WHERE id = ? AND (lease_until IS NULL OR lease_until < ?)
        """,
        (until, item_id, _now()),
    )
    conn.commit()
    return cur.rowcount > 0


def clear_lease(conn: sqlite3.Connection, item_id: int, *, state_changed: bool) -> None:
    """A state change releases the item and resets its stuck counter. No
    change keeps the lease so the selector cannot hot-loop on the item; the
    lease expires on its own and the verb re-runs (verbs are idempotent)."""
    if state_changed:
        conn.execute("UPDATE items SET lease_until = NULL, tick_count = 0 WHERE id = ?", (item_id,))
        conn.commit()


# Spec, Stuck and drift: 3 picks without a state change parks the item.
STUCK_TICKS = 3


def _maybe_park_stuck(conn: sqlite3.Connection, item_id: int) -> None:
    from . import ledger

    row = conn.execute("SELECT tick_count FROM items WHERE id = ?", (item_id,)).fetchone()
    if row["tick_count"] < STUCK_TICKS:
        return
    ledger.insert_activity(
        conn,
        item_id,
        actor="loop",
        action="park",
        from_state=ledger.item_state(conn, item_id),
        to_state="parked",
        reason="stuck",
    )
    conn.execute("UPDATE items SET lease_until = NULL, tick_count = 0 WHERE id = ?", (item_id,))
    conn.commit()


def _hour_ago() -> str:
    return (datetime.now(UTC) - timedelta(hours=1)).isoformat()


def _utc_midnight() -> str:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _health_numbers(conn: sqlite3.Connection) -> dict[str, Any]:
    """Measured from the activity table each tick; the watchdog reads the
    file so a wedged loop still shows its last honest numbers."""
    errors = conn.execute(
        "SELECT count(*) AS n FROM activity WHERE action = 'loop-error' AND at >= ?",
        (_hour_ago(),),
    ).fetchone()["n"]
    rate_limited = conn.execute(
        """
        SELECT count(*) AS n FROM activity
        WHERE action = 'loop-error' AND at >= ? AND reason LIKE '%rate%limit%'
        """,
        (_hour_ago(),),
    ).fetchone()["n"]
    tokens = conn.execute(
        "SELECT coalesce(sum(tokens), 0) AS n FROM activity WHERE at >= ?",
        (_utc_midnight(),),
    ).fetchone()["n"]
    return {
        "errors_last_hour": int(errors),
        "rate_limit_hits_last_hour": int(rate_limited),
        "tokens_today": int(tokens),
        "inert": inert_path().exists(),
    }


# What the digest strip shows while a verb runs (#199). Stale past the
# lease window means the loop died mid-verb; render nothing rather than
# a forever-growing elapsed.
_WORKING_VERBS = {
    "read": "reading",
    "answer": "applying answer to",
    "advance": "enriching",
    "enrich": "enriching",
    "checks": "checking",
    "grade": "grading",
    "land": "landing",
    "connect": "connecting",
}
# An error older than this is history, not news; the activity table keeps it.
ERROR_SURFACE_MINUTES = 15


_INITIAL_STAGE = {"read": "read", "answer": "answer", "advance": "enrich"}


def _stamp_working(conn: sqlite3.Connection, pick: Pick) -> None:
    row = conn.execute(
        "SELECT title, payload_ref FROM items WHERE id = ?", (pick.item_id,)
    ).fetchone()
    title = (row["title"] if row and row["title"] else None) or f"item {pick.item_id}"
    thumbnail = None
    if row and row["payload_ref"]:
        try:
            loaded: object = json.loads(Path(row["payload_ref"]).read_text())
            if isinstance(loaded, dict):
                thumbnail = cast("dict[str, Any]", loaded).get("thumbnail")
        except (OSError, ValueError):
            thumbnail = None
    write_health(
        working_on={
            "item_id": pick.item_id,
            "action": pick.action,
            "title": title,
            "thumbnail": thumbnail,
            "started_at": _now(),
            "stage": {"key": _INITIAL_STAGE.get(pick.action, pick.action), "detail": None},
        }
    )


def stamp_stage(key: str, detail: str | None = None) -> None:
    """Narrate the verb's progress into the health json. Called by the verbs
    (enricher rounds, grader layers, landing, connect) from the loop thread;
    a no-op when nothing is being worked on."""
    raw = read_health().get("working_on")
    if not isinstance(raw, dict):
        return
    w = dict(cast("dict[str, Any]", raw))
    w["stage"] = {"key": key, "detail": detail}
    write_health(working_on=w)


def _working_fragment() -> tuple[bool, str, dict[str, Any] | None]:
    raw = read_health().get("working_on")
    if not isinstance(raw, dict):
        return False, "", None
    w = cast("dict[str, Any]", raw)
    started_raw = w.get("started_at")
    if not isinstance(started_raw, str):
        return False, "", None
    try:
        started = datetime.fromisoformat(started_raw)
    except ValueError:
        return False, "", None
    elapsed = (datetime.now(UTC) - started).total_seconds()
    if elapsed < 0 or elapsed > LEASE_MINUTES * 60:
        return False, "", None
    stage = w.get("stage")
    key = str(cast("dict[str, Any]", stage).get("key")) if isinstance(stage, dict) else None
    verb = _WORKING_VERBS.get(key or str(w.get("action")), "working on")
    return True, f"{verb} {w.get('title')!s} · {int(elapsed)}s", dict(w)


def _recent_error() -> dict[str, Any] | None:
    raw = read_health().get("last_error")
    if not isinstance(raw, dict):
        return None
    err = cast("dict[str, Any]", raw)
    at = err.get("at")
    if not isinstance(at, str):
        return None
    try:
        seen = datetime.fromisoformat(at)
    except ValueError:
        return None
    if (datetime.now(UTC) - seen).total_seconds() > ERROR_SURFACE_MINUTES * 60:
        return None
    return dict(err)


def _answered_connections(conn: sqlite3.Connection, item_id: int) -> bool:
    """True when the item's LATEST ask is a connections ask with an answer.
    Latest-only, same rule as the pending-answer selector (P5 live catch)."""
    row = conn.execute(
        """
        SELECT asks.kind, answers.id AS answer_id FROM asks
        LEFT JOIN answers ON answers.ask_id = asks.id
        WHERE asks.item_id = ? ORDER BY asks.id DESC LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    return bool(row and row["kind"] == "connections" and row["answer_id"] is not None)


def tick_once(conn: sqlite3.Connection) -> TickStats:
    """One tick: advance items until nothing is advanceable or the budget is
    hit. The only caller in production is the loop thread — every transition
    in the process funnels through here (single writer)."""
    from . import curator, evidence, ledger

    stats = TickStats()
    started = time.monotonic()
    while True:
        if inert_path().exists():
            stats.stopped = "inert"
            break
        if stats.advanced + stats.errors >= TICK_MAX_ITEMS:
            stats.stopped = "budget"
            break
        if time.monotonic() - started > TICK_MAX_SECONDS:
            stats.stopped = "budget"
            break
        pick = next_advanceable(conn)
        if pick is None:
            stats.stopped = "idle"
            break
        if not lease(conn, pick.item_id):
            continue
        before = ledger.item_state(conn, pick.item_id)
        _stamp_working(conn, pick)
        try:
            if pick.action == "answer":
                assert pick.answer_id is not None
                apply_answer(conn, pick.item_id, pick.answer_id)
            elif pick.action == "read":
                from . import gatherers  # noqa: F401  # pyright: ignore[reportUnusedImport]

                rr = evidence.read_item(conn, pick.item_id, actor="loop")
                if rr.error:
                    raise RuntimeError(rr.error)
            elif _answered_connections(conn, pick.item_id):
                # An answered connections ask must not fall into
                # advance_item, which would re-enrich a kept item (P6).
                from . import connect

                connect.apply_links(conn, pick.item_id, actor="loop")
            else:
                curator.advance_item(conn, pick.item_id, actor="loop")
        except Exception as exc:
            stats.errors += 1
            write_health(
                last_error={"at": _now(), "item_id": pick.item_id, "reason": str(exc)[:200]}
            )
            ledger.insert_activity(
                conn,
                pick.item_id,
                actor="loop",
                action="loop-error",
                reason=str(exc)[:300],
            )
            _maybe_park_stuck(conn, pick.item_id)
            continue
        finally:
            write_health(working_on=None)
        after = ledger.item_state(conn, pick.item_id)
        changed = after != before
        clear_lease(conn, pick.item_id, state_changed=changed)
        if not changed:
            _maybe_park_stuck(conn, pick.item_id)
        stats.advanced += 1
    write_health(
        last_tick_at=_now(),
        items_advanced=stats.advanced,
        errors=stats.errors,
        **_health_numbers(conn),
    )
    return stats


# ---------------------------------------------------------------------------
# Idle sweep: staleness-checked, coalesces missed runs across laptop sleep
# ---------------------------------------------------------------------------

SWEEP_HOURS = 6
# Quality asks wait for the owner but not forever in the digest's face
# (spec, Asks: "an unanswered ask parks after a window"). Guess until the
# presented_at instrument yields real answer latency.
ASK_PARK_DAYS = 14
QUALITY_PARK_KINDS = ("transcript junk", "blind item", "grader bounce, twice")
# Only read-gate kinds are retryable; a bounce ask waits for the owner.
RETRY_KINDS = ("transcript junk", "blind item")
RETRY_COOLDOWN_HOURS = 24
RETRY_MAX_PER_SWEEP = 10


@dataclass
class SweepStats:
    parked: int = 0
    retried: int = 0
    recovered: int = 0
    expired: int = 0


def sweep_due() -> bool:
    last = read_health().get("last_sweep_at")
    if not isinstance(last, str) or not last:
        return True
    return last < (datetime.now(UTC) - timedelta(hours=SWEEP_HOURS)).isoformat()


def _open_asks(conn: sqlite3.Connection, kinds: tuple[str, ...]) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in kinds)
    return conn.execute(
        f"""
        SELECT asks.id, asks.item_id, asks.kind, asks.proposal, asks.created_at
        FROM asks
        LEFT JOIN answers ON answers.ask_id = asks.id
        LEFT JOIN outbox ON outbox.ask_id = asks.id
        WHERE answers.id IS NULL AND outbox.answered_at IS NULL
          AND asks.kind IN ({placeholders})
        """,
        kinds,
    ).fetchall()


def sweep(conn: sqlite3.Connection) -> SweepStats:
    """The three P5 duties, in order: park stale quality asks, retry parked
    read-gate failures, expire the intent window. The reflex sweep lands
    after P5 (owner decision 2026-08-31); it would slot in here."""
    from . import evidence, ledger

    stats = SweepStats()

    park_before = (datetime.now(UTC) - timedelta(days=ASK_PARK_DAYS)).isoformat()
    for ask in _open_asks(conn, QUALITY_PARK_KINDS):
        if ask["created_at"] >= park_before:
            continue
        if ledger.item_state(conn, ask["item_id"]) != "asking":
            continue
        ledger.insert_activity(
            conn,
            ask["item_id"],
            actor="sweep",
            action="park",
            from_state="asking",
            to_state="parked",
            reason=f"ask unanswered past {ASK_PARK_DAYS}d",
        )
        stats.parked += 1

    # A parked connections ask writes "none" (spec, Asks): the note is live
    # either way, so the item returns to kept instead of stranding at asking.
    for ask in _open_asks(conn, ("connections",)):
        if ask["created_at"] >= park_before:
            continue
        if ledger.item_state(conn, ask["item_id"]) != "asking":
            continue
        conn.execute(
            "UPDATE outbox SET answered_at = ? WHERE ask_id = ?", (ledger.now(), ask["id"])
        )
        ledger.insert_activity(
            conn,
            ask["item_id"],
            actor="sweep",
            action="connect-none",
            from_state="asking",
            to_state="kept",
            reason=f"connections ask unanswered past {ASK_PARK_DAYS}d: none written",
        )
        stats.expired += 1

    cooldown = (datetime.now(UTC) - timedelta(hours=RETRY_COOLDOWN_HOURS)).isoformat()
    for ask in _open_asks(conn, RETRY_KINDS):
        if stats.retried >= RETRY_MAX_PER_SWEEP:
            break
        item_id = ask["item_id"]
        if ledger.item_state(conn, item_id) != "parked":
            continue
        recent = conn.execute(
            """
            SELECT 1 FROM activity
            WHERE item_id = ? AND action = 'retry-read' AND at >= ?
            LIMIT 1
            """,
            (item_id, cooldown),
        ).fetchone()
        if recent:
            continue
        stats.retried += 1
        if evidence.retry_parked(conn, item_id, actor="sweep"):
            stats.recovered += 1

    for ask in _open_asks(conn, ("intent missing",)):
        proposal = cast("dict[str, Any]", json.loads(ask["proposal"]))
        window = int(proposal.get("window_days", 7))
        expire_before = (datetime.now(UTC) - timedelta(days=window)).isoformat()
        if ask["created_at"] >= expire_before:
            continue
        item_id = ask["item_id"]
        if ledger.item_state(conn, item_id) not in ("asking", "parked"):
            continue
        item = conn.execute("SELECT url, title FROM items WHERE id = ?", (item_id,)).fetchone()
        conn.execute(
            "UPDATE outbox SET answered_at = ? WHERE ask_id = ?", (ledger.now(), ask["id"])
        )
        ledger.insert_activity(
            conn,
            item_id,
            actor="sweep",
            action="expire",
            from_state=ledger.item_state(conn, item_id),
            to_state="dropped",
            reason="intent window expired",
            detail=json.dumps(
                {
                    "url": item["url"],
                    "title": item["title"],
                    "non_answer": "intent window expired",
                    "ask_id": ask["id"],
                }
            ),
        )
        stats.expired += 1

    write_health(last_sweep_at=_now())
    return stats


# ---------------------------------------------------------------------------
# Thread driver and the watch line
# ---------------------------------------------------------------------------

POLL_SECONDS = 60


def run_loop(
    wake: threading.Event, stop: threading.Event, *, poll_seconds: float = POLL_SECONDS
) -> None:
    """Thread body: work, then wait for a wake or the poll timeout. Work runs
    first so start-up drains anything that landed while the hub was down; the
    timeout IS the lost-nudge net (the selector is one cheap SELECT when
    idle). Sweep staleness is checked every cycle, so laptop sleep coalesces
    missed sweeps instead of queuing them."""
    from . import ledger

    conn = ledger.connect()
    try:
        # A crash mid-transition leaves leases no thread owns; the hub lock
        # (#38) guarantees one loop, so every lease at start is an orphan.
        conn.execute("UPDATE items SET lease_until = NULL WHERE lease_until IS NOT NULL")
        conn.commit()
    finally:
        conn.close()

    while not stop.is_set():
        conn = ledger.connect()
        try:
            if sweep_due():
                sweep(conn)
            tick_once(conn)
        except Exception:
            logging.getLogger("ytk.loop").exception("loop cycle failed")
        finally:
            conn.close()
        wake.wait(poll_seconds)
        wake.clear()


def health_line() -> dict[str, Any]:
    """The one-liner every watch surface renders (digest, ytk loop status)."""
    if inert_path().exists():
        reason = inert_path().read_text().strip() or "no reason recorded"
        return {"ok": False, "working": False, "line": f"inert — {reason}; run `ytk loop resume`"}
    working, fragment, working_on = _working_fragment()
    err = _recent_error()
    if working:
        out: dict[str, Any] = {
            "ok": True,
            "working": True,
            "line": fragment,
            "working_on": working_on,
        }
        if err:
            out["last_error"] = err
        return out
    h = read_health()
    last = h.get("last_tick_at")
    if not last:
        return {"ok": True, "working": False, "line": "never ticked"}
    line = (
        f"last tick {str(last)[11:16]}Z · {h.get('items_advanced', 0)} advanced · "
        f"{h.get('errors_last_hour', 0)} errors · {h.get('tokens_today', 0):,} tokens today"
    )
    out = {"ok": True, "working": False, "line": line}
    if err:
        out["last_error"] = err
    return out
