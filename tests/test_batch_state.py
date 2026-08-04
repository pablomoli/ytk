"""Overnight batch pipeline state machine (#148, E5 experimental arm).

captured -> submitted -> enriched -> filed, plus terminal skipped (filtered).
Every transition is idempotent and crash-safe: an item is never deleted before
reaching filed, a failure is a recorded state plus a reason, and a re-run
advances every item as far as it can go without repeating completed work.
"""

from __future__ import annotations

import json

import pytest

from ytk import batch


@pytest.fixture
def paths(tmp_path, monkeypatch):
    ledger = tmp_path / "batch_ledger.json"
    results = tmp_path / "results"
    monkeypatch.setattr(batch, "LEDGER_PATH", ledger)
    monkeypatch.setattr(batch, "RESULTS_DIR", results)
    return ledger, results


# --- ledger ------------------------------------------------------------------


def test_capture_is_idempotent_and_never_regresses_state(paths):
    ledger = batch.load_ledger()
    batch.capture(ledger, "https://youtu.be/a", "youtube")
    ledger["https://youtu.be/a"].state = "submitted"
    batch.capture(ledger, "https://youtu.be/a", "youtube")

    assert ledger["https://youtu.be/a"].state == "submitted"
    assert len(ledger) == 1


def test_ledger_round_trip(paths):
    ledger_path, _ = paths
    ledger = batch.load_ledger()
    batch.capture(ledger, "https://youtu.be/a", "youtube")
    batch.save_ledger(ledger)

    loaded = batch.load_ledger()
    assert loaded["https://youtu.be/a"].source == "youtube"
    assert loaded["https://youtu.be/a"].state == "captured"
    assert ledger_path.exists()


# --- stage: submit -------------------------------------------------------------


def _fetcher(payloads):
    def fetch(item):
        result = payloads[item.url]
        if isinstance(result, Exception):
            raise result
        return result

    return fetch


def test_submit_advances_captured_items_into_one_batch(paths):
    ledger = batch.load_ledger()
    batch.capture(ledger, "https://youtu.be/a", "youtube")
    batch.capture(ledger, "https://youtu.be/b", "youtube")
    submitted = []

    def submitter(requests):
        submitted.append(requests)
        return "batch_1"

    report = batch.stage_submit(
        ledger,
        fetcher=_fetcher(
            {
                "https://youtu.be/a": {"system": "s", "user": "u"},
                "https://youtu.be/b": {"system": "s", "user": "u"},
            }
        ),
        submitter=submitter,
    )

    assert len(submitted) == 1 and len(submitted[0]) == 2
    assert all(item.state == "submitted" for item in ledger.values())
    assert all(item.batch_id == "batch_1" for item in ledger.values())
    assert report["submitted"] == 2


def test_submit_records_fetch_failures_and_submits_the_rest(paths):
    ledger = batch.load_ledger()
    batch.capture(ledger, "https://youtu.be/ok", "youtube")
    batch.capture(ledger, "https://youtu.be/broken", "youtube")

    report = batch.stage_submit(
        ledger,
        fetcher=_fetcher(
            {
                "https://youtu.be/ok": {"system": "s", "user": "u"},
                "https://youtu.be/broken": RuntimeError("no captions"),
            }
        ),
        submitter=lambda requests: "batch_1",
    )

    ok = ledger["https://youtu.be/ok"]
    broken = ledger["https://youtu.be/broken"]
    assert ok.state == "submitted"
    assert broken.state == "captured"
    assert broken.error == "no captions"
    assert broken.attempts == 1
    assert report["failed"] == 1


def test_submit_skips_entirely_while_a_batch_is_in_flight(paths):
    ledger = batch.load_ledger()
    batch.capture(ledger, "https://youtu.be/a", "youtube")
    ledger["https://youtu.be/a"].state = "submitted"
    ledger["https://youtu.be/a"].batch_id = "batch_0"
    batch.capture(ledger, "https://youtu.be/b", "youtube")

    def submitter(requests):
        pytest.fail("must not submit while a batch is in flight")

    report = batch.stage_submit(ledger, fetcher=_fetcher({}), submitter=submitter)
    assert "in flight" in report["skipped"]
    assert ledger["https://youtu.be/b"].state == "captured"


def test_submit_marks_filtered_items_skipped_terminal(paths):
    ledger = batch.load_ledger()
    batch.capture(ledger, "https://youtu.be/short", "youtube")

    report = batch.stage_submit(
        ledger,
        fetcher=_fetcher({"https://youtu.be/short": batch.FilteredOut("duration < 60s")}),
        submitter=lambda requests: pytest.fail("nothing to submit"),
    )

    item = ledger["https://youtu.be/short"]
    assert item.state == "skipped"
    assert item.error == "duration < 60s"
    assert report["skipped_items"] == 1


