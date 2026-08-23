# Honest Quality Gates and Bounded Debt Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ytk's local quality signals complete and reproducible, then use those gates to remove stale commentary and split the lowest-risk dialog, source-refresh, and settings monoliths.

**Architecture:** A root `justfile` is the human command surface and delegates the complete gate to `scripts/check-quality`; the pre-commit hook remains incremental. Structural work proceeds only after the local gate is honest: one native-dialog hook, typed source adapters behind the existing hub API, and stateless settings section components behind the existing route-level transaction.

**Tech Stack:** Python 3.13, uv, Ruff, Pyright, pytest, just, React 19, TypeScript 6, Vite+, Vitest browser mode, Playwright, Chromium

## Global Constraints

- No GitHub Actions and no pull request.
- Work only in `/Users/melocoton/Developer/ytk.issue-122-honest-gates`.
- The main checkout's unrelated work remains untouched.
- Frontend tests run in real Chromium through `vp exec vitest run`.
- The repository contains no reference to the retired synthetic DOM environment.
- Pyright remains strict by default with explicit legacy `# pyright: basic` opt-outs.
- The retrieval evaluation remains separate and runs only when a search-stack trigger changes.
- `hub.refresh_sources(force=False, only=None) -> dict` and its response shape remain stable.
- Settings retain one route-level load/save/validation transaction.
- `ytk/cli.py` and `mountMapRenderer` are characterized and planned, not wholesale split.
- No agent contributor or co-author metadata is added to commits.

---

### Task 1: Canonical local command surface

**Files:**
- Create: `justfile`
- Create: `scripts/check-quality`
- Modify: `CLAUDE.md`

**Interfaces:**
- Produces: `scripts/check-quality`, executable from any working directory.
- Produces: `just check` as the complete repository gate.
- Produces: recipes `setup`, `lint`, `format`, `typecheck`, `test`, `test-python`, `test-web`, `build-web`, `eval`, `ui`, `ui-restart`, `chroma-status`, and `install-tool`.

- [ ] **Step 1: Verify the command surface is absent**

Run:

```bash
test ! -f justfile
test ! -f scripts/check-quality
```

Expected: both checks pass because neither interface exists yet.

- [ ] **Step 2: Add the full-gate script**

Create an executable script with this command sequence:

```sh
#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"

uv run --extra dev ruff check ytk scripts tests experiments labs
uv run --extra dev ruff format --check ytk scripts tests experiments labs
uv run --extra dev pyright
uv run --extra dev pytest

cd web
vp lint
vp exec vitest run
vp build
```

- [ ] **Step 3: Add the just recipes**

Create a root `justfile` with `repo := justfile_directory()` and a default recipe
that displays `just --list`. Recipes delegate to uv, Vite+, the installed ytk
CLI, or `scripts/check-quality`; none duplicate gate logic.

The `check` recipe must be:

```make
# Run every supported quality gate.
check:
    "{{ repo }}/scripts/check-quality"
```

The `test-web` recipe must use:

```make
test-web:
    cd "{{ repo }}/web" && vp exec vitest run
```

- [ ] **Step 4: Document the normal workflow and pitfalls**

Add a `Just command reference` section to `CLAUDE.md` containing:

```text
just --list
just setup
just check
just test
just ui
just install-tool
```

Document the full-gate versus incremental-hook distinction, `--extra dev`,
Chromium test command, tracked `web/dist`, live retrieval evaluation,
`uv tool install --reinstall .`, Chroma server diagnostics, and tmux visibility
for long-running commands.

- [ ] **Step 5: Verify recipe discovery and expansion**

Run:

```bash
just --list
just --dry-run check
just --dry-run test
just --dry-run install-tool
sh -n scripts/check-quality
```

Expected: every documented recipe appears, dry runs resolve to the intended
commands, and the shell script parses.

- [ ] **Step 6: Commit the command surface**

```bash
git add justfile scripts/check-quality CLAUDE.md
git commit -m "build: add the local quality command surface"
git push
```

### Task 2: Honest Python lint and hook scope

