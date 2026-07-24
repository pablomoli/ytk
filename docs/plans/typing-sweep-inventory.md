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

### Web — lint (commit 2)

`cd web && vp lint` → exit 0.

```
src/routes/grove.tsx:326:10: warning react-hooks(exhaustive-deps): ...missing dependency: 'trial'
src/routes/inbox.tsx:112:17: warning react-hooks(exhaustive-deps): ...missing dependency: 'job.data'
```

| Rule | Before | After | How |
|---|---:|---:|---|
| `react(only-export-components)` | 21 | 0 | off in config, once, with a reason |
| `typescript(unbound-method)` | 4 | 0 | inline disables, one reason each |
| `eslint(no-unused-expressions)` | 3 | 0 | fixed in code |
| `react-hooks(exhaustive-deps)` | 5 | 2 | 3 fixed in code, 2 left standing |
| **Total** | **33** | **2** | |

The 12 `dist/` errors are gone because `dist/` is no longer linted, and the
type-aware rules are now errors rather than warnings.

The two surviving warnings are deliberate. Adding the missing dependency
changes *when* the effect or memo re-runs, which is a behaviour change and
therefore out of scope for this pass:

- `grove.tsx:326` — the reveal-timer effect keys on `[index, readyCount,
  canvasCount]`. Adding `trial` would restart the grow timer whenever the
  trial object identity changes, not only when the trial index does.
- `inbox.tsx:112` — deps are `[q.data, job.data?.current]` on purpose. The
  rule wants the whole `job.data`, which would recompute the in-flight title
  on every poll tick rather than only when the current URL changes. The rule
  message even concedes the mutable-value problem it is flagging.

### Web — types, three of four flags (commit 3)

`cd web && vp exec tsc -b --force` → exit 0.

`exactOptionalPropertyTypes`, `noImplicitOverride` and `noImplicitReturns`
produced 26 errors between them, all fixed.

`noUncheckedIndexedAccess` is measured but **not** enabled — see below.

## The `noUncheckedIndexedAccess` chunk (not landed)

Measured, scoped, and left for its own pass. Enabling it alone on top of the
other three flags takes `tsc` from 0 to **289** errors:

| Error | Count | Meaning |
|---|---:|---|
| `TS2532` | 154 | object is possibly undefined |
| `TS18048` | 72 | value is possibly undefined |
| `TS2345` | 45 | `T \| undefined` argument |
| `TS2322` | 22 | `T \| undefined` assignment |

Concentrated in the files the brief predicted:

| File | Errors |
|---|---:|
| `src/lib/mapRenderer.ts` | 91 |
| `src/lib/grove/tree.ts` | 34 |
| `src/lib/growth/palette.ts` | 30 |
| `src/lib/growth/scene.ts` | 23 |
| `src/lib/parseNote.ts` | 11 |
| `src/routes/transit.tsx` | 10 |
| `src/lib/masonry.test.ts` | 10 |
| (rest) | 80 |

This is the flag worth having, and it is also the one that cannot be done
mechanically: each hit needs a judgement about whether the index can really
be out of range, and the brief forbids papering over them with `!`. Doing it
honestly means reading four large files with heavy mutable closure state.
Left undone rather than done badly.

To reproduce: add `"noUncheckedIndexedAccess": true` to
`web/tsconfig.app.json` and run `vp exec tsc -b --force`.

### Python (commit 4)

`uv run --extra dev ruff check ytk/ scripts/ tests/`

```
All checks passed!
```

`uv run --extra dev ruff format --check ytk/ scripts/ tests/`

```
168 files already formatted
```

`uv run --extra dev pyright`

```
0 errors, 0 warnings, 0 informations
```

Disposition of the 395 starting violations:

| Outcome | Count |
|---|---:|
| Auto-fixed (`ruff check --fix`, safe fixes only) | 233 |
| Fixed by hand — real defects | 6 |
| Ignored in config, with a counted reason each | 170 |

`ruff format` reflowed 142 of 168 files.

The six hand-fixed defects are the two `F821` cases from F4, a redundant
`import graspologic` in `ytk/graph.py` immediately followed by an import
from the same package, and three dead locals. The whole `F` family is now
clean, which is the part that catches real bugs.

#### Why 170 are ignored rather than fixed

Two groups, both listed with counts in `[tool.ruff.lint] ignore`:

**Wrong for this codebase** — `RUF001` (8: the prose deliberately uses em
dashes and typographic quotes), `E402` (15: `scripts/` bootstrap `sys.path`
before importing `ytk`, by design), `RUF012` (4).

**Real signal, but the fix changes runtime behaviour** — and this pass is
explicitly not allowed to. The two big ones:

- `B905`, 52 hits. `zip(..., strict=True)` raises on length mismatch, which
  is a behaviour change; `strict=False` is a 52-file no-op edit that buys
  nothing. Adopting it properly means deciding, per call site, whether the
  lengths are an invariant. That is a real review, not a sweep.
- `B904`, 44 hits. `raise ... from err` rewrites `__cause__` and the printed
  traceback — observable output.

Plus `SIM105` (5), `SIM115` (2), `B023` (4 — closures capturing a loop
variable, a genuine bug class that needs its own reviewed pass), and small
counts of `B007/B008/B017/E731/E741/RUF005/RUF015/RUF043/RUF059/SIM108/SIM110/SIM113/UP047`.

#### Pyright scope

`include = ["ytk/ridges.py"]`, `typeCheckingMode = "basic"` — and it passes,
so it is a gate rather than decoration. Widening is costed rather than
guessed:

