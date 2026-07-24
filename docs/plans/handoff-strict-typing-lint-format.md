# Handoff: strict typing, lint and format sweep (issue #101, Phase 0)

Self-contained brief. Written 2026-07-24. Agent-agnostic — Claude Code or
Codex can execute it; nothing here assumes a particular assistant.

This is the **gate**: epic #107 blocks the entire shader arc (A–G, #103) on
it. Behaviour must not change. Success is boring and objective — the checks
go green and the app looks and behaves exactly as it does now.

## Scope

Three passes, in this order (each lands as its own commit, so a bisect can
find any behaviour regression):

1. **Format** — the mechanical one, biggest diff, zero risk.
2. **Lint** — promote type-aware rules to errors, fix what they surface.
3. **Types** — tighten `tsconfig`, add Python type checking, fix fallout.

Do them in that order: formatting churn first means the later diffs are
readable instead of drowning in whitespace.

## Ground truth as of writing

- Web toolchain is **Vite+** (`vp`), which wraps Vitest / Oxlint / Oxfmt.
  Never invoke pnpm/npm/vitest/oxlint directly (see `web/AGENTS.md`).
- `vp check` currently reports **formatting issues in 127 files**. That is
  the pre-existing drift this pass exists to clear.
- `web/tsconfig.app.json` already has `strict: true`, `noUnusedLocals`,
  `noUnusedParameters`, `noFallthroughCasesInSwitch`. Missing the stricter
  options listed below.
- `vp exec tsc -b` currently exits **0**. Do not regress that.
- `vp lint` runs type-aware with `react`/`typescript`/`oxc` plugins; today
  it reports warnings, not errors, and it scans `dist/` (noise — scope it
  to `src/`).
- **Python has no linter, formatter or type checker configured at all.**
  `pyproject.toml` has no `[tool.ruff]`, no mypy, no pyright. This pass
  introduces them.
- Tests: `uv run --extra dev pytest -q` (23 tests in `tests/test_ridges.py`
  alone; run the whole suite). Web: `vp test` (~47 files).
- A pre-commit hook exists at `scripts/git-hooks/pre-commit` (installed via
  `git config core.hooksPath scripts/git-hooks`) and runs the retrieval
  eval gate when `ytk/store.py`, `ytk/retrieval_gate.py` or `eval/retrieval/`
  change. Do not disturb it; extend it (step 3 below).

## Step 0 — inventory before fixing

Produce the "before" numbers and commit them as
`docs/plans/typing-sweep-inventory.md` so the epic has a record and so any
suppression added later can be justified against a real count:

```bash
cd /Users/melocoton/Developer/ytk/web
vp check 2>&1 | tail -5                     # format drift count
vp lint 2>&1 | tail -30                     # warning inventory by rule
vp exec tsc -b --force 2>&1 | tail -30      # should be clean today
```

