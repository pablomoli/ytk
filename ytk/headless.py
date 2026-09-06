"""The headless surface (#212, P8 pulled forward): the verbs a terminal, a
chat session or the MCP server use to read one item's packet and trail and
to answer an ask. One module; the CLI and MCP wrappers carry no logic.

Every verb reads what the loop wrote (views, attempts, drafts, the ledger).
The only write is an answer row, an event the loop turns into a transition
on its next tick; the verb nudges it and never advances anything itself.
"""

from __future__ import annotations

import json
import sqlite3
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
