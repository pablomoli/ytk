"""Overnight batch pipeline — the #148 state machine (E5 experimental arm).

captured -> submitted -> enriched -> filed, plus terminal skipped (filtered).
The overnight jobs only ever advance every item as far as it can go: every
transition is idempotent, an item is never deleted before reaching filed, and
a failure is a recorded state plus a reason, retried the next night. State
lives in a sidecar ledger rather than the pending-queue records: the queue is
"what is pending", the ledger is "how far the overnight pipeline advanced it",
and the queue schema is owned by parallel work (#163).
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RequestParams = dict[str, Any]
StageReport = dict[str, int | str]
Guard = tuple[str, Callable[[], bool]]

LEDGER_PATH = Path.home() / ".ytk" / "batch_ledger.json"
RESULTS_DIR = Path.home() / ".ytk" / "batch_results"

STATES = ("captured", "submitted", "enriched", "filed", "skipped")

ENRICH_MODEL = "claude-haiku-4-5"
ENRICH_MAX_TOKENS = 8192


class FilteredOut(Exception):
    """The item fails the configured filters; terminal, never retried."""


@dataclass
class BatchItem:
    url: str
    source: str
    state: str = "captured"
    batch_id: str | None = None
    custom_id: str | None = None
    error: str | None = None
    attempts: int = 0
    captured_at: str | None = None
    submitted_at: str | None = None
    enriched_at: str | None = None
    filed_at: str | None = None


Ledger = dict[str, BatchItem]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def load_ledger() -> Ledger:
    """Load the ledger, tolerating a missing/corrupt file via the .bak copy."""
    for candidate in (LEDGER_PATH, LEDGER_PATH.with_suffix(".json.bak")):
        try:
            if candidate.exists() and candidate.stat().st_size > 0:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
                return {url: BatchItem(**entry) for url, entry in raw.items()}
        except (json.JSONDecodeError, TypeError, ValueError, OSError):
            continue
    return {}


def save_ledger(ledger: Ledger) -> None:
    """Atomic write with a .bak of the previous good copy (same pattern as
    reels_state: a process killed mid-write must never wipe pipeline state)."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps({url: asdict(item) for url, item in ledger.items()}, indent=2)
    tmp = LEDGER_PATH.with_suffix(".json.tmp")
    tmp.write_text(data, encoding="utf-8")
    if LEDGER_PATH.exists() and LEDGER_PATH.stat().st_size > 0:
        try:
            shutil.copy2(LEDGER_PATH, LEDGER_PATH.with_suffix(".json.bak"))
        except OSError:
            pass
    os.replace(tmp, LEDGER_PATH)


def capture(ledger: Ledger, url: str, source: str) -> BatchItem:
    """Idempotent: a re-captured url keeps whatever state it already reached."""
    if url not in ledger:
        ledger[url] = BatchItem(url=url, source=source, captured_at=_now())
    return ledger[url]


def payload_path(item: BatchItem) -> Path:
    return RESULTS_DIR / f"{item.custom_id}-payload.json"


def enrichment_path(item: BatchItem) -> Path:
    return RESULTS_DIR / f"{item.custom_id}-enrichment.json"


# --- stage 1: nightly submit ---------------------------------------------------


def stage_submit(
    ledger: Ledger,
    *,
    fetcher: Callable[[BatchItem], dict[str, str]],
    submitter: Callable[[list[RequestParams]], str],
) -> StageReport:
    """Fetch every captured item and submit one enrichment batch.

    fetcher(item) returns the request material (at minimum system/user; the
    real adapter also persists meta+segments for the file stage), raises
    FilteredOut for terminal filter rejections, or any other exception for a
    retryable failure. submitter(requests) returns the batch id.
    """
    in_flight = [i for i in ledger.values() if i.state == "submitted"]
    if in_flight:
        return {"skipped": f"batch {in_flight[0].batch_id} still in flight", "submitted": 0}

    ready: list[BatchItem] = []
    failed = 0
    skipped_items = 0
    requests: list[RequestParams] = []
    for index, item in enumerate(i for i in ledger.values() if i.state == "captured"):
        item.custom_id = item.custom_id or f"item-{index}-{abs(hash(item.url)) % 10**8}"
        try:
            payload = fetcher(item)
        except FilteredOut as exc:
            item.state = "skipped"
            item.error = str(exc)
            skipped_items += 1
            save_ledger(ledger)
            continue
        except Exception as exc:
            item.error = str(exc)
            item.attempts += 1
            failed += 1
            save_ledger(ledger)
            continue
        requests.append(build_request(item.custom_id, payload["system"], payload["user"]))
        ready.append(item)

    if ready:
        batch_id = submitter(requests)
        for item in ready:
            item.state = "submitted"
            item.batch_id = batch_id
            item.submitted_at = _now()
        save_ledger(ledger)

    return {"submitted": len(ready), "failed": failed, "skipped_items": skipped_items}


