"""Click commands for the canonical GitHub Project work queue."""

from __future__ import annotations

import json

import click

from . import workboard as workboard_service


@click.group(name="work")
def work():
    """Read or update the canonical GitHub Project work queue."""


@work.command(name="next")
def work_next():
    """Show work already in progress and the next executable ticket."""
    try:
        click.echo(workboard_service.format_snapshot(workboard_service.get_snapshot()))
    except workboard_service.WorkboardError as exc:
        raise click.ClickException(str(exc)) from exc


@work.command(name="list")
def work_list():
    """List active project items in canonical order."""
    try:
        click.echo(workboard_service.format_queue(workboard_service.get_snapshot()))
    except workboard_service.WorkboardError as exc:
        raise click.ClickException(str(exc)) from exc


@work.command(name="set-stage")
@click.argument("issue_number", type=int)
@click.argument(
    "stage",
    type=click.Choice(["triage", "needs-evidence", "ready", "in-progress", "verify", "done"]),
)
def work_set_stage(issue_number: int, stage: str):
    """Explicitly change an issue's project Stage."""
    try:
        updated = workboard_service.set_issue_stage(issue_number, stage)
    except workboard_service.WorkboardError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Updated #{updated.number} to {updated.stage}.")


@work.command(name="context", hidden=True)
@click.option("--platform", type=click.Choice(["codex", "claude"]), required=True)
def work_context(platform: str):
    """Emit the platform-specific SessionStart response."""
    try:
        context = workboard_service.format_snapshot(workboard_service.get_snapshot())
    except workboard_service.WorkboardError as exc:
        context = f"ytk workboard unavailable: {exc}"
    if platform == "codex":
        payload = {"continue": True, "systemMessage": context}
    else:
        payload = {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            },
        }
    click.echo(json.dumps(payload))
