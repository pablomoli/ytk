"""Shared GitHub Project work-queue behavior for CLI, MCP, and hooks."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

# What json.loads can actually hand back. Spelled out so the gh payloads below
# are narrowed on the way in rather than trusted: an unexpected shape from the
# CLI then reads as an empty field, not an AttributeError deep in the parse.
type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


def _as_dict(value: JsonValue) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def _as_list(value: JsonValue) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def _as_str(value: JsonValue) -> str:
    return value if isinstance(value, str) else ""


def _as_int(value: JsonValue) -> int | None:
    """int() of a JSON scalar, or None when the field is absent or not numeric."""
    if isinstance(value, bool) or value is None:
        return None
    return int(value) if isinstance(value, int | float | str) and str(value).isdigit() else None


PROJECT_NUMBER = 3
PROJECT_OWNER = "pablomoli"
PROJECT_ID = "PVT_kwHOA9tX2c4Beb83"
REPOSITORY = "pablomoli/ytk"
STAGE_FIELD_ID = "PVTSSF_lAHOA9tX2c4Beb83zhY2L9I"
STATUS_FIELD_ID = "PVTSSF_lAHOA9tX2c4Beb83zhY2Lww"
KIND_FIELD_ID = "PVTSSF_lAHOA9tX2c4Beb83zhY2L0s"
PRIORITY_FIELD_ID = "PVTSSF_lAHOA9tX2c4Beb83zhY2L0w"
AREA_FIELD_ID = "PVTSSF_lAHOA9tX2c4Beb83zhY2L04"
ORDER_FIELD_ID = "PVTF_lAHOA9tX2c4Beb83zhY2L_o"

STAGES = {
    "triage": ("Triage", "fc0d7e07", "f75ad846"),
    "needs-evidence": ("Needs evidence", "3be8ca3e", "f75ad846"),
    "ready": ("Ready", "c284baa8", "f75ad846"),
    "in-progress": ("In progress", "bd47a3e4", "47fc9ee4"),
    "verify": ("Verify", "a57ba5cb", "47fc9ee4"),
    "done": ("Done", "da33651d", "98236657"),
}

KINDS = {
    "bug": ("Bug", "876a56d3"),
    "ux-debt": ("UX debt", "c00ba423"),
    "feature": ("Feature", "d80cfc4b"),
    "investigation": ("Investigation", "3008fcc0"),
    "maintenance": ("Maintenance", "0ebb6648"),
    "initiative": ("Initiative", "846037e6"),
}

PRIORITIES = {
    "p0": ("P0", "fde7982d"),
    "p1": ("P1", "bac73afb"),
    "p2": ("P2", "f6d637cc"),
    "p3": ("P3", "6d5cca7a"),
}

AREAS = {
    "hub-ui": ("Hub UI", "93f91cba"),
    "capture-and-ingest": ("Capture and ingest", "c06585f7"),
    "retrieval-and-eval": ("Retrieval and eval", "5f632254"),
    "map-growth-and-grove": ("Map growth and grove", "0a5f15d1"),
    "vault": ("Vault", "edf96c19"),
    "platform": ("Platform", "06fb732b"),
    "research": ("Research", "5a5f43aa"),
}

# Every field a triaged item is expected to carry. audit() reports absences here.
REQUIRED_FIELDS = ("kind", "priority", "area", "stage", "order")

# Both gh list reads share one cap so ghost detection can tell when the open-issue
# read saturated: a closed row and an unread row look identical past this line (#162).
ISSUE_LIST_LIMIT = 200


def _slug(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _resolve(table: dict[str, tuple[str, str]], value: str, label: str) -> tuple[str, str]:
    """Map a loose spelling ('in progress', 'Hub UI', 'p1') onto a field option."""
    key = _slug(value)
    if key in table:
        return table[key]
    for name, option in table.values():
        if _slug(name) == key:
            return (name, option)
    raise WorkboardError(f"Unknown {label} {value!r}. Choose one of: {', '.join(table)}")


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
    closed: bool = False


@dataclass(frozen=True)
class FieldUpdate:
    issue_number: int
    kind: str | None = None
    priority: str | None = None
    area: str | None = None
    stage: str | None = None
    order: float | None = None


def _plan_writes(update: FieldUpdate) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Resolve an update into settled display names and (field_id, option_id) writes."""
    resolved: dict[str, str] = {}
    writes: list[tuple[str, str]] = []
    if update.kind is not None:
        resolved["kind"], option = _resolve(KINDS, update.kind, "kind")
        writes.append((KIND_FIELD_ID, option))
    if update.priority is not None:
        resolved["priority"], option = _resolve(PRIORITIES, update.priority, "priority")
        writes.append((PRIORITY_FIELD_ID, option))
    if update.area is not None:
        resolved["area"], option = _resolve(AREAS, update.area, "area")
        writes.append((AREA_FIELD_ID, option))
    if update.stage is not None:
        stage_key = _slug(update.stage)
        if stage_key not in STAGES:
            raise WorkboardError(
                f"Unknown stage {update.stage!r}. Choose one of: {', '.join(STAGES)}"
            )
        resolved["stage"], stage_option, status_option = STAGES[stage_key]
        writes.append((STAGE_FIELD_ID, stage_option))
        writes.append((STATUS_FIELD_ID, status_option))
    return resolved, writes