def build_request(custom_id: str, system: str, user: str) -> RequestParams:
    """One Message Batches request on the existing haiku enrichment prompt.

    Structured output pins the response to the Enrichment schema, replacing
    the Agent SDK's run_structured contract on the synchronous path.
    """
    from .enrich import ENRICHMENT_SCHEMA  # deferred: enrich pulls config + sdk modules

    return {
        "custom_id": custom_id,
        "params": {
            "model": ENRICH_MODEL,
            "max_tokens": ENRICH_MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": ENRICHMENT_SCHEMA}},
        },
    }


# --- stage 2: poll -------------------------------------------------------------


def stage_poll(
    ledger: Ledger,
    *,
    poller: Callable[[str], str],
    results_fetcher: Callable[[str], Iterable[dict[str, Any]]],
) -> StageReport:
    """Fetch results for every ended batch; errored items ride the next night.

    poller(batch_id) returns the processing status; results_fetcher(batch_id)
    yields {custom_id, type, enrichment|error} dicts (order not guaranteed —
    matched by custom_id, never position).
    """
    submitted = [i for i in ledger.values() if i.state == "submitted"]
    by_batch: dict[str, list[BatchItem]] = {}
    for item in submitted:
        by_batch.setdefault(item.batch_id or "", []).append(item)

    enriched = 0
    errored = 0
    waiting = 0
    for batch_id, items in by_batch.items():
        if poller(batch_id) != "ended":
            waiting += len(items)
            continue
        by_custom = {i.custom_id: i for i in items}
        for result in results_fetcher(batch_id):
            item = by_custom.get(result["custom_id"])
            if item is None:
                continue
            if result["type"] == "succeeded":
                RESULTS_DIR.mkdir(parents=True, exist_ok=True)
                enrichment_path(item).write_text(json.dumps(result["enrichment"]), encoding="utf-8")
                item.state = "enriched"
                item.enriched_at = _now()
                item.error = None
                enriched += 1
            else:
                item.state = "captured"
                item.error = str(result.get("error") or result["type"])
                item.attempts += 1
                errored += 1
            save_ledger(ledger)

    return {"enriched": enriched, "errored": errored, "waiting": waiting}


# --- stage 3: guarded 5am file window --------------------------------------------


def evaluate_guards(guards: list[Guard]) -> str | None:
    """Name of the first failing guard, or None. Any failure skips the whole
    run — no partial unattended behavior."""
    for name, check in guards:
        try:
            ok = check()
        except Exception:
            ok = False
        if not ok:
            return name
    return None


def stage_file(
    ledger: Ledger,
    *,
    guards: list[Guard],
    filer: Callable[[BatchItem], None],
) -> StageReport:
    failing = evaluate_guards(guards)
    if failing is not None:
        return {"skipped": f"guard failed: {failing}", "filed": 0, "failed": 0}

    filed = 0
    failed = 0
    for item in [i for i in ledger.values() if i.state == "enriched"]:
        try:
            filer(item)
        except Exception as exc:
            # one bad item cannot take down the rest of the run
            item.error = str(exc)
            item.attempts += 1
            failed += 1
            save_ledger(ledger)
            continue
        item.state = "filed"
        item.filed_at = _now()
        item.error = None
        filed += 1
        save_ledger(ledger)

    return {"filed": filed, "failed": failed}


# --- morning report ---------------------------------------------------------------


def morning_report(ledger: Ledger, digest_path: Path, *, skipped_reason: str | None) -> None:
    """Append the overnight outcome to the daily digest. Silence is never
    ambiguous: a skipped run says so and names the guard."""
    lines = ["", f"## Overnight batch — {datetime.now(UTC):%Y-%m-%d}", ""]
    if skipped_reason:
        lines.append(f"- run skipped: {skipped_reason}")
    counts = {state: sum(1 for i in ledger.values() if i.state == state) for state in STATES}
    lines.append(
        f"- {counts['filed']} filed, {counts['enriched']} enriched awaiting filing, "
        f"{counts['submitted']} in batch, {counts['captured']} queued, "
        f"{counts['skipped']} filtered out"
    )
    for item in ledger.values():
        if item.error:
            lines.append(
                f"- failed ({item.state}, attempt {item.attempts}): {item.url} — {item.error}"
            )
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    with digest_path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
