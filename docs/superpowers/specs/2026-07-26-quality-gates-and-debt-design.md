# Honest Quality Gates and Bounded Debt Reduction

## Context

Issue #122 began as a repository-wide quality audit, but its type and lint
foundation has already landed:

- Pyright includes the complete `ytk` package.
- Strict mode is the default; legacy modules opt down explicitly with
  `# pyright: basic`.
- Eight modules are strict-clean, and new modules begin strict.
- Ruff already enforces the selected core and adopted rule families.
- Tests and scripts have narrow security-rule exceptions instead of global
  production exceptions.
- The frontend suite runs in real Chromium through Vitest browser mode and
  Playwright.

This design covers the remaining work. It intentionally does not introduce
GitHub Actions or a pull-request workflow. The repository has one developer and
one user, so enforcement should optimize for a reliable local workflow.

## Measured Baseline

The baseline was measured in the isolated `issue-122-honest-gates` worktree.

### Python

- `uv run --extra dev pyright` reports zero errors.
- The full requested Ruff scope has eight fixable errors, all under
  `experiments/`.
- The pre-commit hook checks staged Python only under `ytk/`, `scripts/`, and
  `tests/`.
- A `pyproject.toml` change triggers whole-scope linting, but that scope also
  excludes `experiments/` and `labs/`.
- The hook still describes Pyright as basic even though strict is now the
  configured default with explicit per-file opt-outs.

### Frontend

- The Chromium suite passes 267 tests across 56 files.
- `vp lint` exits zero but reports two `react-hooks/exhaustive-deps` warnings.
- TanStack Router inspects four `*.test.tsx` files under `src/routes/` and warns
  that they do not export routes.
- `RailWidget.test.tsx` imports the deprecated
  `@vitest/browser/context` entry point.
- The production build passes, with the existing large-chunk advisory.

### Retired synthetic-DOM residue

The former synthetic DOM package and test environment were removed in commit
`6fa66474`, but tracked references remain in:

- active component tests and test setup;
- `web/vitest.config.ts`;
- browser-probe and component comments;
- superseded implementation plans.

Those references are now misleading. The repository contract is Chromium, not
dual-environment compatibility.

### Structural hotspots

- `ytk/ui/hub.py::refresh_sources` is 170 lines. It performs scheduling,
  provider pulls, normalization, error collection, pruning, persistence, and
  auto-ingest.
- `web/src/routes/settings.tsx::SettingsPage` is 553 lines and renders ten
  independent settings sections.
- `ytk/cli.py` remains a package-wide command monolith.
- `web/src/lib/mapRenderer.ts::mountMapRenderer` remains the highest-risk
  rendering monolith.
- `ConfirmDialog`, `NoteViewer`, and `QueueItemViewer` duplicate the same native
  dialog mount and cleanup effect.

## Goals

1. Provide one complete, reproducible local quality command.
2. Make checked and excluded paths explicit.
3. Require zero frontend lint and toolchain warnings under the supported
   commands.
4. Remove the retired synthetic DOM from repository vocabulary and test
   assumptions.
5. Remove historical and conversational comment debt without deleting useful
   invariants.
6. Consolidate native dialog lifecycle code under real-browser tests.
7. Extract provider refresh logic from the hub monolith without changing its
   API or partial-failure semantics.
8. Split settings rendering into focused components without changing the
   settings data contract.
9. Add characterization coverage and concrete decomposition plans before any
   broad `cli.py` or `mapRenderer.ts` extraction.

## Non-goals

- GitHub Actions, pull-request automation, or remote branch policies.
- Enabling every Ruff family.
- Making every existing Python module strict in one pass.
- Enabling `noUncheckedIndexedAccess` across the entire frontend.
- A wholesale split of `ytk/cli.py`.
- A wholesale split of `mountMapRenderer`.
- Search-ranking changes or retrieval baseline updates.
- Behavioral redesign of the settings page, source refresh, or native dialogs.

## Design

### 1. Canonical local quality command