@dataclass(frozen=True)
class WorkboardSnapshot:
    items: tuple[WorkItem, ...]
    in_progress: tuple[WorkItem, ...]
    next_ready: WorkItem | None
    ghosts: tuple[WorkItem, ...] = ()


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
                    str(ISSUE_LIST_LIMIT),
                    "--json",
                    "number,blockedBy,subIssues,title",
                ]
            )
        )
        issue_state: dict[int, dict[str, JsonValue]] = {}
        for entry in _as_list(issue_payload):
            issue = _as_dict(entry)
            number = _as_int(issue.get("number"))
            if number is not None:
                issue_state[number] = issue
        if len(issue_state) >= ISSUE_LIST_LIMIT:
            # Past the cap, "not in the open set" stops meaning "closed", and
            # archive_ghosts would archive live rows. Refuse rather than guess.
            raise WorkboardError(
                f"Open-issue read saturated at {ISSUE_LIST_LIMIT} rows; "
                "raise ISSUE_LIST_LIMIT before trusting ghost detection"
            )

        def _open_numbers(state: dict[str, JsonValue], field: str) -> tuple[int, ...]:
            nodes = _as_list(_as_dict(state.get(field)).get("nodes"))
            found = (
                _as_int(_as_dict(n).get("number"))
                for n in nodes
                if _as_dict(n).get("state") == "OPEN"
            )
            return tuple(n for n in found if n is not None)

        items: list[WorkItem] = []
        for raw in _as_list(_as_dict(project_payload).get("items")):
            raw_item = _as_dict(raw)
            content = _as_dict(raw_item.get("content"))
            number = _as_int(content.get("number"))
            if content.get("type") != "Issue" or number is None:
                continue
            state = issue_state.get(number, {})
            order = raw_item.get("order")
            item = WorkItem(
                item_id=_as_str(raw_item.get("id")),
                number=number,
                title=_as_str(content.get("title")) or _as_str(raw_item.get("title")),
                url=_as_str(content.get("url")),
                priority=_as_str(raw_item.get("priority")),
                area=_as_str(raw_item.get("area")),
                kind=_as_str(raw_item.get("kind")),
                stage=_as_str(raw_item.get("stage")),
                order=float(order)
                if isinstance(order, int | float) and not isinstance(order, bool)
                else float("inf"),
            )
            items.append(
                replace(
                    item,
                    blocked_by=_open_numbers(state, "blockedBy"),
                    open_subissues=_open_numbers(state, "subIssues"),
                    closed=number not in issue_state,
                )
            )

        ordered = tuple(sorted(items, key=lambda item: (item.order, item.number)))
        # Closed issues stay in items so set_stage/set_fields can still reach
        # their rows, but they must never be recommended as work (#162).
        in_progress = tuple(
            item
            for item in ordered
            if item.stage == "In progress" and not item.open_subissues and not item.closed
        )
        next_ready = next(
            (
                item
                for item in ordered
                if item.stage == "Ready"
                and not item.blocked_by
                and not item.open_subissues
                and not item.closed
            ),
            None,
        )
        return WorkboardSnapshot(
            items=ordered,
            in_progress=in_progress,
            next_ready=next_ready,
            # Closed at Done is the terminal state, not drift; a ghost is a
            # closed issue still holding a live stage (#162).
            ghosts=tuple(item for item in ordered if item.closed and item.stage != "Done"),
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

    def add_issue(self, issue_number: int) -> str:
        """Put an issue on the board, returning its item id. Idempotent."""
        existing = next(
            (item for item in self.snapshot().items if item.number == issue_number),
            None,
        )
        if existing is not None:
            return existing.item_id
        return self._add_item(issue_number)

    def _add_item(self, issue_number: int) -> str:
        payload = self._load_json(
            self._run_gh(
                [
                    "project",
                    "item-add",
                    str(PROJECT_NUMBER),
                    "--owner",
                    PROJECT_OWNER,
                    "--url",
                    f"https://github.com/{REPOSITORY}/issues/{issue_number}",
                    "--format",
                    "json",
                ]
            )
        )
        item_id = _as_str(_as_dict(payload).get("id"))
        if not item_id:
            raise WorkboardError(f"Adding #{issue_number} returned no item id")
        return item_id

    def set_fields(
        self,
        issue_number: int,
        *,
        kind: str | None = None,
        priority: str | None = None,
        area: str | None = None,
        stage: str | None = None,
        order: float | None = None,
        create: bool = False,
    ) -> WorkItem:
        """Set any subset of the board fields on one issue.

        Every value is resolved before the first network call, so a typo costs
        nothing and never leaves the item half-written.
        """
        update = FieldUpdate(
            issue_number=issue_number,
            kind=kind,
            priority=priority,
            area=area,
            stage=stage,
            order=order,
        )
        return self.set_many([update], create=create)[0]

    def set_many(
        self, updates: Sequence[FieldUpdate], *, create: bool = False
    ) -> tuple[WorkItem, ...]:
        """Apply field updates to many issues against a single board read.

        Reading item-list is by far the most expensive call here, so a per-item
        snapshot exhausts the GraphQL budget on a bulk fill.
        """
        planned = [(update, _plan_writes(update)) for update in updates]

        snapshot = self.snapshot()
        by_number = {item.number: item for item in snapshot.items}
        added: dict[int, str] = {}
        if create:
            for update, _ in planned:
                if update.issue_number not in by_number:
                    added[update.issue_number] = self._add_item(update.issue_number)

        results: list[WorkItem] = []
        for update, (resolved, writes) in planned:
            item = by_number.get(update.issue_number)
            if item is None:
                # A just-added item is not in item-list yet, so trust the id
                # add_issue returned rather than the stale read.
                fresh_id = added.get(update.issue_number, "")
                if not fresh_id:
                    raise WorkboardError(
                        f"Issue #{update.issue_number} is not in ytk Project {PROJECT_NUMBER}"
                    )
                item = WorkItem(
                    item_id=fresh_id,
                    number=update.issue_number,
                    title="",
                    url=f"https://github.com/{REPOSITORY}/issues/{update.issue_number}",
                    priority="",
                    area="",
                    kind="",
                    stage="",
                    order=float("inf"),
                )
            for field_id, option in writes:
                self._set_single_select(item.item_id, field_id, option)
            if update.order is not None:
                self._set_number(item.item_id, ORDER_FIELD_ID, update.order)
            settled = replace(item, **resolved)
            if update.order is not None:
                settled = replace(settled, order=float(update.order))
            results.append(settled)
        return tuple(results)

    def audit(
        self,
    ) -> tuple[
        tuple[int, ...],
        tuple[tuple[WorkItem, tuple[str, ...]], ...],
        tuple[WorkItem, ...],
    ]:
        """Open issues missing from the board, board items missing fields, and
        board rows whose issue is closed. Reconciles both directions (#162)."""
        snapshot = self.snapshot()
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
                    str(ISSUE_LIST_LIMIT),
                    "--json",
                    "number",
                ]
            )
        )
        open_numbers = {
            number
            for number in (
                _as_int(_as_dict(entry).get("number")) for entry in _as_list(issue_payload)
            )
            if number is not None
        }
        on_board = {item.number for item in snapshot.items}
        missing = tuple(sorted(open_numbers - on_board))

        incomplete: list[tuple[WorkItem, tuple[str, ...]]] = []
        for item in snapshot.items:
            if item.number not in open_numbers:
                continue
            gaps = tuple(
                field
                for field in REQUIRED_FIELDS
                # order is a float: absent reads as inf, never empty string
                if (item.order == float("inf") if field == "order" else not getattr(item, field))
            )
            if gaps:
                incomplete.append((item, gaps))
        return missing, tuple(incomplete), snapshot.ghosts

    def archive_ghosts(self) -> tuple[WorkItem, ...]:
        """Archive every board row whose issue is closed; returns what was archived."""
        ghosts = self.snapshot().ghosts
        for item in ghosts:
            self._run_gh(
                [
                    "project",
                    "item-archive",
                    str(PROJECT_NUMBER),
                    "--owner",
                    PROJECT_OWNER,
                    "--id",
                    item.item_id,
                ]
            )
        return ghosts

    def _set_number(self, item_id: str, field_id: str, value: float) -> None:
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
                "--number",
                str(value),
            ]
        )

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
    def _load_json(raw: str) -> JsonValue:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WorkboardError(f"GitHub CLI returned invalid JSON: {exc}") from exc