Record: files needing format, warning count grouped by rule, and (after
step 3's config change) the type-error count. This inventory is the
deliverable if the sweep runs out of time — a half-finished sweep with a
map of what is left beats a mystery.

## Step 1 — formatting (commit 1)

```bash
cd /Users/melocoton/Developer/ytk/web
vp check --fix
vp test           # must stay green
vp build          # must stay green
```

Then **rebuild and diff-check the bundle**: `web/dist` is committed and
ships inside the Python wheel, so a formatting commit legitimately changes
`dist` hashes. Commit `web/dist` together with the source, exactly as other
commits in this repo do.

Do not hand-edit anything in this pass. If `vp check --fix` produces a
change that looks semantically meaningful, stop and note it — that is a
finding, not a formatting fix.

## Step 2 — lint (commit 2)

In `web/vite.config.ts`, under `lint`:

- Scope the run to `src/` (exclude `dist/`, `routeTree.gen.ts` — generated).
- Promote the type-aware rules from warn to **error**. The ones already
  firing today include `unbound-method`, `restrict-template-expressions`,
  `no-implied-eval` — all real, all in `src/` or generated output.
- Keep `react/rules-of-hooks` at error (already set).

Fix every resulting error. Rules of engagement:

- **No blanket disables.** A `// oxlint-disable-next-line` is acceptable
  only with a one-line reason on the same line, and only where the rule is
  genuinely wrong about this code.
- Prefer fixing the code over loosening the rule.
- If a rule proves to be more noise than signal across many files, turn it
  off **in config, once, with a comment** rather than sprinkling disables.

## Step 3 — types (commit 3 web, commit 4 Python)

### Web

Add to `web/tsconfig.app.json` `compilerOptions`:

```jsonc
"noUncheckedIndexedAccess": true,   // the big one — array/record access yields T | undefined
"noImplicitOverride": true,
"exactOptionalPropertyTypes": true,
"noImplicitReturns": true
```

`noUncheckedIndexedAccess` will produce the bulk of the errors, and it is
the one worth having: this codebase indexes into arrays constantly
(`data.all.domains[point.dom]`, `ramp[i + 1]`, `g.z[jj * g.nx + ii]`), and
several of those genuinely can be `undefined` for out-of-range input.

Fix honestly. `!` non-null assertions are allowed **only** where an
invariant is established a few lines above and is stated in a comment;
otherwise narrow with a guard or provide a default. Note that `map.tsx`
already leans on `map.data!` after early returns — those are fine and can
stay, but do not add new ones without justification.

Files that will need the most attention, in rough order:
`web/src/lib/mapRenderer.ts` (large, mutable closure state, heavy indexing),
`web/src/lib/mapGroups.ts`, `web/src/lib/mapAggregation.ts`,
`web/src/routes/map.tsx`, `web/src/routes/grove.tsx`, `web/src/routes/growth.tsx`.

### Python

Introduce Ruff (lint + format) and a type checker. Add to `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]   # formatter owns line length

[tool.ruff.format]
quote-style = "double"
```

Add `ruff` and `pyright` (or `mypy`) to the `dev` extra. Then:

```bash
uv run --extra dev ruff format ytk/ scripts/ tests/
uv run --extra dev ruff check --fix ytk/ scripts/ tests/
uv run --extra dev pytest -q            # must stay green
```

For the type checker, **do not start at strict across the whole package** —
that produces hundreds of errors in modules this pass has no business
rewriting. Start strict on the math/data core, which is already annotated
and is what the rest of the epic builds on:

```toml
[tool.pyright]
include = ["ytk", "scripts", "tests"]
typeCheckingMode = "basic"

[[tool.pyright.executionEnvironments]]
root = "ytk/ridges.py"
typeCheckingMode = "strict"
```

Complete the annotations in `ytk/ridges.py` first — note that
`log_density_grad_hess` currently has no return annotation (it returns a
3- or 4-tuple depending on `return_scale`; use `@overload` or a union) and
several functions take `h` untyped because it is deliberately
`float | np.ndarray`. Introduce a module-level alias:
`Bandwidth = float | np.ndarray`.

Then widen coverage module by module as far as time allows, recording in
the inventory doc which modules are strict and which are still basic.

### Hook up the gate

Extend `scripts/git-hooks/pre-commit` so Python changes run
`ruff check` and the type checker, mirroring how it already runs the
retrieval eval gate for store/eval changes. Keep it fast — the hook must
not become something worth bypassing.

## Acceptance

- `cd web && vp check` — clean (no format drift, no lint errors)
- `cd web && vp exec tsc -b --force` — exit 0 under the stricter config
- `cd web && vp test` — green
- `uv run --extra dev ruff check ytk/ scripts/ tests/` — clean
- `uv run --extra dev pytest -q` — green (whole suite, not just ridges)
- `cd web && vp build` — green, `web/dist` committed
- **No behaviour change.** Verify /map by eye against the current build:
  fog, web, terrain, shell chips all still render; legend and hover still
  work. A headless screenshot before and after is the cheap proof.
- Inventory doc committed with before/after numbers.

## Gotchas (each of these has already cost a session)

- **The Bash cwd drifts.** After any `cd web && vp ...`, the *next* command
  still starts in `web/`. `git add ytk/...` fails loudly; `uv run python
  scripts/...` fails **silently**. Start every git/uv command with
  `cd /Users/melocoton/Developer/ytk && ...`.
- **`vp check --fix` will touch ~127 files.** Commit it alone. Do not mix
  it with logic changes or review becomes impossible.
- **`web/dist` is committed and shipped in the wheel** (`pyproject.toml`
  force-include maps `web/dist` → `ytk/ui/webdist`). Rebuild and commit it
  whenever `web/src` changes, or the running hub serves stale code.
- **Do not deploy as part of this pass.** No `uv tool install`, no
  `launchctl kickstart`. This is a code-quality pass; deploying is a
  separate, gated action (check `/api/ingest/status` first, then restart as
  a *separate* command — never chain the check and the kickstart).
- **Never use `git worktree` directly** — project convention is the `wt`
  CLI. `wt merge` when done, or `wt remove` after merging manually.
- If another session has uncommitted work in the tree, `git add` explicit
  paths only, never `-A`.

## Out of scope

Idle-stop render loop and GPU picking (the other half of #101) — those are
behaviour changes and belong in their own pass, after this one is green.
