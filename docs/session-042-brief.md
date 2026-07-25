# ytk — Session 042 Brief

**Date:** 2026-07-25
**Mode:** Repository triage and workboard planning

## What Changed

GitHub Project 3 is now the canonical repository workboard:

- Project: <https://github.com/users/pablomoli/projects/3>
- All 65 open issues are present.
- Every item has `Priority`, `Area`, `Kind`, `Stage`, and numeric `Order`.
- GitHub `Status` mirrors active project work.
- The project status update names the current and next work.

The execution contract is:

1. Continue the P0 item already in `In progress`.
2. Otherwise start the lowest `Order` item in `Ready`.
3. Do not start `Needs evidence`, `Triage`, `Verify`, blocked work, or parent initiatives as implementation tickets.

#127 is implemented and in `Verify`. The next Ready sequence is:

1. #114 — stop the test suite from launching a real Playwright browser.
2. #124 — make profile prose readable with full and reduced motion.
3. #125 — make the inbox ingest workspace reachable and modular.
4. #123 — add inspection, provenance, original links, and useful fallbacks.
5. #111 — freeze the retrieval gate's scored corpus.
6. #122 — make lint and type gates honest, then address comment and monolith debt.
7. #126 — replace source chips with persistent multi-select filters.

## Issue Reconciliation

- #21 is now the UI usability initiative and owns #123–#126.
- #120 was closed as a duplicate of the stronger root-cause report in #114.
- Native blockers connect #124, #125, and #122 to #114; #113 to #111; transcript follow-ups to #6; and later map compute work to its prerequisites.
- #127 tracks the shared Codex and Claude Code work-queue integration.

## Current Quality Gates

Ruff is present, but the pre-commit hook runs it only against staged Python files under `ytk/`, `scripts/`, and `tests/`. Repository-wide paths such as `experiments/` and `labs/` are outside that hook, and broad global ignores suppress several rule families everywhere.

Pyright is configured in basic mode for `ytk/ridges.py` only. A green `uv run pyright` is therefore not a backend-wide type signal.

The frontend has strict TypeScript, lint, tests, and a production build, but none run from the repository hook. There is no tracked GitHub Actions workflow, so the only general enforcement is a clone-local, bypassable hook. #122 contains the detailed findings, severity, comment hotspots, and recommended expansion order.

## Agent Integration

#127 is implemented through one shared `ytk.workboard` service backed by the
authenticated `gh` CLI.

CLI:

```bash
ytk work list
ytk work next
ytk work set-stage ISSUE_NUMBER STAGE
```

The MCP server exposes matching `work_list`, `work_next`, and
`work_set_stage` tools. Project-local SessionStart hooks in
`.codex/hooks.json` and `.claude/settings.json` call a hidden context command
that wraps the same snapshot in each runtime's supported JSON envelope.

Startup is read-only and non-blocking. If GitHub is unavailable, the hook
injects a short unavailable message and allows the session to continue.
Blocked tickets and initiatives with open sub-issues are excluded from the
next executable item.

Codex requires one-time review of the checked-in project hook through `/hooks`.
Changing the hook definition invalidates that trust and requires another
review.

GitHub's public ProjectV2 API does not expose saved-view or workflow creation. The project, fields, items, dependencies, values, and status update were configured through `gh`; custom saved views still require an authenticated GitHub web session.

## Verification

```text
Ruff check                         passed
Ruff format --check               passed
Focused CLI/workboard tests       36 passed
Broad suite excluding #114 file   730 passed, 1 deselected
Configured Pyright scope          0 errors
Source and wheel build            passed
Pre-Verify live CLI snapshot      current #127, next #114
Live MCP snapshot                 next #114
Codex/Claude hook JSON            parsed and returned expected context
```

`tests/test_hub.py` remains excluded only because #114 is the next scheduled
repair.

## Exact Commands

```bash
gh project view 3 --owner pablomoli --web
gh project item-list 3 --owner pablomoli --limit 200 --format json
ytk work next
ytk work list
ytk work set-stage 114 in-progress
```
