"""Operational visibility for long-running ytk work (migrations, re-embeds).

One writer, three surfaces:
  ~/.ytk/ops-status.json    — machine-readable run state; scripts/watchboard.py
                              renders it live in a tmux pane
  ~/.ytk/logs/ops-journal.md — timestamped milestone journal, written for the
                              human reading it the morning after
  notifications              — memo.notify (tmux/macOS, focus-aware) on step
                              failures always, and on opted-in completions

Shell steps report through the CLI:

  uv run python -m ytk.ops run "phase2-migration" "one-line intent"
  uv run python -m ytk.ops step backup running "copying ~/.ytk/chroma"
  uv run python -m ytk.ops step backup done "1.1G at ~/.ytk/chroma.pre-v2"
  uv run python -m ytk.ops step migrate fail "count mismatch" --notify
  uv run python -m ytk.ops journal "cutover commit is abc1234"

Python callers (migrate_embedder) import the module functions directly.
Every write is a whole-file replace via os.replace, so the watchboard never
reads a torn JSON.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

STATUS_PATH = Path.home() / ".ytk" / "ops-status.json"
JOURNAL_PATH = Path.home() / ".ytk" / "logs" / "ops-journal.md"

_STATES = ("running", "done", "fail", "skip")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read() -> dict:
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(status: dict) -> None:
    status["updated"] = _now()
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
    os.replace(tmp, STATUS_PATH)


def start_run(name: str, intent: str = "") -> None:
    """Begin a fresh run: resets steps and progress, keeps nothing."""
    _write({"run": name, "intent": intent, "started": _now(), "steps": [], "progress": None})
    journal(f"run started: {name}" + (f" — {intent}" if intent else ""), header=True)


def step(name: str, state: str, detail: str = "", notify: bool = False) -> None:
    """Upsert a named step. Failures always notify; completions when asked."""
    if state not in _STATES:
        raise ValueError(f"state must be one of {_STATES}")
    status = _read() or {"run": "adhoc", "started": _now(), "steps": [], "progress": None}
    steps = status.setdefault("steps", [])
    for s in steps:
        if s["name"] == name:
            s.update(state=state, detail=detail, at=_now())
            break
    else:
        steps.append({"name": name, "state": state, "detail": detail, "at": _now()})
    if state in ("done", "fail"):
        status["progress"] = None  # a finished step's bar is stale by definition
    _write(status)
    if state != "running":
        journal(f"{name}: {state}" + (f" — {detail}" if detail else ""))
    if state == "fail" or notify:
        _notify(f"[ytk ops] {name}: {state}", detail)


def progress(current: int, total: int, rate: float | None = None, label: str = "") -> None:
    """Update the live progress bar (attach to whichever step is running)."""
    status = _read()
    if not status:
        return
    eta_min = (total - current) / rate / 60 if rate else None
    status["progress"] = {
        "label": label,
        "current": int(current),
        "total": int(total),
        "rate": round(rate, 2) if rate else None,
        "eta_min": round(eta_min, 1) if eta_min is not None else None,
    }
    _write(status)


def journal(msg: str, header: bool = False) -> None:
    """Append one timestamped milestone line for the morning read."""
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with JOURNAL_PATH.open("a", encoding="utf-8") as f:
        if header:
            f.write(f"\n## {stamp} — {msg}\n")
        else:
            f.write(f"- `{stamp}` {msg}\n")


def _notify(summary: str, detail: str = "") -> None:
    try:
        from ytk.memo import notify as memo_notify

        memo_notify(f"{summary}. {detail}"[:180], kind="ops")
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    notify = "--notify" in args
    args = [a for a in args if a != "--notify"]
    if not args:
        print(__doc__)
        return 2
    cmd, rest = args[0], args[1:]
    if cmd == "run" and rest:
        start_run(rest[0], rest[1] if len(rest) > 1 else "")
    elif cmd == "step" and len(rest) >= 2:
        step(rest[0], rest[1], rest[2] if len(rest) > 2 else "", notify=notify)
    elif cmd == "progress" and len(rest) >= 2:
        progress(
            int(rest[0]),
            int(rest[1]),
            float(rest[2]) if len(rest) > 2 else None,
            rest[3] if len(rest) > 3 else "",
        )
    elif cmd == "journal" and rest:
        journal(rest[0])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