Add `scripts/check-quality`, an executable shell entry point that fails on the
first unsuccessful command. It will run from any working directory by resolving
the repository root first.

The command will run:

```text
uv run --extra dev ruff check ytk scripts tests experiments labs
uv run --extra dev ruff format --check ytk scripts tests experiments labs
uv run --extra dev pyright
uv run --extra dev pytest
vp lint
vp exec vitest run
vp build
```

The frontend commands execute from `web/`. The Vitest command uses
`vp exec vitest run`; the integrated `vp test` path is not used because the
current Vite+ beta cannot load the project test binary correctly.

The script is the authoritative definition of “the repository quality gate
passes.” The pre-commit hook remains incremental and fast.

### 2. Honest local hook scope

The staged Python matcher and configuration-change sweep will include
`experiments/` and `labs/`. The current eight experiment violations will be
fixed rather than excluded.

The hook messages will describe the actual Pyright policy: strict by default,
with visible legacy opt-outs. It will not claim that Pyright is basic.

Changing any gate-defining file will run the complete affected scope:

- `pyproject.toml` triggers full Python lint and format checks.
- frontend lint, test, TypeScript, or Vite configuration changes trigger the
  relevant frontend checks.
- `scripts/check-quality` is verified directly by tests rather than recursively
  invoking itself from the hook.

The retrieval hook remains separate and keeps its current file triggers.

### 3. Frontend warning elimination

Fix both hook-dependency warnings according to their actual state ownership.
Neither warning will be suppressed without a reasoned invariant.

Configure the TanStack Router plugin to ignore route test files rather than
renaming tests solely for the router. Update the deprecated Vitest browser
import to `vitest/browser`.

Frontend lint, route generation, and tests must exit with no errors, warnings,
deprecations, or unexpected dependency-optimization reloads. The existing
production chunk-size advisory is not part of #122; it will remain visible and
be recorded separately rather than hidden inside this change.

### 4. Remove retired synthetic-DOM references

The repository will contain no tracked references to the retired environment.

Active tests will stop installing `HTMLDialogElement` methods conditionally as
environment polyfills. Chromium supplies the native methods. Tests may spy on
those methods, but they must exercise native browser behavior.

Comments will describe current Chromium behavior directly. Superseded plans
will be corrected so they cannot instruct a future worker to reinstall the
retired environment or design around its limitations.

The acceptance witness is:

```sh
! rg -n -i 'js''dom' .
```

with no matches.

### 5. Comment policy and cleanup

Comments beside code may document:

- invariants and non-obvious contracts;
- browser, WebGL, or platform constraints;
- mathematical assumptions;
- memory and performance limits;
- benchmark methodology needed to interpret a constant.

Comments beside code must not document:

- implementation history;
- failed attempts or old warning counts;
- issue phases and workshop chronology;
- conversational incident narratives;
- duplicated explanations already represented by an abstraction.

Repository guidance will state this policy briefly. Historical material that
still matters belongs in a design, decision, debugging note, or commit body.

The cleanup will include the locations named by #122, including Ruff adoption
counts, the old `THEME_FLOOR` history, the unexplained bloom discrepancy,
Vite warning counts, grove prototype headers, duplicated dialog explanations,
and the conversational visual-index failure comment.

### 6. Native dialog lifecycle

Add a focused hook:

```ts
useModalDialog(dialogRef: RefObject<HTMLDialogElement | null>): void
```

It owns only mount and cleanup:

- call `showModal()` once when the element is mounted and not already open;
- close the dialog during cleanup if it remains open.

It does not call a consumer’s `onClose`. User intent remains explicit through
`onCancel`, the close button, and backdrop clicks. This preserves the existing
StrictMode-safe contract: cleanup is not treated as user intent.

`ConfirmDialog`, `NoteViewer`, and `QueueItemViewer` will use the hook. Animation
setup and cleanup remains local to `NoteViewer`.

Tests run in Chromium and cover:

- modal opening;
- Escape cancellation;
- close-button behavior;
- backdrop behavior;
- StrictMode remount cleanup;
- `NoteViewer` animation cleanup independently of modal ownership.

### 7. Source refresh decomposition

Keep `hub.refresh_sources(force=False, only=None) -> dict` as the public
orchestrator and preserve its returned shape.

Move provider-specific normalization into a strict new module under
`ytk/ui/`. Each adapter receives typed callables and the mutable `ReelsState`,
then returns the number of inserted items. The six adapters are:

- Instagram
- YouTube
- Pinterest
- TikTok
- Reddit
- iMessage

The hub orchestrator retains:

- the process lock;
- cadence calculation;
- due-source selection;
- state load and save;
- per-provider failure collection;
- pruning already-ingested URLs;
- post-lock auto-ingest scheduling.

Expected provider failures remain isolated: one provider does not prevent other
due providers from running. The returned `errors` list keeps stable
`"<source>: <message>"` entries for the current API contract. Internal logs will
retain exception context without exposing it through unrelated endpoints.

Characterization tests will lock down:

- per-source throttling;
- `only` selection;
- successful count accounting;
- one provider failing while later providers still run;
- failed providers not advancing their cadence timestamp;
- pruning and state persistence;
- iMessage link/prose normalization;
- auto-ingest occurring outside the lock;
- all registered pull seams being stubbed in unit tests.

### 8. Settings component decomposition

Keep query, mutation, draft, saved-state, validation, and dirty-state ownership
in `SettingsPage`.

Move rendering into focused components under
`web/src/components/settings/`:

- `HubSettings`
- `FetchCadenceSettings`
- `InterestSettings`
- `MapColorSettings`
- `IngestFilterSettings`
- `MiscSettings`
- `EnvironmentSettings`
- `EnrichmentToneSettings`
- `ExperimentSettings`

`GroveBucketsSection`, `ChipList`, and `CheckList` move into the same component
area or focused helpers. Section components receive typed values and callbacks;
they do not fetch or save the complete settings document themselves.

This leaves one transaction boundary for saving `SettingsConfig` while making
each visual section independently testable.

Chromium characterization covers:

- loading and initial draft hydration;
- editing representative scalar, nullable, list, checkbox, and ordered-rule
  fields;
- save success and restart messaging;
- validation-path rendering;
- revert behavior;
- refresh and enrichment-preview actions;
- grove bucket persistence.

### 9. Remaining monoliths

`ytk/cli.py` and `mountMapRenderer` will not be mechanically split in this
change.

The implementation will add:

- a responsibility map;
- existing and missing behavioral witnesses;
- a dependency-ordered extraction sequence;
- the first bounded characterization tests where coverage is absent.

The CLI sequence should move service logic out of Click commands before moving
command registration. The renderer sequence should separate resource ownership
before separating frame execution: shader/program setup, targets, terrain,
picking, bloom, labels, input, and animation state.

## Error Handling

- The quality script stops at the first failed command and preserves that
  command’s exit status.
- Source adapters may raise expected provider exceptions to the orchestrator,
  which records the source failure and continues.
- Unexpected programming errors remain visible in logs with traceback context.
- Frontend dialog cleanup checks the native `open` state before closing.
- Settings section components do not catch API errors; the route-level
  transaction boundary continues to translate validation and save failures.

## Verification

The final verification set is:

```text
scripts/check-quality
! rg -n -i 'js''dom' .
git diff --check
git status --short
```

Targeted red-green tests will run during each implementation task. The retrieval
evaluation runs only if a search-stack trigger file changes.

## Delivery

Work lands as reviewable commits on `issue-122-honest-gates` and is pushed
directly. No pull request is created.

The intended sequence is:

1. local gate and honest scopes;
2. frontend warning and retired-environment cleanup;
3. comment-only cleanup;
4. native dialog lifecycle;
5. source refresh extraction;
6. settings component extraction;
7. characterization and decomposition documentation;
8. session documentation and issue update.