# --- stage: poll ---------------------------------------------------------------


def test_poll_leaves_unended_batches_alone(paths):
    ledger = batch.load_ledger()
    batch.capture(ledger, "https://youtu.be/a", "youtube")
    ledger["https://youtu.be/a"].state = "submitted"
    ledger["https://youtu.be/a"].batch_id = "batch_1"
    ledger["https://youtu.be/a"].custom_id = "item-0"

    report = batch.stage_poll(
        ledger,
        poller=lambda batch_id: "in_progress",
        results_fetcher=lambda batch_id: pytest.fail("must not fetch an unended batch"),
    )
    assert ledger["https://youtu.be/a"].state == "submitted"
    assert report["waiting"] == 1


def test_poll_stores_enrichment_and_recycles_errors(paths):
    _, results_dir = paths
    ledger = batch.load_ledger()
    for i, url in enumerate(["https://youtu.be/good", "https://youtu.be/bad"]):
        batch.capture(ledger, url, "youtube")
        ledger[url].state = "submitted"
        ledger[url].batch_id = "batch_1"
        ledger[url].custom_id = f"item-{i}"

    results = [
        {"custom_id": "item-0", "type": "succeeded", "enrichment": {"thesis": "t"}},
        {"custom_id": "item-1", "type": "errored", "error": "invalid_request"},
    ]

    report = batch.stage_poll(
        ledger,
        poller=lambda batch_id: "ended",
        results_fetcher=lambda batch_id: results,
    )

    good = ledger["https://youtu.be/good"]
    bad = ledger["https://youtu.be/bad"]
    assert good.state == "enriched"
    assert json.loads(batch.enrichment_path(good).read_text()) == {"thesis": "t"}
    # errored rides the next night's batch from captured, with the reason kept
    assert bad.state == "captured"
    assert bad.error == "invalid_request"
    assert bad.attempts == 1
    assert report["enriched"] == 1


# --- stage: file ---------------------------------------------------------------


def _enriched_ledger(n=2):
    ledger = batch.load_ledger()
    for i in range(n):
        url = f"https://youtu.be/v{i}"
        batch.capture(ledger, url, "youtube")
        ledger[url].state = "enriched"
    return ledger


def test_file_skips_whole_run_when_any_guard_fails(paths):
    ledger = _enriched_ledger()

    report = batch.stage_file(
        ledger,
        guards=[("chroma", lambda: True), ("memory", lambda: False)],
        filer=lambda item: pytest.fail("guard failed; nothing may run"),
    )

    assert report["skipped"] == "guard failed: memory"
    assert all(item.state == "enriched" for item in ledger.values())


def test_file_advances_items_and_isolates_per_item_errors(paths):
    ledger = _enriched_ledger(3)
    filed = []

    def filer(item):
        if item.url.endswith("v1"):
            raise RuntimeError("encoder oom")
        filed.append(item.url)

    report = batch.stage_file(ledger, guards=[("chroma", lambda: True)], filer=filer)

    assert ledger["https://youtu.be/v0"].state == "filed"
    assert ledger["https://youtu.be/v2"].state == "filed"
    assert ledger["https://youtu.be/v1"].state == "enriched"
    assert ledger["https://youtu.be/v1"].error == "encoder oom"
    assert report["filed"] == 2 and report["failed"] == 1


def test_file_rerun_is_idempotent(paths):
    ledger = _enriched_ledger(1)
    calls = []
    batch.stage_file(ledger, guards=[], filer=lambda item: calls.append(item.url))
    batch.stage_file(ledger, guards=[], filer=lambda item: calls.append(item.url))

    assert calls == ["https://youtu.be/v0"]


# --- morning report --------------------------------------------------------------


def test_morning_report_appends_to_digest(paths, tmp_path):
    ledger = batch.load_ledger()
    batch.capture(ledger, "https://youtu.be/a", "youtube")
    ledger["https://youtu.be/a"].state = "filed"
    batch.capture(ledger, "https://youtu.be/b", "youtube")
    ledger["https://youtu.be/b"].error = "no captions"

    digest = tmp_path / "review-2026-08-04.md"
    batch.morning_report(ledger, digest, skipped_reason=None)

    text = digest.read_text()
    assert "1 filed" in text
    assert "no captions" in text


def test_morning_report_records_a_skipped_run(paths, tmp_path):
    ledger = batch.load_ledger()
    digest = tmp_path / "review-2026-08-04.md"
    batch.morning_report(ledger, digest, skipped_reason="guard failed: memory")

    assert "run skipped: guard failed: memory" in digest.read_text()