def get_snapshot() -> WorkboardSnapshot:
    return WorkboardClient().snapshot()


def set_issue_stage(issue_number: int, stage: str) -> WorkItem:
    return WorkboardClient().set_stage(issue_number, stage)


def set_issue_fields(
    issue_number: int,
    *,
    kind: str | None = None,
    priority: str | None = None,
    area: str | None = None,
    stage: str | None = None,
    order: float | None = None,
    create: bool = False,
) -> WorkItem:
    return WorkboardClient().set_fields(
        issue_number,
        kind=kind,
        priority=priority,
        area=area,
        stage=stage,
        order=order,
        create=create,
    )


def audit_board() -> tuple[
    tuple[int, ...],
    tuple[tuple[WorkItem, tuple[str, ...]], ...],
    tuple[WorkItem, ...],
]:
    return WorkboardClient().audit()


def archive_board_ghosts() -> tuple[WorkItem, ...]:
    return WorkboardClient().archive_ghosts()


def format_audit(
    missing: tuple[int, ...],
    incomplete: tuple[tuple[WorkItem, tuple[str, ...]], ...],
    ghosts: tuple[WorkItem, ...],
) -> str:
    lines = ["ytk workboard audit"]
    if missing:
        lines.append(f"Open but not on the board ({len(missing)}):")
        lines.extend(f"  #{number}" for number in missing)
    else:
        lines.append("Open but not on the board: none")
    if incomplete:
        lines.append(f"On the board with missing fields ({len(incomplete)}):")
        lines.extend(
            f"  #{item.number} missing {', '.join(gaps)} — {item.title}"
            for item, gaps in incomplete
        )
    else:
        lines.append("On the board with missing fields: none")
    if ghosts:
        lines.append(f"Board rows whose issue is closed ({len(ghosts)}):")
        lines.extend(f"  #{item.number} [{item.stage}] — {item.title}" for item in ghosts)
        lines.append("Archive them with: ytk work audit --fix (or work_audit fix=true)")
    else:
        lines.append("Board rows whose issue is closed: none")
    return "\n".join(lines)


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
    row = f"#{item.number} {item.title} [{item.priority} | {item.stage} | Order {item.order:g}]"
    if item.closed:
        row += " [issue closed — ghost row, run work audit --fix]"
    return row