**Files:**
- Modify: `experiments/encoder_harness/bench_latency.py`
- Modify: `experiments/encoder_harness/export_corpus.py`
- Modify: `experiments/encoder_harness/mlx_agreement.py`
- Modify: `experiments/encoder_harness/retrieval_eval.py`
- Modify: `experiments/migrate_embedder.py`
- Modify: `experiments/reanchor_interest.py`
- Modify: `experiments/visual_encoder_eval.py`
- Modify: `scripts/git-hooks/pre-commit`
- Modify: `pyproject.toml`

**Interfaces:**
- Changes: full Ruff scope is `ytk scripts tests experiments labs`.
- Changes: staged Python matching includes `experiments/` and `labs/`.
- Preserves: retrieval-gate triggers and strict-by-default Pyright policy.

- [ ] **Step 1: Capture the eight current Ruff failures**

Run:

```bash
uv run --extra dev ruff check ytk scripts tests experiments labs
```

Expected: eight fixable findings, all under `experiments/`.

- [ ] **Step 2: Apply Ruff's safe fixes**

Run:

```bash
uv run --extra dev ruff check --fix ytk scripts tests experiments labs
uv run --extra dev ruff format ytk scripts tests experiments labs
```

Inspect the changes and retain runtime behavior.

- [ ] **Step 3: Widen the incremental hook**

Change the staged matcher to:

```sh
py_changed=$(printf '%s\n' "$changed" | grep -E '^(ytk|scripts|tests|experiments|labs)/.*\.py$')
```

Change configuration-triggered lint and format commands and messages to use all
five paths. Update the Pyright message from “basic” to “strict by default with
explicit legacy opt-outs.”

- [ ] **Step 4: Reduce configuration history to current policy**

Replace adoption counts and phase narration in `pyproject.toml` with short
current reasons. Keep rule-specific explanations whose removal would make a
future change unsafe.

- [ ] **Step 5: Verify the complete Python gate**

Run:

```bash
uv run --extra dev ruff check ytk scripts tests experiments labs
uv run --extra dev ruff format --check ytk scripts tests experiments labs
uv run --extra dev pyright
sh -n scripts/git-hooks/pre-commit
```

Expected: all commands exit zero.

- [ ] **Step 6: Commit Python gate honesty**

```bash
git add pyproject.toml scripts/git-hooks/pre-commit experiments
git commit -m "lint: make the complete Python scope honest"
git push
```

### Task 3: Chromium-only frontend hygiene

**Files:**
- Create: `tests/test_repository_hygiene.py`
- Modify: `web/vite.config.ts`
- Modify: `web/vitest.config.ts`
- Modify: `web/src/routes/grove.tsx`
- Modify: `web/src/routes/inbox.tsx`
- Modify: `web/src/components/RailWidget.test.tsx`
- Modify: active frontend tests and comments returned by the repository search
- Modify: superseded plans returned by the repository search

**Interfaces:**
- Produces: a tracked-text hygiene test that forbids the retired environment's
  contiguous package name without embedding that name in the test itself.
- Changes: TanStack ignores `*.test.tsx` route files.
- Changes: Vitest browser imports use `vitest/browser`.

- [ ] **Step 1: Add the failing repository hygiene test**

Create:

```python
from pathlib import Path
import subprocess


def test_retired_dom_environment_is_absent() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = "js" + "dom"
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    offenders = []
    for raw in tracked:
        if not raw:
            continue
        path = root / raw.decode()
        if path.is_file() and forbidden.encode() in path.read_bytes().lower():
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
```

- [ ] **Step 2: Verify the hygiene test fails**

Run:

```bash
uv run --extra dev pytest tests/test_repository_hygiene.py -q
```

Expected: failure listing active tests, configuration comments, and old plans.

- [ ] **Step 3: Remove every tracked reference**

Rewrite active comments around Chromium's actual behavior. Remove obsolete
conditional dialog method installation from browser tests. Correct or remove
superseded plan instructions that would reinstall the retired environment.

- [ ] **Step 4: Fix route, hook, and browser warnings**

Configure TanStack's `routeFileIgnorePattern` for test files. Fix the
`grove.tsx` and `inbox.tsx` dependency arrays from their actual data ownership.
Replace `@vitest/browser/context` with `vitest/browser`.

