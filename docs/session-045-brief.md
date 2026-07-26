# ytk — Session 045 Brief

**Date:** 2026-07-26
**Mode:** Honest quality gates and bounded debt reduction

## Outcome

Issue #122 is complete on branch `issue-122-honest-gates`. The repository now
has one documented local command surface, and `just check` truthfully exercises
the full supported Python scope, strict backend typing, fast Python tests,
frontend lint, real-Chromium frontend tests, and the production web build.

GitHub Actions and pull requests were intentionally excluded. This is a
single-contributor repository, so remote PR enforcement would add workflow
machinery without adding a second reviewer or integration boundary. The local
gate is authoritative and is also available as smaller `just` recipes for
focused development.

The retired simulated DOM environment is no longer installed, resolved, or
used. Vitest's upstream lockfile metadata still declares its name as an
optional peer; `autoInstallPeers: false` prevents installation, and a repository
hygiene test rejects authored references and any resolved lockfile package.

## Quality Surface

The root `justfile` documents and exposes the common workflows:

```bash
just setup
just check
just lint
just format
just typecheck
just test
just build-web
just eval
just ui
just ui-restart
just chroma-status
just install-tool
```

`scripts/check-quality` is the implementation behind `just check`. It runs:

1. Ruff lint and formatting over `ytk`, `scripts`, `tests`, `experiments`, and
   `labs`
2. strict Pyright over `ytk`
3. the fast Python suite
4. frontend lint
5. Vitest in Chromium
6. the production web build

The pre-commit hook remains incremental for latency, but now includes
`experiments` and `labs`. Ruff exceptions that depend on initialization order
are path-scoped rather than globally disabling `E402`.

## Debt Reduction

- Replaced development-history and conversational comments with current
  invariants or removed them.
- Added the repository comment policy to `AGENTS.md`.
- Consolidated native `<dialog>` open/close behavior in `useModalDialog`.
- Extracted typed source-provider adapters from `refresh_sources`, leaving the
  hub function responsible for scheduling, isolation, persistence, and
  post-lock auto-ingest.
- Split settings rendering from its draft/save transaction. The route now owns
  loading, cloning, validation, saving, and reverting while
  `SettingsSections` owns section presentation.
- Added witness-first extraction plans for `ytk/cli.py` and
  `web/src/lib/mapRenderer.ts`; both remain behaviorally risky enough that
  extraction without additional characterization would be false progress.

## Verification

```text
Ruff lint                         clean
Ruff format                       212 files formatted
Pyright                           0 errors, 0 warnings
Python tests                      859 passed, 1 deselected
Frontend test files               59 passed
Frontend tests                    278 passed
Frontend production build         passed
Repository hygiene                passed
git diff --check                  clean
```

The production build still reports the pre-existing JavaScript chunk-size
warning for the 1.35 MB main bundle. This is visible debt, not a hidden failure,
and remains separate from issue #122's lint, type, comment, and monolith scope.

## Architecture Documents

- `docs/architecture/cli-decomposition.md`
- `docs/architecture/map-renderer-decomposition.md`
- `docs/superpowers/specs/2026-07-26-quality-gates-and-debt-design.md`
- `docs/superpowers/plans/2026-07-26-quality-gates-and-debt.md`

## Commands

```bash
just --list
just check
git diff --check master...HEAD
gh issue view 122
```
