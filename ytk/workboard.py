"""Shared GitHub Project work-queue behavior for CLI, MCP, and hooks."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

PROJECT_NUMBER = 3
PROJECT_OWNER = "pablomoli"
PROJECT_ID = "PVT_kwHOA9tX2c4Beb83"
REPOSITORY = "pablomoli/ytk"
STAGE_FIELD_ID = "PVTSSF_lAHOA9tX2c4Beb83zhY2L9I"
STATUS_FIELD_ID = "PVTSSF_lAHOA9tX2c4Beb83zhY2Lww"

STAGES = {
    "triage": ("Triage", "fc0d7e07", "f75ad846"),
    "needs-evidence": ("Needs evidence", "3be8ca3e", "f75ad846"),
    "ready": ("Ready", "c284baa8", "f75ad846"),
    "in-progress": ("In progress", "bd47a3e4", "47fc9ee4"),
    "verify": ("Verify", "a57ba5cb", "47fc9ee4"),
    "done": ("Done", "da33651d", "98236657"),
}


class WorkboardError(RuntimeError):
    """Raised when the workboard cannot be read or updated."""


GhRunner = Callable[[list[str]], str]


@dataclass(frozen=True)
class WorkItem:
    item_id: str
    number: int
    title: str
    url: str
    priority: str
    area: str
    kind: str
    stage: str
    order: float
    blocked_by: tuple[int, ...] = ()
    open_subissues: tuple[int, ...] = ()


@dataclass(frozen=True)
class WorkboardSnapshot:
    items: tuple[WorkItem, ...]
    in_progress: tuple[WorkItem, ...]
    next_ready: WorkItem | None


def run_gh(args: list[str]) -> str:
    """Run an authenticated GitHub CLI command and return stdout."""
    try:
        result = subprocess.run(
            ["gh", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkboardError(f"GitHub CLI failed: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise WorkboardError(f"GitHub CLI failed: {detail}")
    return result.stdout


class WorkboardClient:
    def __init__(self, run_gh: GhRunner = run_gh):
        self._run_gh = run_gh

    def snapshot(self) -> WorkboardSnapshot:
        project_payload = self._load_json(
            self._run_gh(
                [
                    "project",
                    "item-list",
                    str(PROJECT_NUMBER),
                    "--owner",
                    PROJECT_OWNER,
                    "--limit",
                    "200",
                    "--format",
                    "json",
                ]
            )
        )
        issue_payload = self._load_json(
            self._run_gh(
                [
                    "issue",
                    "list",
                    "--repo",
                    REPOSITORY,
                    "--state",
                    "open",
                    "--limit",
                    "200",
                    "--json",
                    "number,blockedBy,subIssues,title",
                ]
            )
        )
        issue_state = {
            int(issue["number"]): issue
            for issue in issue_payload
            if isinstance(issue, dict) and "number" in issue
        }

        items: list[WorkItem] = []
        for raw_item in project_payload.get("items", []):
            content = raw_item.get("content") or {}
            if content.get("type") != "Issue" or "number" not in content:
                continue
            number = int(content["number"])
            state = issue_state.get(number, {})
            blocked_by = tuple(
                int(node["number"])
                for node in state.get("blockedBy", {}).get("nodes", [])
                if node.get("state") == "OPEN"
            )
            open_subissues = tuple(
                int(node["number"])
                for node in state.get("subIssues", {}).get("nodes", [])
                if node.get("state") == "OPEN"
            )
            item = WorkItem(
                item_id=str(raw_item["id"]),
                number=number,
                title=str(content.get("title") or raw_item.get("title") or ""),
                url=str(content.get("url") or ""),
                priority=str(raw_item.get("priority") or ""),
                area=str(raw_item.get("area") or ""),
                kind=str(raw_item.get("kind") or ""),
                stage=str(raw_item.get("stage") or ""),
                order=float(raw_item.get("order") or float("inf")),
            )
            items.append(replace(item, blocked_by=blocked_by, open_subissues=open_subissues))

        ordered = tuple(sorted(items, key=lambda item: (item.order, item.number)))
        in_progress = tuple(
            item for item in ordered if item.stage == "In progress" and not item.open_subissues
        )
        next_ready = next(
            (
                item
                for item in ordered
                if item.stage == "Ready" and not item.blocked_by and not item.open_subissues
            ),
            None,
        )
        return WorkboardSnapshot(
            items=ordered,
            in_progress=in_progress,
            next_ready=next_ready,
        )

    def set_stage(self, issue_number: int, stage: str) -> WorkItem:
        stage_key = stage.strip().lower().replace("_", "-").replace(" ", "-")
        if stage_key not in STAGES:
            allowed = ", ".join(STAGES)
            raise WorkboardError(f"Unknown stage {stage!r}. Choose one of: {allowed}")

        snapshot = self.snapshot()
        item = next(
            (candidate for candidate in snapshot.items if candidate.number == issue_number),
            None,
        )
        if item is None:
            raise WorkboardError(f"Issue #{issue_number} is not in ytk Project {PROJECT_NUMBER}")

        stage_name, stage_option, status_option = STAGES[stage_key]
        self._set_single_select(item.item_id, STAGE_FIELD_ID, stage_option)
        self._set_single_select(item.item_id, STATUS_FIELD_ID, status_option)
        return replace(item, stage=stage_name)

    def _set_single_select(self, item_id: str, field_id: str, option_id: str) -> None:
        self._run_gh(
            [
                "project",
                "item-edit",
                "--id",
                item_id,
                "--project-id",
                PROJECT_ID,
                "--field-id",
                field_id,
                "--single-select-option-id",
                option_id,
            ]
        )

    @staticmethod
    def _load_json(raw: str) -> Any:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WorkboardError(f"GitHub CLI returned invalid JSON: {exc}") from exc


def get_snapshot() -> WorkboardSnapshot:
    return WorkboardClient().snapshot()


def set_issue_stage(issue_number: int, stage: str) -> WorkItem:
    return WorkboardClient().set_stage(issue_number, stage)


def format_snapshot(snapshot: WorkboardSnapshot) -> str:
    lines = ["ytk workboard"]
    if snapshot.in_progress:
        for item in snapshot.in_progress:
            lines.append(f"Current: {_format_item(item)}")
    else:
        lines.append("Current: none")
    if snapshot.next_ready is None:
        lines.append("Next: no executable Ready item")
    else:
        lines.append(f"Next: {_format_item(snapshot.next_ready)}")
    lines.append("Startup is read-only. Change Stage only when work explicitly begins.")
    return "\n".join(lines)


def format_queue(snapshot: WorkboardSnapshot) -> str:
    lines = ["ytk work queue"]
    lines.extend(_format_item(item) for item in snapshot.items if item.stage != "Done")
    return "\n".join(lines)


def _format_item(item: WorkItem) -> str:
    return f"#{item.number} {item.title} [{item.priority} | {item.stage} | Order {item.order:g}]"
