"""Capture-outcome log — the #149-E5 baseline instrumentation.

Every ingest attempt appends one JSONL record to ~/.ytk/capture_log.jsonl
(override with YTK_CAPTURE_LOG; "off" disables). Instrumentation only: a
logging failure is swallowed so it can never take down an ingest. The window
this accumulates is the before-measurement that gates #148's state machine.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

_CAPTURE_LOG = Path.home() / ".ytk" / "capture_log.jsonl"


def log_capture(
    surface: str,
    url: str,
    *,
    source: str,
    outcome: str,
    error: str | None = None,
    attempt: int | None = None,
    duration_s: float | None = None,
    note_found: bool | None = None,
) -> None:
    target = os.environ.get("YTK_CAPTURE_LOG", str(_CAPTURE_LOG))
    if target.strip().lower() == "off":
        return
    record: dict[str, str | int | float | bool] = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "surface": surface,
        "url": url,
        "source": source,
        "outcome": outcome,
    }
    if error is not None:
        record["error"] = error[:500]
    if attempt is not None:
        record["attempt"] = attempt
    if duration_s is not None:
        record["duration_s"] = round(duration_s, 1)
    if note_found is not None:
        record["note_found"] = note_found
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass
