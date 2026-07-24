# Typing / lint / format sweep — inventory

Issue #101 Phase 0, the gate on epic #107. Measured 2026-07-24 in the
worktree branch `worktree-agent-a5004c1712baaca2f`, forked from `master`.

This is the map: what the codebase looked like before the sweep, what each
pass changed, and what was deliberately left alone. Every number below was
produced by the command quoted next to it.

The "After" section is filled in as each pass lands, so a half-finished
sweep still leaves an accurate record rather than a promise.

## Before

### Web — formatting

`cd web && vp check`

```
Found formatting issues in 127 files (758ms, 8 threads).
```

Oxfmt was scanning **everything**, `web/dist` included. `web/dist` is
committed build output that ships inside the Python wheel
(`pyproject.toml` force-includes `web/dist` → `ytk/ui/webdist`), so the
first `vp check --fix` beautified the minified bundle — a 60,667-line diff
across four generated files. See finding F1.

### Web — lint

`cd web && vp lint`

```
Found 12 errors and 3735 warnings in 136 files
```

Split by origin, because almost all of it is noise from the committed
bundle:

| Origin | Errors | Warnings |
|---|---:|---:|
| `dist/` (minified build output) | 12 | 3702 |
| `src/` (hand-written) | 0 | 33 |

The 12 "errors" are all `react-hooks(rules-of-hooks)` firing on minified
React internals inside `dist/assets/index-*.js` — single-letter function
names the rule cannot recognise as components. Zero signal.

`src/` warnings by rule:

| Rule | Count |
|---|---:|
| `react(only-export-components)` | 21 |
| `react-hooks(exhaustive-deps)` | 5 |
| `typescript(unbound-method)` | 4 |
| `eslint(no-unused-expressions)` | 3 |
| **Total** | **33** |

Worth recording against the handoff brief: the type-aware rules it
expected to find in `src/` (`restrict-template-expressions`,
`no-implied-eval`, `no-floating-promises`, and 45 of the 49
`unbound-method` hits) fire **only** inside `dist/`. Hand-written source
is already clean of them. Promoting those rules to error is therefore
cheap — the cost was always the unscoped run, not the code.

### Web — types

`cd web && vp exec tsc -b --force` → exit 0.

`tsconfig.app.json` has `strict`, `noUnusedLocals`, `noUnusedParameters`,
`erasableSyntaxOnly`, `noFallthroughCasesInSwitch`. Missing
`noUncheckedIndexedAccess`, `noImplicitOverride`,
`exactOptionalPropertyTypes`, `noImplicitReturns`.

### Python

No linter, no formatter, no type checker configured at all. `pyproject.toml`
has no `[tool.ruff]`, no `[tool.pyright]`, no mypy.

`uvx ruff check --select E,F,I,UP,B,SIM,RUF --ignore E501 ytk/ scripts/ tests/`
over 166 files:

```
Found 395 errors.
204 fixable with the `--fix` option (85 hidden fixes with `--unsafe-fixes`).
```

Top rules:

| Rule | Count | What |
|---|---:|---|
| `I001` | 83 | unsorted imports |
| `B905` | 52 | `zip()` without explicit `strict=` |
| `B904` | 44 | `raise` without `from` inside `except` |
| `F401` | 32 | unused imports |
| `UP017` | 28 | `datetime.timezone.utc` → `datetime.UTC` |
| `E702` | 18 | multiple statements on one line |
| `UP037` | 15 | quoted annotation |
| `UP024` | 14 | `OSError` alias |
| `E402` | 13 | import not at top of file |
| `RUF046` | 9 | unnecessary `int()` cast |
| `RUF059` | 9 | unused unpacked variable |
| (28 more rules) | 78 | |

Three of these are not style — see findings F3 and F4.

## Findings

Behaviour-relevant things the sweep surfaced. Recorded rather than
silently "fixed", per the brief.

### F1 — `vp check --fix` reformats the committed bundle

Oxfmt had no ignore list, so it rewrote `web/dist/assets/*.js` and `*.css`,
un-minifying shipped build output. Nothing in the repo would have caught
it: `vp build` regenerates `dist` with fresh content hashes, so the
beautified files would simply have been committed and shipped.

**Fixed** — `fmt.ignorePatterns = ["dist/**", "src/routeTree.gen.ts"]` in
`web/vite.config.ts`.

### F2 — formatting splits JSX text nodes

Wrapping a long JSX line makes Oxfmt emit the space-preserving `{" "}`
form, so one text child becomes two:

```
map.tsx:  ... · sil {layout.params.silhouette ...}    (before)
          ... · sil{" "}                              (after)
              {layout.params.silhouette ...}
```

Rendered text is byte-identical; the DOM gets one extra text node. Standard
Prettier/Oxfmt behaviour and safe, but it means the rebuilt bundle differs
from the old one in more than whitespace. Verified by diffing the old and
new minified bundles: exactly **four** differing regions — three of them
this `{" "}` split, one the chunk-hash reference for the lazily-imported
`scene-*.js`. No logic changed.

### F3 — `ytk/sdk.py` cannot be imported on Python 3.11

```
invalid-syntax: Cannot use type parameter lists on Python 3.11
  --> ytk/sdk.py:39:15
   |
39 | def structured[R: BaseModel](
```

PEP 695 type-parameter syntax is 3.12+. `pyproject.toml` declares
`requires-python = ">=3.11"`. The project runs on 3.13 locally so this has
never bitten, but the wheel advertises support for an interpreter it would
crash on at import.

**Not fixed** — raising `requires-python` is a packaging decision, not a
quality fix. `[tool.ruff] target-version = "py313"` makes Ruff parse the
file, which unblocks the sweep but does not resolve the mismatch.

### F4 — two `F821` undefined names in annotations

Both are string annotations, so they never evaluate at runtime and no test
covers them. They break `typing.get_type_hints()` on those symbols and any
type checker.

- `ytk/store.py:990` — `def tag_counts() -> "Counter[str]"`, with
  `from collections import Counter` at line 998, *inside the function
  body*, eight lines below the signature that references it.
- `ytk/transcript.py:26` — `now: "datetime | None" = None`; `datetime` is
  never imported in that module at all.

## After

### Web — formatting (commit 1)

`cd web && vp fmt --check`

```
Checking formatting...
All matched files use the correct format.
Finished in 1291ms on 147 files using 8 threads.
```

122 source files reformatted. `web/dist` no longer touched by the
formatter, and regenerated once by `vp build`.

`cd web && vp test`

```
Test Files  46 passed (46)
     Tests  160 passed (160)
```

`cd web && vp build` → green, `web/dist` committed.