- [ ] **Step 5: Verify RED becomes GREEN**

Run:

```bash
uv run --extra dev pytest tests/test_repository_hygiene.py -q
cd web
vp lint
vp exec vitest run
vp build
```

Expected: the hygiene test passes; lint has no warnings; route generation and
tests have no route-file, deprecation, or dependency-optimization warnings; 267
or more Chromium tests pass; the build succeeds.

- [ ] **Step 6: Commit Chromium-only hygiene**

```bash
git add tests/test_repository_hygiene.py web docs scripts
git commit -m "test(web): make Chromium the only test contract"
git push
```

### Task 4: Comment-only debt cleanup

**Files:**
- Modify: `AGENTS.md`
- Modify: `pyproject.toml`
- Modify: `scripts/build_map.py`
- Modify: `web/src/lib/mapRenderer.ts`
- Modify: `web/vite.config.ts`
- Modify: `web/src/routes/grove.tsx`
- Modify: `web/src/lib/grove/tree.ts`
- Modify: `web/src/lib/grove/leaf.ts`
- Modify: `web/src/lib/grove/datatree.ts`
- Modify: `ytk/ui/hub.py`
- Modify: any exact duplicate lifecycle explanations located during the sweep

**Interfaces:**
- Produces: repository comment policy in `AGENTS.md`.
- Preserves: WebGL, embedding, mathematical, memory, and benchmark invariants.
- Changes no runtime behavior.

- [ ] **Step 1: Record the comment-debt witness**

Run targeted `rg` searches for prototype/workshop headers, warning-count
history, the bloom discrepancy, the theme-floor history, and conversational
incident narration. Save the matching paths in the task notes.

- [ ] **Step 2: Add the concise policy**

Add:

```text
- Comments explain current invariants, constraints, and reasons. Do not record
  development history, failed attempts, issue phases, or conversational
  narration beside code.
```

- [ ] **Step 3: Remove or relocate the named debt**

Keep short current constraints. Delete commit-history prose and stale labels.
Do not alter executable tokens, shader constants, or configuration values.

- [ ] **Step 4: Prove behavior-neutrality**

Run:

```bash
git diff --word-diff=porcelain
uv run --extra dev ruff check ytk scripts tests experiments labs
cd web && vp lint
```

Inspect every non-comment hunk; none may change runtime behavior.

- [ ] **Step 5: Commit comment cleanup**

```bash
git add AGENTS.md pyproject.toml scripts/build_map.py web ytk/ui/hub.py
git commit -m "docs: remove development-history comments"
git push
```

### Task 5: Shared native dialog lifecycle

**Files:**
- Create: `web/src/lib/useModalDialog.ts`
- Create: `web/src/lib/useModalDialog.test.tsx`
- Modify: `web/src/components/ConfirmDialog.tsx`
- Modify: `web/src/components/ConfirmDialog.test.tsx`
- Modify: `web/src/components/NoteViewer.tsx`
- Modify: `web/src/components/NoteViewer.test.tsx`
- Modify: `web/src/components/QueueItemViewer.tsx`
- Modify: `web/src/components/QueueItemViewer.test.tsx`

**Interfaces:**
- Produces: `useModalDialog(dialogRef: RefObject<HTMLDialogElement | null>): void`.
- Preserves: user intent is delivered only by cancel, button, or backdrop
  handlers; effect cleanup never calls consumer `onClose`.

- [ ] **Step 1: Write failing hook tests**

In Chromium, render a harness under `StrictMode` and assert the dialog becomes
modal, Escape calls the harness cancel handler once, and unmount closes the
dialog without reporting user intent.

- [ ] **Step 2: Verify RED**

Run:

```bash
cd web
vp exec vitest run src/lib/useModalDialog.test.tsx
```

Expected: module-not-found failure.

- [ ] **Step 3: Implement the minimal hook**

Implement:

```ts
import type { RefObject } from "react";
import { useEffect } from "react";

export function useModalDialog(dialogRef: RefObject<HTMLDialogElement | null>) {
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
    };
  }, [dialogRef]);
}
```

