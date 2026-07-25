"""CLI, MCP, and SessionStart interfaces for the shared workboard."""

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner

import ytk.workboard as workboard
from ytk import mcp_server
from ytk.cli import cli
from ytk.workboard import WorkboardError, WorkboardSnapshot, WorkItem

REPO_ROOT = Path(__file__).resolve().parents[1]


def _snapshot() -> WorkboardSnapshot:
    current = WorkItem(
        item_id="item-127",
        number=127,
        title="shared agent work queue",
        url="https://github.com/pablomoli/ytk/issues/127",
        priority="P0",
        area="Platform",
        kind="Feature",
        stage="In progress",
        order=1,
    )
    next_ready = WorkItem(
        item_id="item-114",
        number=114,
        title="repair test isolation",
        url="https://github.com/pablomoli/ytk/issues/114",
        priority="P0",
        area="Platform",
        kind="Bug",
        stage="Ready",
        order=2,
    )
    return WorkboardSnapshot(
        items=(current, next_ready),
        in_progress=(current,),
        next_ready=next_ready,
    )


def test_work_next_shows_current_and_next_ticket(monkeypatch):
    monkeypatch.setattr(workboard, "get_snapshot", _snapshot, raising=False)

    result = CliRunner().invoke(cli, ["work", "next"])

    assert result.exit_code == 0, result.output
    assert "Current: #127 shared agent work queue" in result.output
    assert "Next: #114 repair test isolation" in result.output


def test_cli_and_mcp_list_render_the_same_ordered_queue(monkeypatch):
    monkeypatch.setattr(workboard, "get_snapshot", _snapshot)

    cli_result = CliRunner().invoke(cli, ["work", "list"])
    mcp_result = mcp_server.work_list()

    assert cli_result.exit_code == 0, cli_result.output
    assert cli_result.output.strip() == mcp_result
    assert mcp_result.index("#127") < mcp_result.index("#114")


def test_cli_and_mcp_next_render_the_same_snapshot(monkeypatch):
    monkeypatch.setattr(workboard, "get_snapshot", _snapshot)

    cli_result = CliRunner().invoke(cli, ["work", "next"])
    mcp_result = mcp_server.work_next()

    assert cli_result.exit_code == 0, cli_result.output
    assert cli_result.output.strip() == mcp_result


def test_cli_and_mcp_set_stage_use_the_shared_transition(monkeypatch):
    changed = replace(_snapshot().next_ready, stage="In progress")
    calls: list[tuple[int, str]] = []

    def set_issue_stage(issue_number: int, stage: str) -> WorkItem:
        calls.append((issue_number, stage))
        return changed

    monkeypatch.setattr(workboard, "set_issue_stage", set_issue_stage, raising=False)

    cli_result = CliRunner().invoke(
        cli,
        ["work", "set-stage", "114", "in-progress"],
    )
    mcp_result = mcp_server.work_set_stage(114, "in-progress")

    assert cli_result.exit_code == 0, cli_result.output
    assert cli_result.output.strip() == "Updated #114 to In progress."
    assert mcp_result == "Updated #114 to In progress."
    assert calls == [(114, "in-progress"), (114, "in-progress")]


def test_codex_session_context_uses_supported_system_message(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(workboard, "get_snapshot", lambda: snapshot)

    result = CliRunner().invoke(
        cli,
        ["work", "context", "--platform", "codex"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "continue": True,
        "systemMessage": workboard.format_snapshot(snapshot),
    }


def test_claude_session_context_uses_additional_context(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(workboard, "get_snapshot", lambda: snapshot)

    result = CliRunner().invoke(
        cli,
        ["work", "context", "--platform", "claude"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": workboard.format_snapshot(snapshot),
        },
    }


def test_session_context_reports_unavailable_board_without_blocking_startup(monkeypatch):
    def fail() -> WorkboardSnapshot:
        raise WorkboardError("authentication unavailable")

    monkeypatch.setattr(workboard, "get_snapshot", fail)

    result = CliRunner().invoke(
        cli,
        ["work", "context", "--platform", "codex"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "continue": True,
        "systemMessage": "ytk workboard unavailable: authentication unavailable",
    }


@pytest.mark.parametrize("command", ["next", "list"])
def test_read_commands_report_github_failures_cleanly(monkeypatch, command):
    def fail() -> WorkboardSnapshot:
        raise WorkboardError("authentication unavailable")

    monkeypatch.setattr(workboard, "get_snapshot", fail)

    result = CliRunner().invoke(cli, ["work", command])

    assert result.exit_code == 1
    assert result.output == "Error: authentication unavailable\n"


def test_set_stage_reports_github_failure_cleanly(monkeypatch):
    def fail(issue_number: int, stage: str) -> WorkItem:
        raise WorkboardError("project update failed")

    monkeypatch.setattr(workboard, "set_issue_stage", fail)

    result = CliRunner().invoke(
        cli,
        ["work", "set-stage", "114", "in-progress"],
    )

    assert result.exit_code == 1
    assert result.output == "Error: project update failed\n"


@pytest.mark.parametrize(
    ("config_path", "platform"),
    [
        (".codex/hooks.json", "codex"),
        (".claude/settings.json", "claude"),
    ],
)
def test_session_start_hook_is_read_only(tmp_path, config_path, platform):
    project_json = tmp_path / "project.json"
    project_json.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "item-127",
                        "area": "Platform",
                        "content": {
                            "number": 127,
                            "repository": "pablomoli/ytk",
                            "title": "shared agent work queue",
                            "type": "Issue",
                            "url": "https://github.com/pablomoli/ytk/issues/127",
                        },
                        "kind": "Feature",
                        "order": 1,
                        "priority": "P0",
                        "repository": "https://github.com/pablomoli/ytk",
                        "stage": "In progress",
                        "status": "In Progress",
                        "title": "shared agent work queue",
                    }
                ],
                "totalCount": 1,
            }
        ),
        encoding="utf-8",
    )
    issues_json = tmp_path / "issues.json"
    issues_json.write_text(
        json.dumps(
            [
                {
                    "blockedBy": {"nodes": [], "totalCount": 0},
                    "number": 127,
                    "subIssues": {"nodes": [], "totalCount": 0},
                    "title": "shared agent work queue",
                }
            ]
        ),
        encoding="utf-8",
    )
    gh_log = tmp_path / "gh.log"
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        """#!/usr/bin/env python3
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with Path(os.environ["FAKE_GH_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write(" ".join(args) + "\\n")
if args[:2] == ["project", "item-list"]:
    print(Path(os.environ["FAKE_PROJECT_JSON"]).read_text(encoding="utf-8"))
elif args[:2] == ["issue", "list"]:
    print(Path(os.environ["FAKE_ISSUES_JSON"]).read_text(encoding="utf-8"))
else:
    raise SystemExit(2)
""",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    config = json.loads((REPO_ROOT / config_path).read_text(encoding="utf-8"))
    command = config["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}:{env['PATH']}",
            "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
            "FAKE_GH_LOG": str(gh_log),
            "FAKE_PROJECT_JSON": str(project_json),
            "FAKE_ISSUES_JSON": str(issues_json),
        }
    )

    result = subprocess.run(
        command,
        shell=True,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    context = payload.get("systemMessage") or payload["hookSpecificOutput"]["additionalContext"]
    assert "Current: #127 shared agent work queue" in context
    assert platform in command
    assert gh_log.read_text(encoding="utf-8").splitlines() == [
        "project item-list 3 --owner pablomoli --limit 200 --format json",
        (
            "issue list --repo pablomoli/ytk --state open --limit 200 "
            "--json number,blockedBy,subIssues,title"
        ),
    ]
