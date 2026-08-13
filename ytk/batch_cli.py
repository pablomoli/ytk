"""Click commands for the overnight batch pipeline (#148)."""

from __future__ import annotations

import click

from . import batch, batch_adapters


@click.group(name="batch")
def batch_group():
    """Drive the overnight ingest pipeline: capture, submit, poll, file."""


@batch_group.command(name="status")
def batch_status():
    """Show every ledger item and its pipeline state."""
    ledger = batch.load_ledger()
    if not ledger:
        click.echo("Ledger empty — nothing captured for the overnight pipeline.")
        return
    for state in batch.STATES:
        items = [i for i in ledger.values() if i.state == state]
        if not items:
            continue
        click.echo(f"{state} ({len(items)}):")
        for item in items:
            suffix = f" — {item.error}" if item.error else ""
            click.echo(f"  {item.url}{suffix}")


@batch_group.command(name="capture")
@click.argument("urls", nargs=-1, required=True)
def batch_capture(urls: tuple[str, ...]):
    """Capture URLs into the overnight ledger (instant, no fetch)."""
    from .reels import classify_url

    ledger = batch.load_ledger()
    for url in urls:
        batch.capture(ledger, url, classify_url(url))
    batch.save_ledger(ledger)
    click.echo(f"Captured {len(urls)}; ledger holds {len(ledger)} items.")


@batch_group.command(name="run")
@click.option(
    "--stage",
    type=click.Choice(["submit", "poll", "file"]),
    required=True,
    help="Which pipeline stage to advance.",
)
@click.option("--dry-run", is_flag=True, help="Report what would happen; touch nothing.")
@click.option(
    "--force",
    is_flag=True,
    help="Skip the file-stage guards. Debugging only: the idle guard fails by "
    "definition while you are at the keyboard, so a hand-run needs this.",
)
def batch_run(stage: str, dry_run: bool, force: bool):
    """Advance every item as far as this stage allows."""
    ledger = batch.load_ledger()

    if dry_run:
        eligible = {
            "submit": [i for i in ledger.values() if i.state == "captured"],
            "poll": [i for i in ledger.values() if i.state == "submitted"],
            "file": [i for i in ledger.values() if i.state == "enriched"],
        }[stage]
        click.echo(f"dry-run: {stage} would touch {len(eligible)} items")
        for item in eligible:
            click.echo(f"  {item.url}")
        return

    if stage == "submit":
        report = batch.stage_submit(
            ledger, fetcher=_fetch, submitter=batch_adapters.submit_enrichment_batch
        )
    elif stage == "poll":
        report = batch.stage_poll(
            ledger,
            poller=batch_adapters.poll_batch,
            results_fetcher=batch_adapters.fetch_batch_results,
        )
    else:
        guards = [] if force else batch_adapters.default_guards()
        report = batch.stage_file(ledger, guards=guards, filer=_file)
    click.echo(" ".join(f"{k}={v}" for k, v in report.items()))


def _fetch(item: batch.BatchItem) -> dict[str, str]:
    if item.source not in batch_adapters.OVERNIGHT_SOURCES:
        raise batch.FilteredOut(f"source {item.source} not routed overnight yet")
    return batch_adapters.fetch_youtube_payload(item)


def _file(item: batch.BatchItem) -> None:
    batch_adapters.file_youtube_item(item)


@batch_group.command(name="report")
def batch_report():
    """Append the overnight outcome to today's digest."""
    from datetime import date

    from .vault import get_brain_path

    ledger = batch.load_ledger()
    digest = get_brain_path() / "inbox" / f"review-{date.today().isoformat()}.md"
    batch.morning_report(ledger, digest, skipped_reason=None)
    click.echo(f"Report appended to {digest}")