- [ ] **Step 4: Migrate all three consumers**

Remove duplicated show/close effects. Keep `NoteViewer`'s GSAP effect focused on
animation only. Keep cancel and backdrop handlers local.

- [ ] **Step 5: Run dialog and full browser tests**

Run:

```bash
cd web
vp exec vitest run src/lib/useModalDialog.test.tsx \
  src/components/ConfirmDialog.test.tsx \
  src/components/NoteViewer.test.tsx \
  src/components/QueueItemViewer.test.tsx
vp exec vitest run
vp lint
```

Expected: all tests pass with no warnings.

- [ ] **Step 6: Commit dialog lifecycle**

```bash
git add web/src/lib/useModalDialog.ts web/src/lib/useModalDialog.test.tsx \
  web/src/components
git commit -m "refactor(web): share native dialog lifecycle"
git push
```

### Task 6: Source refresh adapters

**Files:**
- Create: `ytk/ui/source_refresh.py`
- Create: `tests/test_source_refresh.py`
- Modify: `ytk/ui/hub.py`
- Modify: `tests/test_hub.py`
- Modify: `tests/conftest.py` only if seam registration changes

**Interfaces:**
- Produces: strict typed adapter functions returning inserted counts.
- Preserves: `hub.refresh_sources(force: bool = False, only: set | None = None) -> dict`.
- Preserves: `PULL_SOURCES`, `PULL_SEAMS`, and unit-test live-I/O guards.

- [ ] **Step 1: Add adapter characterization tests**

Cover YouTube deduplication, Pinterest normalization, iMessage prose versus bare
links, and provider count returns with typed fake seams.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run --extra dev pytest tests/test_source_refresh.py -q
```

Expected: import failure because `ytk.ui.source_refresh` does not exist.

- [ ] **Step 3: Implement strict provider adapters**

Create one function per provider. Use `Protocol` or typed callable aliases for
seams; do not use `Any`. The module does not load configuration, acquire locks,
or persist state.

- [ ] **Step 4: Strengthen orchestrator characterization**

Add tests proving a failed provider does not advance its timestamp, later due
providers still run, pruning persists, `only` remains targeted, and auto-ingest
runs after lock release.

- [ ] **Step 5: Reduce `refresh_sources` to orchestration**

Replace provider bodies with adapter calls inside the existing per-source
failure boundary. Keep state load/save, cadence, result shape, pruning, and
post-lock auto-ingest in `hub.py`.

- [ ] **Step 6: Run focused and complete backend gates**

Run:

```bash
uv run --extra dev pytest tests/test_source_refresh.py tests/test_hub.py \
  tests/test_settings.py tests/test_test_hygiene.py -q
uv run --extra dev pyright
uv run --extra dev ruff check ytk tests
```

Expected: all tests pass, Pyright reports zero, and Ruff is clean.

- [ ] **Step 7: Commit source decomposition**

```bash
git add ytk/ui/source_refresh.py ytk/ui/hub.py tests
git commit -m "refactor(hub): separate source refresh adapters"
git push
```

### Task 7: Settings section components

**Files:**
- Create: `web/src/components/settings/SettingsSections.tsx`
- Create: `web/src/components/settings/SettingsSections.test.tsx`
- Modify: `web/src/routes/settings.tsx`
- Create or modify: `web/src/routes/settings.test.tsx`

**Interfaces:**
- Produces: typed section components for hub, cadence, interest, map color,
  ingest filters, misc, environment, tone, experiments, and grove buckets.
- Preserves: one `SettingsConfig` draft and one save mutation in `SettingsPage`.

- [ ] **Step 1: Add route-level characterization**

Mock settings APIs and cover loading, one scalar edit, nullable max duration,
list edit, checkbox edit, rule ordering, save success, validation error, and
revert.

- [ ] **Step 2: Run characterization against the monolith**

Run:

```bash
cd web
vp exec vitest run src/routes/settings.test.tsx
```

Expected: characterization passes before extraction.

- [ ] **Step 3: Add focused section tests**

Render section components with typed fixtures and callbacks. Assert each section
emits the intended immutable update request without fetching or saving the whole
document.

- [ ] **Step 4: Extract stateless sections**

Move `ChipList`, `CheckList`, `GroveBucketsSection`, and the ten visual sections
under `web/src/components/settings/`. Keep query/mutation state, cloning,
validation mapping, dirty detection, save, and revert in the route.

- [ ] **Step 5: Verify frontend behavior**

Run:

```bash
cd web
vp exec vitest run src/routes/settings.test.tsx \
  src/components/settings/SettingsSections.test.tsx
