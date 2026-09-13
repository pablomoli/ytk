"""The headless surface (#212, P8 pulled forward): the verbs a terminal, a
chat session or the MCP server use to read one item's packet and trail and
to answer an ask. One module; the CLI and MCP wrappers carry no logic.

Every verb reads what the loop wrote (views, attempts, drafts, the ledger).
The only write is an answer row, an event the loop turns into a transition
on its next tick; the verb nudges it and never advances anything itself.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from . import attempt as attempt_mod
from . import ledger
from . import view as view_mod


def _item_row(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise LookupError(f"no item {item_id}")
    return row


def _title(row: sqlite3.Row) -> str:
    """items.title is filled at read; older rows and bare captures fall back
    to the bundle's title, then the url (the ask cards do the same)."""
    if row["title"]:
        return str(row["title"])
    try:
        ref = row["payload_ref"]
    except IndexError:
        ref = None
    if ref and Path(ref).exists():
        try:
            loaded: object = json.loads(Path(ref).read_text())
        except (OSError, ValueError):
            loaded = None
        if isinstance(loaded, dict):
            title = cast("dict[str, Any]", loaded).get("title")
            if isinstance(title, str) and title:
                return title
    return str(row["url"])


def _open_ask(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT asks.* FROM asks LEFT JOIN answers ON answers.ask_id = asks.id
        WHERE asks.item_id = ? AND answers.id IS NULL ORDER BY asks.id DESC LIMIT 1
        """,
        (item_id,),
    ).fetchone()


def _proposal(row: sqlite3.Row) -> dict[str, Any]:
    try:
        loaded: object = json.loads(row["proposal"])
    except ValueError:
        return {}
    return dict(cast("dict[str, Any]", loaded)) if isinstance(loaded, dict) else {}


def _ask_line(row: sqlite3.Row, proposal: dict[str, Any]) -> str:
    opts = " | ".join(str(o) for o in cast("list[object]", proposal.get("options") or []))
    packet = ""
    if proposal.get("view_hash"):
        packet = f" · packet {proposal['view_hash']} attempt {proposal.get('attempt')}"
    return (
        f"ask {row['id']} · {row['kind']} · options {opts}{packet} · since {row['created_at'][:16]}"
    )


def _budget_line(v: view_mod.View) -> str:
    b = v.budget
    shown = ", ".join(u["id"] for u in v.shown)
    line = (
        f"packet {v.view_hash} · budget frames_shown {b.get('frames_shown')}, "
        f"cap {b.get('evidence_cap_chars')}, sheet {b.get('sheet')} · shown {shown or 'nothing'}"
    )
    if v.openable:
        line += " · in the box " + ", ".join(u["id"] for u in v.openable)
    if v.not_shown:
        line += " · not shown: " + "; ".join(v.not_shown)
    return line


def _attempt_line(a: attempt_mod.Attempt) -> str:
    verdict = a.verdict_out or {}
    if not verdict:
        outcome = "open"
    elif verdict.get("passed"):
        outcome = f"{verdict.get('layer', 'model')} pass"
    else:
        bounces = cast("list[dict[str, Any]]", verdict.get("bounces") or [])
        first = bounces[0].get("check") if bounces else "ungrounded claim"
        outcome = f"{verdict.get('layer', 'model')} bounce: {first}"
    return f"attempt {a.n} · findings in {len(a.findings_in)} · {outcome}"


def _trail(conn: sqlite3.Connection, item_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT at, actor, action, to_state, model, tokens, duration_ms, reason FROM activity "
        "WHERE item_id = ? ORDER BY id",
        (item_id,),
    ).fetchall()
    out: list[str] = []
    for r in rows:
        bits = [r["at"][11:19], r["actor"], r["action"]]
        if r["to_state"]:
            bits.append(f"-> {r['to_state']}")
        if r["reason"]:
            bits.append(str(r["reason"])[:90])
        if r["model"]:
            cost = f"{r['model']}"
            if r["tokens"]:
                cost += f" {r['tokens']} tok"
            if r["duration_ms"]:
                cost += f" {r['duration_ms'] / 1000:.1f}s"
            bits.append(cost)
        out.append("  " + " · ".join(bits))
    return out


def item(conn: sqlite3.Connection, item_id: int) -> str:
    """One item: title, state, packet, attempts, open ask, spend, trail."""
    from .curator import ITEM_CALL_CAP, model_calls

    row = _item_row(conn, item_id)
    state = ledger.item_state(conn, item_id) or "captured"
    lines = [
        f"item {item_id}: {_title(row)}",
        f"source {row['source']} · state {state} · {row['url']}",
    ]
    v = view_mod.latest_view(item_id)
    lines.append(_budget_line(v) if v else "no packet yet")
    for a in attempt_mod.attempts_for(item_id):
        lines.append(_attempt_line(a))
    ask = _open_ask(conn, item_id)
    if ask is not None:
        lines.append(_ask_line(ask, _proposal(ask)))
    lines.append(f"calls {model_calls(conn, item_id)} of {ITEM_CALL_CAP}")
    lines.append(f"page /packet/{item_id}")
    lines.append("trail:")
    lines += _trail(conn, item_id)
    return "\n".join(lines)


def ask_list(conn: sqlite3.Connection) -> str:
    """Every unanswered ask, oldest first."""
    # Unanswered, and the item is still asking: an ask the loop superseded
    # (item 756 carried a September 1 bounce ask after it had landed) is
    # not answerable, and answering it would poke a kept item.
    rows = conn.execute(
        """
        SELECT asks.*, items.title, items.url, items.payload_ref FROM asks
        JOIN items ON items.id = asks.item_id
        LEFT JOIN answers ON answers.ask_id = asks.id
        WHERE answers.id IS NULL
          AND (SELECT to_state FROM activity WHERE item_id = asks.item_id
               AND to_state IS NOT NULL ORDER BY id DESC LIMIT 1) = 'asking'
        ORDER BY asks.id
        """
    ).fetchall()
    if not rows:
        return "no open asks"
    out: list[str] = []
    for r in rows:
        out.append(f"{_ask_line(r, _proposal(r))} · item {r['item_id']} {_title(r)}")
    return "\n".join(out)


def ask_answer(
    conn: sqlite3.Connection,
    ask_id: int,
    choice: str,
    text: str | None = None,
    *,
    surface: str = "cli",
) -> str:
    """Record the owner's answer and wake the loop. A repeat is a no-op."""
    from . import asks, wake

    row = conn.execute("SELECT * FROM asks WHERE id = ?", (ask_id,)).fetchone()
    if row is None:
        raise LookupError(f"no ask {ask_id}")
    options = [str(o) for o in cast("list[object]", _proposal(row).get("options") or [])]
    if options and choice not in options:
        return f"ask {ask_id} offers {' | '.join(options)}; '{choice}' is not one of them"
    answer_id = asks.answer_ask(conn, ask_id, choice=choice, text=text, surface=surface)
    if answer_id is None:
        return f"ask {ask_id} was already answered"
    woke = wake.nudge_loop()
    tail = "loop woken" if woke else "hub not reachable; the 60 s poll picks it up"
    return f"ask {ask_id} answered '{choice}' for item {row['item_id']} · {tail}"


def _view_for(item_id: int, attempt: int | None) -> view_mod.View | None:
    if attempt is not None:
        a = attempt_mod.load_attempt(item_id, attempt)
        if a is None:
            return None
        return view_mod.view_by_hash(item_id, a.view_hash)
    return view_mod.latest_view(item_id)


def view_show(
    conn: sqlite3.Connection, item_id: int, attempt: int | None = None, *, full: bool = False
) -> str:
    """The packet an attempt read (or the latest one): budget, units, and
    with `full` the rendered bytes themselves."""
    _item_row(conn, item_id)
    v = _view_for(item_id, attempt)
    if v is None:
        return f"item {item_id}: no packet" + (f" for attempt {attempt}" if attempt else "")
    lines = [_budget_line(v), f"bundle {v.bundle_path} ({v.bundle_hash}) · tokenizer {v.tokenizer}"]
    if v.gaps:
        lines.append("gaps: " + "; ".join(v.gaps))
    lines.append(f"rendered {len(v.rendered)} chars, {len(v.transcript)} transcript lines")
    if full:
        lines += ["", v.rendered]
    return "\n".join(lines)


def grade(
    conn: sqlite3.Connection, item_id: int, attempt: int | None = None, *, model: bool = False
) -> str:
    """Re-run the grader on an attempt's draft without writing a row: the
    deterministic layer always, the model layer only when asked (one Opus
    call)."""
    from . import grader, rubric
    from .curator import latest_take, tag_vocab
    from .enricher import EnrichmentV2, draft_path

    _item_row(conn, item_id)
    n = attempt
    if n is None:
        row = conn.execute(
            "SELECT count(*) AS n FROM activity WHERE item_id = ? AND action = 'enrich'", (item_id,)
        ).fetchone()
        n = int(row["n"])
    a = attempt_mod.load_attempt(item_id, n)
    v = view_mod.view_by_hash(item_id, a.view_hash) if a else view_mod.latest_view(item_id)
    path = draft_path(item_id, n)
    if v is None or not path.exists():
        return f"item {item_id}: no draft or packet for attempt {n}"
    draft = EnrichmentV2.model_validate_json(Path(path).read_text())
    take = latest_take(conn, item_id)
    bounces = grader.deterministic_checks(
        draft,
        v,
        vocab=tag_vocab(),
        take_kind=take["kind"] if take else None,
        take_text=take["text"] if take else None,
    )
    lines = [f"attempt {n} · packet {v.view_hash} · deterministic layer:"]
    lines += [f"  bounce {b.check}: {b.detail}" for b in bounces] or ["  pass"]
    if bounces or not model:
        if not bounces and not model:
            lines.append("model layer not run (pass --model to spend one Opus call)")
        return "\n".join(lines)
    header = a or attempt_mod.Attempt(
        item_id=item_id, n=n, view_hash=v.view_hash, take=None, previous_draft=None
    )
    verdict, res = grader.grade_model(draft, v, header, rubric.load().text)
    lines.append(
        f"model layer ({res.model}, {res.tokens} tok): {'pass' if verdict.passed else 'bounce'}"
    )
    lines += [f"  {b.check}: {b.detail}" for b in verdict.bounces]
    lines += [
        f"  spot-check {'ok' if s.grounded else 'UNGROUNDED'}: {s.claim[:80]}"
        for s in verdict.spot_checks
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The packet page (#213): where a packet is at an instant, reconstructed from
# the ledger, the attempt files and the answers table. Server-side only; the
# hub route and `ytk item` read the same dicts.

STATIONS = ("runner", "proctor", "student", "spell-checker", "teacher", "librarian", "owner")
MODEL_STATIONS = frozenset({"student", "spell-checker", "teacher", "librarian"})
FILED = "filed"
# Grader rows whose reason opens with one of these came from the deterministic
# layer; the spell-checker, not the teacher, made that call.
_DETERMINISTIC = (
    "bounce: concept grounding",
    "bounce: key moment",
    "bounce: tag",
    "bounce: banned",
)
_TERMINAL = frozenset({"kept", "connected", "kept-unlabeled"})
_UNIT = re.compile(r"t:\d+(?:-\d+)?|frame:\d+")


def _ts(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Station:
    name: str
    since: datetime
    note: str

    @property
    def model(self) -> bool:
        return self.name in MODEL_STATIONS


@dataclass
class History:
    """Everything station_at needs for one item, loaded once."""

    item_id: int
    rows: list[dict[str, Any]]
    attempts: list[attempt_mod.Attempt]
    # (asked_at, answered_at, choice) for every answered ask, by ask id
    answers: list[tuple[datetime, datetime, str]]


def history(conn: sqlite3.Connection, item_id: int) -> History:
    rows = [
        dict(r)
        for r in conn.execute("SELECT * FROM activity WHERE item_id = ? ORDER BY id", (item_id,))
    ]
    answers = [
        (_ts(r["created_at"]), _ts(r["at"]), str(r["choice"]))
        for r in conn.execute(
            "SELECT a.created_at, n.at, n.choice FROM asks a JOIN answers n ON n.ask_id = a.id "
            "WHERE a.item_id = ? ORDER BY a.id",
            (item_id,),
        )
    ]
    return History(item_id, rows, attempt_mod.attempts_for(item_id), answers)


def station_at(h: History, t: datetime, *, working: dict[str, Any] | None = None) -> Station | None:
    """Where the packet is at `t` and since when. None before the item has any
    row (a grandfathered note is not a packet). The four cases that were wrong
    until measured (docs/design/packet-page/README.md): an answered ask sits at
    the proctor until pickup; a connect with nothing argued files the item; an
    open attempt is the student's, then the spell-checker's until the grade
    row, and the teacher's for the grade's duration; the live pad counts every
    model call. `working` is the loop's working_on record for this item, the
    only witness of the librarian while the connect row has not landed."""
    rows = [r for r in h.rows if _ts(r["at"]) <= t]
    if not rows or all(r["action"] == "grandfather" for r in rows):
        return None
    last = rows[-1]
    later = [r for r in h.rows if _ts(r["at"]) > t]
    at = _ts(last["at"])
    for a in h.attempts:
        if a.opened_at and _ts(a.opened_at) <= t and (a.closed_at is None or t < _ts(a.closed_at)):
            # The attempt stays open until the verdict; the writer's row is
            # what hands the packet from the student to the checkers.
            written = any(
                r["actor"] == "enricher" and (r["reason"] or "").startswith(f"attempt {a.n}")
                for r in rows
            )
            if not written:
                return Station("student", _ts(a.opened_at), f"attempt {a.n}")
    if last["actor"] == "enricher":
        grade = next((r for r in later if r["actor"] == "grader" and r["action"] == "grade"), None)
        if grade and grade["duration_ms"]:
            start = _ts(grade["at"]) - timedelta(milliseconds=grade["duration_ms"])
            if start <= t:
                return Station("teacher", start, "marking")
        return Station("spell-checker", at, "checking")
    st = last["to_state"]
    if st == "asking":
        ans = next(
            (x for x in h.answers if x[0] <= t and x[1] <= t and x[0] >= at - timedelta(seconds=2)),
            None,
        )
        if ans:
            return Station("proctor", ans[1], "answered, waiting")
        kind = ""
        for r in reversed(rows):
            if r["action"] == "ask":
                kind = (r["reason"] or "").split(":")[0].strip().lower()
                break
        if kind.startswith("why this"):
            kind = "intent missing"
        return Station("owner", at, "ask · " + kind[:32])
    if st == "answered":
        return Station("proctor", at, "answered, waiting")
    if st in ("captured", "read"):
        return Station("runner", at, str(st))
    if st == "enriched":
        return Station("proctor", at, "passed, filing")
    if last["actor"] == "connect" or last["action"] == "connect-none":
        return Station(FILED, at, "kept, no links")
    if st == "kept":
        if working and working.get("action") == "connect" and working.get("started_at"):
            return Station("librarian", _ts(str(working["started_at"])), "arguing links")
        nxt = next((r for r in later if r["actor"] == "connect"), None)
        if nxt and nxt["duration_ms"]:
            start = _ts(nxt["at"]) - timedelta(milliseconds=nxt["duration_ms"])
            if start <= t:
                return Station("librarian", start, "arguing links")
        if nxt:
            return Station("proctor", at, "kept, connect pending")
        return Station(FILED, at, "kept")
    if st == "connected":
        return Station(FILED, at, "linked")
    if last["action"] == "loop-error":
        return Station("proctor", at, "error, retrying")
    if last["actor"] == "grader":
        return Station("student", at, "next round")
    return Station("proctor", at, str(st or ""))


def _station_dict(s: Station | None) -> dict[str, Any] | None:
    if s is None:
        return None
    return {"name": s.name, "since": s.since.isoformat(), "note": s.note, "model": s.model}


def _calls(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Model calls to date and the ink they spent: every row that reports tokens."""
    calls = [r for r in rows if r["tokens"] is not None]
    return len(calls), sum(int(r["tokens"] or 0) for r in calls)


def _rounds(rows: list[dict[str, Any]], s: Station | None) -> int:
    n = sum(1 for r in rows if r["actor"] == "enricher")
    if s and s.name == "student" and s.note.startswith("attempt"):
        n += 1
    return n


def _working_on() -> dict[str, Any] | None:
    from . import loop as loop_mod

    raw = loop_mod.health_line().get("working_on")
    return dict(cast("dict[str, Any]", raw)) if isinstance(raw, dict) else None


def track(conn: sqlite3.Connection, t: datetime | None = None) -> dict[str, Any]:
    """Every packet in flight at `t` (default now): the four things the track
    answers, per packet. Filed packets are not listed; nothing filed is drawn."""
    t = t or datetime.now(UTC)
    working = _working_on()
    live = t >= datetime.now(UTC) - timedelta(seconds=5)
    packets: list[dict[str, Any]] = []
    items = conn.execute(
        "SELECT items.id, items.title, items.source, items.url, items.payload_ref FROM items "
        "WHERE EXISTS (SELECT 1 FROM activity WHERE item_id = items.id AND action != 'grandfather')"
    ).fetchall()
    for row in items:
        h = history(conn, row["id"])
        if live:
            last_state = next((r["to_state"] for r in reversed(h.rows) if r["to_state"]), None)
            wk = working if working and working.get("item_id") == row["id"] else None
            if last_state in _TERMINAL and not wk and h.rows[-1]["actor"] != "enricher":
                continue
        else:
            wk = None
        s = station_at(h, t, working=wk)
        if s is None or s.name == FILED:
            continue
        rows = [r for r in h.rows if _ts(r["at"]) <= t]
        calls, tokens = _calls(rows)
        packets.append(
            {
                "id": row["id"],
                "title": _title(row),
                "source": row["source"],
                "station": _station_dict(s),
                "rounds": _rounds(rows, s),
                "calls": calls,
                "tokens": tokens,
            }
        )
    packets.sort(key=lambda p: (STATIONS.index(p["station"]["name"]), p["station"]["since"]))
    return {"t": t.isoformat(), "stations": list(STATIONS), "cap": _cap(), "packets": packets}


def _cap() -> int:
    from .curator import ITEM_CALL_CAP

    return ITEM_CALL_CAP


def _who(r: dict[str, Any]) -> str:
    who = {
        "loop": "proctor",
        "operator": "runner",
        "sweep": "runner",
        "enricher": "student",
        "connect": "librarian",
        "owner": "owner",
    }.get(str(r["actor"]), str(r["actor"]))
    reason = r["reason"] or ""
    if r["actor"] == "grader":
        who = "spell-checker" if reason.startswith(_DETERMINISTIC) else "teacher"
        if r["action"] == "ask":
            who = "proctor"
    if r["action"] in ("capture", "read"):
        who = "runner"
    return who


def _trail_row(r: dict[str, Any]) -> dict[str, Any]:
    reason = r["reason"] or ""
    act = str(r["action"])
    what = {
        "ask": "ask, " + (reason.split(":")[0].lower() if reason else ""),
        "answer": reason or "answer",
        "loop-error": "error, " + (reason[:60] if reason else "loop"),
        "enrich": reason,
        "grade": reason.replace("bounce: ", "bounce, ").lower(),
        "connect": reason,
        "connect-apply": "apply links",
        "connect-none": "no links",
    }.get(act, act)
    right = (
        f"{int(r['tokens'] or 0):,} tok · {round((r['duration_ms'] or 0) / 1000)} s"
        if r["model"]
        else (r["to_state"] or "")
    )
    return {
        "at": r["at"],
        "who": _who(r),
        "what": what,
        "right": right,
        "error": act == "loop-error",
        "model": bool(r["model"]),
        "tokens": int(r["tokens"] or 0),
    }


def _cites(where: str | None) -> list[str]:
    return _UNIT.findall(where or "")


def _model_row(r: dict[str, Any] | None) -> dict[str, Any] | None:
    if r is None:
        return None
    inputs: dict[str, Any] = {}
    if r["inputs"]:
        try:
            loaded: object = json.loads(r["inputs"])
            if isinstance(loaded, dict):
                inputs = dict(cast("dict[str, Any]", loaded))
        except ValueError:
            inputs = {}
    return {
        "model": r["model"],
        "tokens": int(r["tokens"] or 0),
        "seconds": round((r["duration_ms"] or 0) / 1000),
        "at": r["at"],
        "view_hash": inputs.get("view_hash"),
    }


def _attempt_dict(a: attempt_mod.Attempt, rows: list[dict[str, Any]]) -> dict[str, Any]:
    verdict = a.verdict_out or {}
    draft: dict[str, Any] | None = None
    if a.draft_out and Path(a.draft_out).exists():
        try:
            loaded: object = json.loads(Path(a.draft_out).read_text())
        except (OSError, ValueError):
            loaded = None
        if isinstance(loaded, dict):
            d = cast("dict[str, Any]", loaded)
            draft = {
                "thesis": d.get("thesis") or "",
                "concepts": len(cast("list[object]", d.get("key_concepts") or [])),
                "insights": len(cast("list[object]", d.get("insights") or [])),
                "moments": len(cast("list[object]", d.get("key_moments") or [])),
                "tags": list(cast("list[str]", d.get("interest_tags") or [])),
            }
    writer = next(
        (
            r
            for r in rows
            if r["actor"] == "enricher" and (r["reason"] or "").startswith(f"attempt {a.n}")
        ),
        None,
    )
    marker = None
    if writer:
        marker = next(
            (
                r
                for r in rows
                if r["actor"] == "grader" and r["action"] == "grade" and r["id"] > writer["id"]
            ),
            None,
        )
    take = a.take or {}
    return {
        "n": a.n,
        "opened_at": a.opened_at,
        "closed_at": a.closed_at,
        "view_hash": a.view_hash,
        "take_kind": take.get("kind"),
        "findings": [
            {
                "check": str(f.get("check", "")).lower(),
                "where": f.get("where") or "",
                "detail": f.get("detail") or "",
            }
            for f in a.findings_in
        ],
        "passed": bool(verdict.get("passed")) if verdict else None,
        "layer": verdict.get("layer"),
        "bounces": [
            {
                "check": str(b.get("check", "")).lower(),
                "where": b.get("where") or "",
                "detail": b.get("detail") or "",
            }
            for b in cast("list[dict[str, Any]]", verdict.get("bounces") or [])
        ],
        "spots": [
            {
                "grounded": bool(s.get("grounded")),
                "where": s.get("where") or "",
                "claim": s.get("claim") or "",
            }
            for s in cast("list[dict[str, Any]]", verdict.get("spot_checks") or [])
        ],
        "draft": draft,
        "writer": _model_row(writer),
        "marker": _model_row(marker),
    }


def _view_dict(v: view_mod.View, cited: set[int]) -> dict[str, Any]:
    """The packet as the page draws it: units, budget, the transcript folded
    to its head plus a window around every cited second, the frames by url."""
    tr = v.transcript
    lines: list[dict[str, Any]] = []
    if tr:
        keep = set(range(min(14, len(tr))))
        for c in cited:
            idx = min(range(len(tr)), key=lambda i: abs(float(tr[i]["start"]) - c))
            keep.update(range(max(0, idx - 2), min(len(tr), idx + 3)))
        last = -1
        for i in sorted(keep):
            if last >= 0 and i != last + 1:
                lines.append({"fold": i - last - 1})
            hit = any(abs(float(tr[i]["start"]) - c) <= 1.5 for c in cited)
            lines.append({"s": int(float(tr[i]["start"])), "text": tr[i]["text"], "hit": hit})
            last = i
        if last < len(tr) - 1:
            lines.append({"fold": len(tr) - 1 - last})
    nframes: int | None = None
    for s in v.not_shown:
        m = re.search(r"frames \d+ to (\d+)", s)
        if m:
            nframes = int(m.group(1))
    frames = [u for u in (*v.shown, *v.openable) if u["kind"] == "frame"]
    if nframes is None:
        nframes = len(frames)
    return {
        "hash": v.view_hash,
        "bundle": v.bundle_hash,
        "source": v.source,
        "origin": v.transcript_origin,
        "duration": v.duration or (float(tr[-1]["start"]) + 2 if tr else None),
        "nlines": len(tr),
        "lines": lines,
        "shown": [u["id"] for u in v.shown],
        "openable": [u["id"] for u in v.openable],
        "not_shown": list(v.not_shown),
        "gaps": list(v.gaps),
        "budget": dict(v.budget),
        "tokenizer": v.tokenizer,
        "nframes": nframes,
        "frames": [
            {
                "id": u["id"],
                "t": u.get("t"),
                "shown": u in v.shown,
                "url": f"/api/evidence/frame/{v.item_id}/{int(u['id'][6:])}",
            }
            for u in frames
        ],
    }


def frame_path(item_id: int, n: int) -> Path | None:
    """The file behind `frame:NNN` in the item's latest packet, or None. The
    path comes from the view on disk, never from the request."""
    v = view_mod.latest_view(item_id)
    if v is None:
        return None
    uid = f"frame:{n:03d}"
    for u in (*v.shown, *v.openable):
        if u["id"] == uid and u.get("path"):
            return Path(str(u["path"]))
    return None


def packet(conn: sqlite3.Connection, item_id: int, t: datetime | None = None) -> dict[str, Any]:
    """One item's page: header, packet, every round, asks, connections, trail,
    at `t` (default now). Before `t` nothing later is shown, so a replay reads
    as the live page did then."""
    row = _item_row(conn, item_id)
    t = t or datetime.now(UTC)
    h = history(conn, item_id)
    working = _working_on()
    wk = working if working and working.get("item_id") == item_id else None
    s = station_at(h, t, working=wk)
    rows = [r for r in h.rows if _ts(r["at"]) <= t]
    attempts = [a for a in h.attempts if a.opened_at and _ts(a.opened_at) <= t]
    calls, tokens = _calls(rows)
    cap = _cap()
    v = view_mod.latest_view(item_id)
    cited: set[int] = set()
    att_dicts: list[dict[str, Any]] = []
    for a in attempts:
        d = _attempt_dict(a, rows)
        # An open round shows only what the clock has reached.
        if a.closed_at and _ts(a.closed_at) > t:
            d.update(
                {
                    "closed_at": None,
                    "passed": None,
                    "layer": None,
                    "bounces": [],
                    "spots": [],
                    "draft": None,
                    "marker": None,
                }
            )
        att_dicts.append(d)
        for x in (*d["findings"], *d["bounces"], *d["spots"]):
            for u in _cites(x["where"]):
                if u.startswith("t:"):
                    cited.add(int(u[2:].split("-")[0]))
    graded = next((d for d in reversed(att_dicts) if d["marker"]), None)
    if graded is None:
        agreement = {"status": "pending", "draft": v.view_hash if v else None, "grade": None}
    elif not graded["marker"]["view_hash"]:
        agreement = {"status": "none", "draft": graded["view_hash"], "grade": None}
    else:
        same = graded["marker"]["view_hash"] == graded["view_hash"]
        agreement = {
            "status": "same" if same else "mismatch",
            "draft": graded["view_hash"],
            "grade": graded["marker"]["view_hash"],
        }
    asks_out: list[dict[str, Any]] = []
    for r in conn.execute(
        "SELECT a.id, a.kind, a.proposal, a.created_at, n.choice, n.text, n.at FROM asks a "
        "LEFT JOIN answers n ON n.ask_id = a.id WHERE a.item_id = ? ORDER BY a.id",
        (item_id,),
    ):
        if _ts(r["created_at"]) > t:
            continue
        prop = _proposal(r)
        answered = r["choice"] is not None and _ts(r["at"]) <= t
        asks_out.append(
            {
                "id": r["id"],
                "kind": r["kind"],
                "why": prop.get("why") or "",
                "options": list(cast("list[str]", prop.get("options") or [])),
                "created_at": r["created_at"],
                "attempt": prop.get("attempt"),
                "view_hash": prop.get("view_hash"),
                "links": [
                    {
                        "target": link.get("target"),
                        "title": link.get("target_title") or link.get("target"),
                        "why": link.get("argument") or link.get("why") or link.get("reason") or "",
                    }
                    for link in cast("list[dict[str, Any]]", prop.get("links") or [])
                ],
                "answer": {"choice": r["choice"], "text": r["text"], "at": r["at"]}
                if answered
                else None,
            }
        )
    take_row = None
    for tk in conn.execute(
        "SELECT kind, text, written_at FROM takes WHERE item_id = ? ORDER BY id DESC", (item_id,)
    ):
        if _ts(tk["written_at"]) <= t:
            take_row = tk
            break
    rounds = _rounds(rows, s)
    n_flag = f" --attempt {rounds}" if rounds else ""
    return {
        "id": item_id,
        "title": _title(row),
        "source": row["source"],
        "url": row["url"],
        "t": t.isoformat(),
        "state": next((r["to_state"] for r in reversed(rows) if r["to_state"]), None),
        "station": _station_dict(s),
        "calls": calls,
        "cap": cap,
        "tokens": tokens,
        "rounds": rounds,
        "running": bool(s and s.name in ("student", "teacher", "spell-checker", "librarian")),
        "take": {"kind": take_row["kind"], "text": take_row["text"]}
        if take_row and take_row["text"]
        else None,
        "view": _view_dict(v, cited) if v else None,
        "agreement": agreement,
        "attempts": att_dicts,
        "asks": asks_out,
        "trail": [_trail_row(r) for r in rows],
        "commands": {
            "view": f"ytk view {item_id}{n_flag} --full",
            "grade": f"ytk grade {item_id}{n_flag}",
            "item": f"ytk item {item_id}",
        },
    }