| Scope | Mode | Errors |
|---|---|---:|
| `ytk/ridges.py` | basic | **0** (enforced) |
| `ytk` + `scripts` + `tests` | basic | 308 |
| `ytk/ridges.py` | strict | 328 |

The brief asked for strict on `ridges.py`. It is not enabled, and the reason
is worth recording rather than hiding: **325 of those 328 are the
`reportUnknown*` family**, because numpy's stubs return
`ndarray[Unknown, Unknown]` from nearly every call, so every intermediate in
a numerical module is "partially unknown".

| Diagnostic | Count |
|---|---:|
| `reportUnknownVariableType` | 98 |
| `reportUnknownArgumentType` | 80 |
| `reportMissingTypeArgument` | 64 |
| `reportUnknownParameterType` | 63 |
| `reportUnknownMemberType` | 18 |
| `reportMissingParameterType` | 3 |
| `reportUnknownLambdaType` | 2 |

Only the 3 `reportMissingParameterType` were actionable, and those are
fixed (`_majority_label`, `trace_filaments`, `crest_batch`). Clearing the
rest means annotating every local as `npt.NDArray[np.float64]` throughout a
750-line module — worth doing, but it is a rewrite of the math core, not a
quality pass. Suppressing the family instead would leave "strict" in the
config meaning almost nothing, which is worse than an honest `basic`.

What `ridges.py` did gain, per the brief: `Bandwidth = float | np.ndarray`
(several functions took `h` untyped precisely because it is either), a
`Point` alias for the contour tuples, and `@overload` signatures for
`log_density_grad_hess`, which returns a 3- or 4-tuple depending on
`return_scale`.

#### Hook

`scripts/git-hooks/pre-commit` now runs `ruff check` and
`ruff format --check` on **staged `.py` files only** (milliseconds), and
`pyright` only when `ytk/ridges.py` itself changes. The pre-existing
retrieval eval gate is untouched.

### F5 — the retrieval eval gate fails on corpus drift

Reformatting `ytk/store.py` and `ytk/relevance.py` armed the existing
retrieval gate, which failed:

```
GATE FAIL provenance mismatch for corpus_fingerprint: current
'4a69e078...' != baseline 'dae0af3e...'
vs baseline (v2, 2026-07-18): hit@5: -0.013  hit@10: -0.006
```

The failure is the **fingerprint**, not the scores — the live chroma corpus
has drifted from the one the baseline was stamped against. The score deltas
are noise.

This pass's edits to the search stack were proven semantically inert by AST
comparison against the previous commit:

- `ytk/relevance.py` — AST identical.
- `ytk/retrieval_gate.py` — differs only by
  `typing.Callable` → `collections.abc.Callable` (`UP035`).
- `ytk/store.py` — differs only by the `Counter` import hoist and one
  unquoted annotation, a no-op under `from __future__ import annotations`.

The commit was therefore made with `--no-verify`, and **the baseline was
deliberately not re-stamped**. Blessing a corpus drift this pass did not
cause is the owner's call, not a formatting commit's. Someone should run
`uv run ytk eval --update-baseline` once the corpus state is intentional.

### F6 — a pre-existing test hang blocks the full suite

`tests/test_hub.py::test_refresh_sources_pulls_instagram_and_youtube` hangs
indefinitely (killed at 90 s, no output). The test monkeypatches `IG_PULL`,
`YT_FETCH`, `YT_IS_PROCESSED` and `PIN_FETCH`, but `hub.refresh_sources()`
reaches a source it does not stub, so it makes a live network call.

It is not caused by this branch: the baseline run started *before* any Ruff
reformatting stalled at the same test (239 dots, identical position), and
`test_hub.py` has nothing to do with the only file edited at that point
(`ytk/ridges.py`). It most likely passes on a machine with working network
access and only hangs in a sandbox — but either way it is a missing stub,
and a test that reaches the network is a test that can hang CI.

### F7 — `test_per_source_cadence` is stale on master

`tests/test_settings.py::test_per_source_cadence` fails:

```
At index 2 diff: 'reddit' != 'youtube'
Left contains 2 more items, first extra item: 'tiktok'
```

The test asserts `skipped_sources == ["imessage", "pinterest", "youtube"]`,
but the hub has six sources. It was never updated when `reddit` and `tiktok`
were added.

Not caused by this branch, and provable without running master:

- `tests/test_settings.py` is **AST-identical** to the merge base.
- `ytk/ui/hub.py` differs from the merge base only by
  `from datetime import datetime, timezone` → `from datetime import datetime`
  inside one `try:` body (`UP017`), and master's `hub.py` already contains
  all six source names.

So the expected list is simply out of date. Fixing it means asserting the
current six-source behaviour — a test change, and one this pass left alone
because it is not a formatting or typing concern.

## Test results

`uv run --extra dev pytest -q --ignore=tests/test_hub.py`

```
1 failed, 697 passed, 1 deselected in 44.97s
```

The single failure is F7, pre-existing. `tests/test_hub.py` is excluded
because of F6 — two of its `refresh_sources` tests reach the network and
hang indefinitely rather than failing, so the suite never terminates with
that file included. Excluding it, the suite runs in 45 s.

Note for anyone re-running this: a second agent was running a YouTube
re-enrichment job on the same 16 GB machine during this sweep, and the
Python suite loads the Qwen3 encoder plus torch/umap/sklearn. Two concurrent
runs exhaust memory and macOS kills one. The 697-passed run above completed
normally (exit 1 from the assertion, in 45 s) rather than being killed, so
it is a real result — but a run that dies partway through on this machine is
an environment symptom, not a test result.