vp lint
vp exec vitest run
vp build
```

Expected: all Chromium tests pass, lint has no warnings, and the build succeeds.

- [ ] **Step 6: Commit settings decomposition**

```bash
git add web/src/routes/settings.tsx web/src/routes/settings.test.tsx \
  web/src/components/settings web/dist
git commit -m "refactor(web): split settings sections"
git push
```

### Task 8: Remaining monolith witness inventory and decomposition plans

**Files:**
- Create: `docs/architecture/cli-decomposition.md`
- Create: `docs/architecture/map-renderer-decomposition.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Produces: dependency-ordered extraction maps for `ytk/cli.py` and
  `mountMapRenderer`.
- Produces: an exact existing-witness inventory and the exact new test required
  before each future extraction step.

- [ ] **Step 1: Map CLI command groups**

Use the structural outline to group commands by ingestion, retrieval, profile,
maintenance, workboard, runtime, and presentation. Record service logic still
embedded in Click callbacks and identify the first leaves that can move without
changing registration.

- [ ] **Step 2: Map renderer ownership**

Record resource creation, resize, frame, and disposal ownership for programs,
targets, terrain, picking, bloom, labels, input, and animation. State the
required witness for each extraction.

- [ ] **Step 3: Record concrete witness requirements**

For every extraction step, name the existing test or probe that protects it.
Where none exists, specify the exact future test file, test function name,
observable input, and assertion in the architecture note. No code moves from
either monolith until that named witness exists and has completed a red-green
cycle.

- [ ] **Step 4: Link the architecture notes**

Add the two documents to the project structure or quality-gate section in
`CLAUDE.md`, without duplicating their contents.

- [ ] **Step 5: Commit decomposition evidence**

```bash
git add docs/architecture CLAUDE.md
git commit -m "docs: plan the remaining monolith extractions"
git push
```

### Task 9: Full verification and close-out

**Files:**
- Modify through vault tools: `second-brain/projects/ytk/session-045-brief.md`
- Modify through vault tools: `second-brain/wiki/hot.md`
- Modify through vault tools: `second-brain/wiki/index.md`
- Update through CLI: GitHub issue #122 and project stage

**Interfaces:**
- Produces: a clean pushed branch with no PR.
- Produces: issue ledger distinguishing completed work from explicit follow-ups.

- [ ] **Step 1: Run the complete gate**

Run:

```bash
just check
! rg -n -i 'js''dom' .
git diff --check
```

Expected: all quality commands pass, the retired environment has zero matches,
and the diff has no whitespace errors.

- [ ] **Step 2: Review the aggregate diff**

List tmux panes, open `hunk diff` in a visible split pane, read the review
session, and resolve every correctness or scope issue found.

- [ ] **Step 3: Re-run affected gates after review fixes**

Run `just check` again after any change. Do not rely on the earlier result.

- [ ] **Step 4: Write session documentation**

Update the vault-only session brief with decisions, verification evidence,
commands, and remaining strictness/monolith follow-ups. Update the vault index
and hot state through the ytk MCP tools.

- [ ] **Step 5: Update issue #122 using CLIs**

Post the acceptance ledger with `gh issue comment 122`. Use:

```bash
uv run ytk work set-stage 122 verify
```

Move to `done` only if every retained acceptance item is complete. Do not create
a pull request.

- [ ] **Step 6: Commit and push close-out**

```bash
git add docs CLAUDE.md
git commit -m "docs: record issue 122 quality completion"
git push
git status --short --branch
```

Expected: branch and remote point to the same commit and the worktree is clean.
