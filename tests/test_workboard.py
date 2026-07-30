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


def _board_fixture(items, issues):
    """Stub gh for snapshot() + audit(): both issue-list shapes, plus mutations."""
    mutations: list[list[str]] = []

    def run_gh(args: list[str]) -> str:
        if args[:3] == ["project", "item-list", "3"]:
            return json.dumps({"items": items, "totalCount": len(items)})
        if args[:2] == ["issue", "list"]:
            if "blockedBy" in args[-1]:
                return json.dumps(
                    [
                        {
                            "blockedBy": {"nodes": [], "totalCount": 0},
                            "number": n,
                            "subIssues": {"nodes": [], "totalCount": 0},
                            "title": f"issue {n}",
                        }
                        for n in issues
                    ]
                )
            return json.dumps([{"number": n} for n in issues])
        mutations.append(args)
        return ""

    return run_gh, mutations


def _item(number, *, item_id=None, **fields):
    base = {
        "id": item_id or f"item-{number}",
        "content": {
            "number": number,
            "repository": "pablomoli/ytk",
            "title": f"issue {number}",
            "type": "Issue",
            "url": f"https://github.com/pablomoli/ytk/issues/{number}",
        },
        "title": f"issue {number}",
    }
    base.update(fields)
    return base


def test_set_fields_writes_every_requested_field_and_leaves_others_alone():
    run_gh, mutations = _board_fixture(
        [_item(153, area="", kind="", order=None, priority="", stage="", status="")],
        [153],
    )

    updated = WorkboardClient(run_gh=run_gh).set_fields(
        153,
        kind="initiative",
        priority="p2",
        area="map-growth-and-grove",
        order=66,
    )

    assert (updated.kind, updated.priority, updated.area) == (
        "Initiative",
        "P2",
        "Map growth and grove",
    )
    assert updated.order == 66
    option_ids = [
        m[m.index("--single-select-option-id") + 1]
        for m in mutations
        if "--single-select-option-id" in m
    ]
    assert option_ids == ["846037e6", "f6d637cc", "0a5f15d1"]
    number_writes = [m for m in mutations if "--number" in m]
    assert number_writes[0][number_writes[0].index("--number") + 1] == "66"
    # stage was not requested, so neither Stage nor Status may be touched
    touched_fields = {m[m.index("--field-id") + 1] for m in mutations if "--field-id" in m}
    assert workboard.STAGE_FIELD_ID not in touched_fields
    assert workboard.STATUS_FIELD_ID not in touched_fields


def test_set_fields_accepts_display_spellings():
    run_gh, mutations = _board_fixture([_item(153)], [153])

    updated = WorkboardClient(run_gh=run_gh).set_fields(153, area="Hub UI", priority="P1")

    assert (updated.area, updated.priority) == ("Hub UI", "P1")


def test_set_fields_rejects_unknown_kind_without_reading_github():
    def fail_if_called(args: list[str]) -> str:
        pytest.fail(f"gh must not run for an invalid kind: {args}")

    with pytest.raises(WorkboardError, match="Unknown kind"):
        WorkboardClient(run_gh=fail_if_called).set_fields(153, kind="epic")


def test_audit_reports_absent_issues_and_empty_fields():
    items = [
        _item(21, area="Hub UI", kind="Initiative", order=65, priority="P0", stage="In progress"),
        _item(153, area="", kind="", order=None, priority="", stage=""),
        _item(999, area="Vault", kind="Bug", order=3, priority="P1", stage="Done"),
    ]
    run_gh, _ = _board_fixture(items, [21, 153, 160])

    missing, incomplete = WorkboardClient(run_gh=run_gh).audit()

    assert missing == (160,)
    # #999 is closed, so it is not audited even though it sits on the board
    assert [item.number for item, _ in incomplete] == [153]
    assert set(incomplete[0][1]) == {"kind", "priority", "area", "stage", "order"}


def test_add_issue_returns_existing_item_without_adding_twice():
    run_gh, mutations = _board_fixture([_item(21, order=65)], [21])

    item_id = WorkboardClient(run_gh=run_gh).add_issue(21)

    assert item_id == "item-21"
    assert mutations == []


def test_set_fields_writes_a_freshly_added_item_the_board_read_cannot_see_yet():
    """item-add returns an id before item-list lists it; trust the id, not the read."""
    added: list[list[str]] = []
    mutations: list[list[str]] = []

    def run_gh(args: list[str]) -> str:
        if args[:3] == ["project", "item-list", "3"]:
            return json.dumps({"items": [], "totalCount": 0})
        if args[:2] == ["issue", "list"]:
            if "blockedBy" in args[-1]:
                return json.dumps([])
            return json.dumps([{"number": 160}])
        if args[:2] == ["project", "item-add"]:
            added.append(args)
            return json.dumps({"id": "PVTI_fresh", "type": "Issue"})
        mutations.append(args)
        return ""

    updated = WorkboardClient(run_gh=run_gh).set_fields(
        160, kind="maintenance", priority="p2", order=71, create=True
    )

    assert len(added) == 1
    assert updated.item_id == "PVTI_fresh"
    assert (updated.kind, updated.priority, updated.order) == ("Maintenance", "P2", 71)
    edited_ids = {m[m.index("--id") + 1] for m in mutations if "--id" in m}
    assert edited_ids == {"PVTI_fresh"}


def test_set_fields_without_create_still_fails_when_absent():
    def run_gh(args: list[str]) -> str:
        if args[:3] == ["project", "item-list", "3"]:
            return json.dumps({"items": [], "totalCount": 0})
        if args[:2] == ["issue", "list"]:
            return json.dumps([] if "blockedBy" in args[-1] else [{"number": 160}])
        pytest.fail(f"must not mutate an absent item: {args}")

    with pytest.raises(WorkboardError, match="not in ytk Project 3"):
        WorkboardClient(run_gh=run_gh).set_fields(160, kind="maintenance")


def test_set_many_reads_the_board_once_for_the_whole_batch():
    """A per-item snapshot exhausts the GraphQL budget on a bulk fill."""
    items = [_item(n, area="", kind="", order=None, priority="", stage="") for n in (153, 154, 155)]
    run_gh, mutations = _board_fixture(items, [153, 154, 155])
    reads: list[list[str]] = []

    def counting_gh(args: list[str]) -> str:
        if args[:3] == ["project", "item-list", "3"]:
            reads.append(args)
        return run_gh(args)

    updated = WorkboardClient(run_gh=counting_gh).set_many(
        [
            workboard.FieldUpdate(153, kind="initiative", order=66.0),
            workboard.FieldUpdate(154, kind="feature", order=66.1),
            workboard.FieldUpdate(155, kind="feature", order=66.2),
        ]
    )

    assert len(reads) == 1
    assert [i.number for i in updated] == [153, 154, 155]
    assert [i.kind for i in updated] == ["Initiative", "Feature", "Feature"]
    assert [i.order for i in updated] == [66.0, 66.1, 66.2]


def test_set_many_rejects_the_whole_batch_before_writing_anything():
    items = [_item(n) for n in (153, 154)]
    run_gh, mutations = _board_fixture(items, [153, 154])

    with pytest.raises(WorkboardError, match="Unknown priority"):
        WorkboardClient(run_gh=run_gh).set_many(
            [
                workboard.FieldUpdate(153, kind="feature"),
                workboard.FieldUpdate(154, priority="urgent"),
            ]
        )

    assert mutations == []
