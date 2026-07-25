# Inbox rail: reachable and modular (#125)

Date: 2026-07-25
Issue: [#125](https://github.com/pablomoli/ytk/issues/125) — bug(inbox): make the ingest
workspace reachable and modular

## Problem

The inbox right rail puts four unrelated workflows in one undifferentiated control stack,
and its sticky geometry is wrong in two opposite ways depending on scroll position. The
ingest action — the point of the page — is unreachable at every laptop viewport size.

### Measured evidence

Probed against the live hub at `/inbox`, four viewport sizes, both motion preferences:

| viewport | rail bottom past fold | ingest button top | hittable |
|---|---|---|---|
| 1440x900 | +102px | 955 (vh 900) | no |
| 1280x800 | +102px | 955 | no |
| 1280x700 | +102px | 955 | no |
| 1152x620 | +102px | 955 | no |

Scrolling the rail does not rescue it: rail content is 904px against a 900px client
height, so internal overflow yields ~4px of travel while the button sits ~55px below the
fold.

The same defect presents differently by scroll state:

| scroll state | rail top | bottom past fold | first heading |
|---|---|---|---|
| unscrolled | 102 | +102px (ingest stranded) | visible |
| scrolled | 0 | 0 | covered by `.fchip` |

### Root cause

`.rail` is `position: sticky; top: 0; max-height: 100vh`, written as though it were the
only sticky element on the page. It is not: `.hub-nav` (84px) plus the filter chip row
form a sticky stack totalling 102px.

- Unscrolled, the rail's box starts at y=102 and `max-height: 100vh` carries its bottom to
  1002 — exactly `100vh + offset`, so the last 102px is past the fold with no scroll that
  can reach it.
- Scrolled, the rail sticks to `top: 0` and its own headings pass under the filter chips.

Both motion preferences behave identically, so this is a layout defect, independent of the
`#124` reveal bug.

The `calc(100vh - 46px)` constants elsewhere in `styles.css` encode a nav height that no
longer holds (measured 84px, stack 102px). Replacing 46 with 102 would only queue up the
next stale number.

## Design

### 1. Sticky geometry

Declare the sticky stack height once as a custom property and derive from it:

```css
.rail {
  top: var(--sticky-top);
  max-height: calc(100vh - var(--sticky-top));
}
```

The sticky elements composing the stack consume the same variable, so the rail and the
things above it can never disagree. This resolves both failure modes with one value.

`--sticky-top` is a single declared constant, not a computed one. CSS cannot sum the
rendered heights of two sticky elements, and measuring them in JS with a `ResizeObserver`
buys accuracy this page does not need at the cost of a layout dependency in script. The
win is therefore one place to change rather than automatic derivation: if the nav's
padding or the filter row's height changes, this variable must change with it. That is
strictly better than today's four independently stale literals, and the browser probe
would catch the drift.

Scope: correct the stale `100vh - 46px` constants **on the inbox path only**. A full
sweep of `styles.css` is unrelated refactoring.

### 2. Rail decomposition

Four widgets, each a native `<details>/<summary>`:

| widget | contents |
|---|---|
| Queue sources | paste textarea, add, refresh, source pull |
| Profile match | rank, show-matches toggle, batch controls, status |
| Ingest selection | tag chips, thought textarea |
| Job progress | current item, elapsed, failures |

Native disclosure supplies keyboard operation and screen-reader semantics with no
hand-rolled ARIA, satisfying the accessibility criterion by construction.

The rail splits into two regions:

- a **scrollable** stack of the four widgets
- a **pinned footer**, outside the scroll area, holding the selected-count and the ingest
  button

Reachability then follows from structure rather than from how much the user happens to
have collapsed. This is the key decision: collapsing alone cannot guarantee the criterion,
because a user may expand everything.

Tags and the thought textarea stay inside the scrollable ingest widget; only the count and
the action are pinned.

### 3. State and persistence

One pref key per widget, via a minimal extension to `web/src/lib/prefs.ts`:

```ts
export const getPref = (key: string, fallback = false): boolean => { ... }
```

`getPref` currently returns `false` for an unset key and so cannot express "default open".
Adding a fallback parameter fixes that; `setPref` writes `"0"` rather than removing the
key, keeping "unset" distinguishable from "explicitly closed".

Backward compatible: existing stored values are `"1"` or absent, and both continue to read
correctly for `CURSOR_PREF` and `PROFILE_MATCHES_PREF`. Existing single-argument
`getPref` calls keep their current behaviour.

Defaults on a fresh visit:

- Queue sources — open
- Ingest selection — open
- Profile match — collapsed
- Job progress — collapsed

Job progress auto-expands once when a job starts, then honours the user's choice; it does
not re-open itself on every poll.

### 4. Verification

**jsdom (`vitest`)** — what it can hold honestly:

- each widget toggles independently
- fresh-visit defaults match the table above
- prefs round-trip, and an unset key yields the widget's declared default
- the ingest count and button render outside the scrollable region
- job progress auto-expands on transition to running, and stays closed if the user closed
  it afterwards

**Browser probe** — geometry, which jsdom cannot represent (it has no layout; this is the
same reason the `#124` bug escaped its unit test):

- `rail.bottom <= innerHeight`
- the ingest button is hittable via `document.elementFromPoint`
- at 1440x900, 1280x800, 1280x700, 1152x620
- unscrolled and scrolled
- under both `prefers-reduced-motion` settings — the pairing that encodes "full and reduced
  motion produce the same geometry and functionality"

The probe belongs in `scripts/`, matching `smoke_map.py`. It must not join the pytest
suite: `tests/conftest.py` deliberately fails any test that reaches Playwright (#114).

## Acceptance mapping

| Criterion | Satisfied by |
|---|---|
| Ingest reachable at laptop sizes and zoom | pinned footer + corrected `max-height`; browser probe across four viewports |
| No nested scroll trap | rail height derived from `--sticky-top` so the rail scrolls only when its own content genuinely overflows |
| Widgets expand/collapse independently | four independent `<details>`, one pref key each |
| Selection and ingest usable alongside progress/matches | pinned footer is outside the scroll area |
| Keyboard reaches every control predictably | native `<details>/<summary>`; DOM order matches visual order |
| Full and reduced motion identical | asserted in the probe under both preferences |

## Out of scope

- Broader `inbox.tsx` refactoring beyond extracting the four widgets
- A repo-wide sweep of `100vh` constants in `styles.css`
- Visual restyling of the rail; this is geometry and structure, not a redesign
