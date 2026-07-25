"""Behavioral tests for the GitHub Project work queue."""

import json
import subprocess

import pytest

import ytk.workboard as workboard
from ytk.workboard import WorkboardClient, WorkboardError


def test_snapshot_excludes_blocked_work_and_parent_initiatives():
    project_items = {
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
            },
            {
                "id": "item-110",
                "area": "Hub UI",
                "content": {
                    "number": 110,
                    "repository": "pablomoli/ytk",
                    "title": "blocked first item",
                    "type": "Issue",
                    "url": "https://github.com/pablomoli/ytk/issues/110",
                },
                "kind": "Bug",
                "order": 1,
                "priority": "P0",
                "repository": "https://github.com/pablomoli/ytk",
                "stage": "Ready",
                "status": "Todo",
                "title": "blocked first item",
            },
            {
                "id": "item-21",
                "area": "Hub UI",
                "content": {
                    "number": 21,
                    "repository": "pablomoli/ytk",
                    "title": "parent initiative",
                    "type": "Issue",
                    "url": "https://github.com/pablomoli/ytk/issues/21",
                },
                "kind": "Initiative",
                "order": 1.5,
                "priority": "P0",
                "repository": "https://github.com/pablomoli/ytk",
                "stage": "Ready",
                "status": "Todo",
                "title": "parent initiative",
            },
            {
                "id": "item-114",
                "area": "Platform",
                "content": {
                    "number": 114,
                    "repository": "pablomoli/ytk",
                    "title": "repair test isolation",
                    "type": "Issue",
                    "url": "https://github.com/pablomoli/ytk/issues/114",
                },
                "kind": "Bug",
                "order": 2,
                "priority": "P0",
                "repository": "https://github.com/pablomoli/ytk",
                "stage": "Ready",
                "status": "Todo",
                "title": "repair test isolation",
            },
        ],
        "totalCount": 4,
    }
    issue_state = [
        {
            "blockedBy": {"nodes": [], "totalCount": 0},
            "number": 127,
            "subIssues": {"nodes": [], "totalCount": 0},
            "title": "shared agent work queue",
        },
        {
            "blockedBy": {
                "nodes": [
                    {
                        "number": 99,
                        "state": "OPEN",
                        "title": "prerequisite",
                        "url": "https://github.com/pablomoli/ytk/issues/99",
                    }
                ],
                "totalCount": 1,
            },
            "number": 110,
            "subIssues": {"nodes": [], "totalCount": 0},
            "title": "blocked first item",
        },
        {
            "blockedBy": {"nodes": [], "totalCount": 0},
            "number": 21,
            "subIssues": {
                "nodes": [
                    {
                        "number": 114,
                        "state": "OPEN",
                        "title": "repair test isolation",
                        "url": "https://github.com/pablomoli/ytk/issues/114",
                    }
                ],
                "totalCount": 1,
            },
            "title": "parent initiative",
        },
        {
            "blockedBy": {"nodes": [], "totalCount": 0},
            "number": 114,
            "subIssues": {"nodes": [], "totalCount": 0},
            "title": "repair test isolation",
        },
    ]

    def run_gh(args: list[str]) -> str:
        if args[:3] == ["project", "item-list", "3"]:
            return json.dumps(project_items)
        if args[:2] == ["issue", "list"]:
            return json.dumps(issue_state)
        raise AssertionError(f"Unexpected gh call: {args}")

    snapshot = WorkboardClient(run_gh=run_gh).snapshot()

    assert [item.number for item in snapshot.in_progress] == [127]
    assert snapshot.next_ready is not None
    assert snapshot.next_ready.number == 114


def test_set_stage_updates_project_stage_and_status():
    project_items = {
        "items": [
            {
                "id": "item-114",
                "area": "Platform",
                "content": {
                    "number": 114,
                    "repository": "pablomoli/ytk",
                    "title": "repair test isolation",
                    "type": "Issue",
                    "url": "https://github.com/pablomoli/ytk/issues/114",
                },
                "kind": "Bug",
                "order": 2,
                "priority": "P0",
                "repository": "https://github.com/pablomoli/ytk",
                "stage": "Ready",
                "status": "Todo",
                "title": "repair test isolation",
            }
        ],
        "totalCount": 1,
    }
    issue_state = [
        {
            "blockedBy": {"nodes": [], "totalCount": 0},
            "number": 114,
            "subIssues": {"nodes": [], "totalCount": 0},
            "title": "repair test isolation",
        }
    ]
    mutations: list[list[str]] = []

    def run_gh(args: list[str]) -> str:
        if args[:3] == ["project", "item-list", "3"]:
            return json.dumps(project_items)
        if args[:2] == ["issue", "list"]:
            return json.dumps(issue_state)
        mutations.append(args)
        return ""

    updated = WorkboardClient(run_gh=run_gh).set_stage(114, "in-progress")

    assert updated.stage == "In progress"
    assert mutations == [
        [
            "project",
            "item-edit",
            "--id",
            "item-114",
            "--project-id",
            "PVT_kwHOA9tX2c4Beb83",
            "--field-id",
            "PVTSSF_lAHOA9tX2c4Beb83zhY2L9I",
            "--single-select-option-id",
            "bd47a3e4",
        ],
        [
            "project",
            "item-edit",
            "--id",
            "item-114",
            "--project-id",
            "PVT_kwHOA9tX2c4Beb83",
            "--field-id",
            "PVTSSF_lAHOA9tX2c4Beb83zhY2Lww",
            "--single-select-option-id",
            "47fc9ee4",
        ],
    ]


def test_set_stage_rejects_unknown_stage_without_reading_github():
    def fail_if_called(args: list[str]) -> str:
        pytest.fail(f"gh must not run for an invalid stage: {args}")

    with pytest.raises(WorkboardError, match="Unknown stage"):
        WorkboardClient(run_gh=fail_if_called).set_stage(114, "started")


def test_run_gh_surfaces_cli_failure(monkeypatch):
    monkeypatch.setattr(
        workboard.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["gh", "project", "item-list"],
            returncode=1,
            stdout="",
            stderr="permission denied",
        ),
    )

    with pytest.raises(WorkboardError, match="permission denied"):
        workboard.run_gh(["project", "item-list", "3"])
