# Inbox Rail Reachability and Modularity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the inbox ingest action reachable at every laptop viewport and split the rail's four workflows into independently collapsible widgets.

**Architecture:** One CSS custom property (`--sticky-top`) drives both the rail's sticky offset and its max-height, so the rail and the sticky elements above it cannot disagree. The rail splits into a scrollable stack of four native `<details>` widgets plus a footer pinned outside the scroll area holding the selected-count and ingest button, which makes reachability structural rather than contingent on what the user has expanded.

**Tech Stack:** React 19, TypeScript, TanStack Router, vitest + @testing-library/react (jsdom), plain CSS, Playwright (Python) for geometry verification.

## Global Constraints

- Sticky stack height is `--sticky-top: 102px`, declared once in `:root` in `web/src/styles.css`. Never re-hardcode 102 anywhere else; always `var(--sticky-top)`.
- Widgets use native `<details>`/`<summary>`. Do not hand-roll ARIA (`role="button"`, `aria-expanded`) — native disclosure already provides keyboard and screen-reader semantics.
- The selected-count and the ingest `<button>` must render OUTSIDE the rail's scrollable region.
- Fresh-visit defaults: Queue sources open, Ingest selection open, Profile match collapsed, Job progress collapsed.
- `prefs.setPref` must remain backward compatible: existing stored values are `"1"` or absent, and `CURSOR_PREF` / `PROFILE_MATCHES_PREF` must keep reading correctly. Existing single-argument `getPref(key)` calls must keep their current behaviour.
- No emojis anywhere in code, comments, tests, or commit messages.
- Comments explain why, in the codebase's existing voice. No conversational or narrating comments.
- The Playwright probe lives in `scripts/`. It must NOT go in `tests/` — `tests/conftest.py` deliberately fails any test that reaches Playwright (#114).
- Run web tests with `pnpm exec vitest run` from `web/` (not `vp test`, which is broken).

---

### Task 1: prefs gains a default-aware read

**Files:**
- Modify: `web/src/lib/prefs.ts`
- Test: `web/src/lib/prefs.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `getPref(key: string, fallback?: boolean): boolean` and `setPref(key: string, on: boolean): void`. Task 3 relies on `getPref(key, true)` returning `true` when the key is absent.

**Context:** `getPref` currently returns `false` for an unset key, so it cannot express "this widget defaults to open". Adding a fallback parameter fixes that. `setPref` currently REMOVES the key when turning something off, which makes "explicitly closed" indistinguishable from "never set" — it must write `"0"` instead.

- [ ] **Step 1: Write the failing tests**

Append to `web/src/lib/prefs.test.ts`:

```ts
test("getPref returns the fallback when the key is unset", () => {
  expect(getPref("ytk:test:absent", true)).toBe(true);
  expect(getPref("ytk:test:absent", false)).toBe(false);
  expect(getPref("ytk:test:absent")).toBe(false);
});

test("getPref honours an explicit false over a true fallback", () => {
  setPref("ytk:test:closed", false);
  expect(getPref("ytk:test:closed", true)).toBe(false);
});

test("setPref round-trips both directions", () => {
  setPref("ytk:test:rt", true);
  expect(getPref("ytk:test:rt")).toBe(true);
  setPref("ytk:test:rt", false);
  expect(getPref("ytk:test:rt")).toBe(false);
});

test("a legacy stored 1 still reads as on", () => {
  localStorage.setItem("ytk:test:legacy", "1");
  expect(getPref("ytk:test:legacy")).toBe(true);
  expect(getPref("ytk:test:legacy", false)).toBe(true);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && pnpm exec vitest run src/lib/prefs.test.ts`
Expected: FAIL — `getPref("ytk:test:absent", true)` returns `false`, and the explicit-false test fails because `setPref(key, false)` removes the key.

- [ ] **Step 3: Implement**

Replace the two exported functions in `web/src/lib/prefs.ts`:

```ts
/* An unset key is not the same as an explicitly closed one: rail widgets
   need per-widget defaults, so reads take the fallback and writes record
   "0" rather than removing the key. Legacy values are "1" or absent, both
   of which still read correctly. */
export const getPref = (key: string, fallback = false): boolean => {
  try {
    const stored = localStorage.getItem(key);
    return stored === null ? fallback : stored === "1";
  } catch {
    return fallback;
  }
};

export const setPref = (key: string, on: boolean): void => {
  try {
    localStorage.setItem(key, on ? "1" : "0");
  } catch {
    /* private mode */
  }
};
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && pnpm exec vitest run src/lib/prefs.test.ts`
Expected: PASS

- [ ] **Step 5: Run the whole suite for regressions**

Run: `cd web && pnpm exec vitest run`
Expected: all pass. `CURSOR_PREF` and `PROFILE_MATCHES_PREF` consumers are unaffected.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/prefs.ts web/src/lib/prefs.test.ts
git commit -m "feat(prefs): let a read declare its default (#125)"
```

---

### Task 2: correct the rail's sticky geometry

**Files:**
- Modify: `web/src/styles.css` (`:root`, `.rail` at ~line 1170, and the `.rail` entries in the media queries at ~1519 and ~1524)

**Interfaces:**
- Consumes: nothing.
- Produces: the CSS custom property `--sticky-top` on `:root`, and a `.rail` whose bottom no longer passes the fold. Task 4 relies on `.rail-scroll` and `.rail-footer` class names defined here.

**Context:** `.rail` is `position: sticky; top: 0; max-height: 100vh`, written as though it were the only sticky element. It is not: `.hub-nav` (84px) plus the filter chip row form a 102px sticky stack. Unscrolled, the rail's box runs y=102 to 1002 against a 900px viewport — the last 102px sits past the fold with no scroll that reaches it. Scrolled, the rail sticks to 0 and its headings pass under `.fchip`.

Measured evidence at four viewports (1440x900, 1280x800, 1280x700, 1152x620): rail bottom is `+102px` past the fold in every case and the ingest button is not hittable.

- [ ] **Step 1: Declare the custom property**

In `web/src/styles.css`, add to the existing `:root` block:

```css
  /* Height of the sticky stack above the rail: .hub-nav plus the filter
     chip row. CSS cannot sum two sticky elements' rendered heights, so this
     is one declared constant rather than a derived one — change it here if
     either element's height changes. scripts/probe_inbox_rail.py fails if
     it drifts. */
  --sticky-top: 102px;
```

- [ ] **Step 2: Fix `.rail`**

Replace `top: 0;` and `max-height: 100vh;` in the `.rail` rule:

```css
.rail {
  width: 320px;
  flex: 0 0 320px;
  position: sticky;
  top: var(--sticky-top);
  align-self: flex-start;
  max-height: calc(100vh - var(--sticky-top));
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  padding: 1rem;
  box-sizing: border-box;
  background: #181818;
  border-radius: 10px;
  overflow: hidden;
}
```

`overflow-y: auto` moves off `.rail` and onto `.rail-scroll` — the rail itself must not scroll, or the pinned footer would scroll away with it.

- [ ] **Step 3: Add the two regions**

Add immediately after the `.rail` rule:

```css
.rail-scroll {
  flex: 1 1 auto;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  min-height: 0;
}

/* Pinned outside .rail-scroll: the ingest action must stay reachable no
   matter how many widgets are expanded. */
.rail-footer {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-top: 0.7rem;
  border-top: 1px solid var(--line, #3a352c);
}
```

`min-height: 0` is required: a flex child defaults to `min-height: auto`, which refuses to shrink below its content and would push the footer past the rail's bottom edge.

- [ ] **Step 4: Fix the stale constants on the inbox path**

The `.rail` rules inside the media queries at ~line 1519 and ~1524 override `max-height`/`top` with `100vh`-based values. Update any `max-height` there to `calc(100vh - var(--sticky-top))` and any `top: 0` to `top: var(--sticky-top)`. Leave every other `100vh - 46px` in the file alone — those are other pages and out of scope.

- [ ] **Step 5: Verify the build**

Run: `cd web && pnpm build`
Expected: `tsc -b` and the bundle both succeed.

- [ ] **Step 6: Commit**

```bash
git add web/src/styles.css
git commit -m "fix(inbox): derive rail height from the sticky stack (#125)"
```

---

### Task 3: the RailWidget disclosure component

**Files:**
- Create: `web/src/components/RailWidget.tsx`
- Test: `web/src/components/RailWidget.test.tsx`

**Interfaces:**
- Consumes: `getPref`, `setPref` from `../lib/prefs` (Task 1).
- Produces:

```tsx
export function RailWidget({
  title,
  prefKey,
  defaultOpen = false,
  forceOpenKey,
  children,
}: {
  title: string;
  prefKey: string;
  defaultOpen?: boolean;
  forceOpenKey?: string | number | null;
  children: React.ReactNode;
}): JSX.Element
```

Task 4 renders four of these.

**Context:** `forceOpenKey` exists for job progress: when a job starts, the widget should open itself once so a running job is not silently hidden. When the key CHANGES to a new non-null value the widget opens; the user may then close it and it stays closed, because the key does not change again until the next job.

- [ ] **Step 1: Write the failing tests**

Create `web/src/components/RailWidget.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { RailWidget } from "./RailWidget";
import { getPref } from "../lib/prefs";

beforeEach(() => localStorage.clear());

const open = (title: string) =>
  (screen.getByText(title).closest("details") as HTMLDetailsElement).open;

test("uses its declared default when no pref is stored", () => {
  render(
    <>
      <RailWidget title="queue" prefKey="ytk:test:q" defaultOpen>
        <p>q body</p>
      </RailWidget>
      <RailWidget title="match" prefKey="ytk:test:m">
        <p>m body</p>
      </RailWidget>
    </>,
  );
  expect(open("queue")).toBe(true);
  expect(open("match")).toBe(false);
});

test("a stored pref overrides the default", () => {
  localStorage.setItem("ytk:test:q", "0");
  render(
    <RailWidget title="queue" prefKey="ytk:test:q" defaultOpen>
      <p>q body</p>
    </RailWidget>,
  );
  expect(open("queue")).toBe(false);
});

test("toggling persists the new state", () => {
  render(
    <RailWidget title="queue" prefKey="ytk:test:q" defaultOpen>
      <p>q body</p>
    </RailWidget>,
  );
  screen.getByText("queue").click();
  expect(open("queue")).toBe(false);
  expect(getPref("ytk:test:q", true)).toBe(false);
});

test("widgets toggle independently", () => {
  render(
    <>
      <RailWidget title="queue" prefKey="ytk:test:q" defaultOpen>
        <p>q body</p>
      </RailWidget>
      <RailWidget title="match" prefKey="ytk:test:m" defaultOpen>
        <p>m body</p>
      </RailWidget>
    </>,
  );
  screen.getByText("queue").click();
  expect(open("queue")).toBe(false);
  expect(open("match")).toBe(true);
});

test("uses native details and summary rather than hand-rolled ARIA", () => {
  const { container } = render(
    <RailWidget title="queue" prefKey="ytk:test:q">
      <p>q body</p>
    </RailWidget>,
  );
  expect(container.querySelector("details")).toBeTruthy();
  expect(container.querySelector("summary")).toBeTruthy();
  expect(container.querySelector("[aria-expanded]")).toBeNull();
});

test("forceOpenKey opens the widget when it changes to a new value", () => {
  const { rerender } = render(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey={null}>
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(false);
  rerender(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey="job-1">
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(true);
});

test("forceOpenKey does not reopen after the user closes it", () => {
  const { rerender } = render(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey="job-1">
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(true);
  screen.getByText("job").click();
  expect(open("job")).toBe(false);
  rerender(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey="job-1">
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(false);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && pnpm exec vitest run src/components/RailWidget.test.tsx`
Expected: FAIL — module `./RailWidget` does not exist.

- [ ] **Step 3: Implement**

Create `web/src/components/RailWidget.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { getPref, setPref } from "../lib/prefs";

/* One collapsible section of the inbox rail. Native details/summary carries
   the keyboard and screen-reader semantics, so there is no ARIA to maintain
   here. Open state persists per widget, which is why each caller passes its
   own pref key. */
export function RailWidget({
  title,
  prefKey,
  defaultOpen = false,
  forceOpenKey,
  children,
}: {
  title: string;
  prefKey: string;
  defaultOpen?: boolean;
  forceOpenKey?: string | number | null;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(() => getPref(prefKey, defaultOpen));
  /* Opens once per new key, then leaves the user alone: a job that is still
     running must not re-open a section the user deliberately closed. */
  const forced = useRef(forceOpenKey ?? null);

  useEffect(() => {
    const key = forceOpenKey ?? null;
    if (key === null || key === forced.current) return;
    forced.current = key;
    setOpen(true);
    setPref(prefKey, true);
  }, [forceOpenKey, prefKey]);

  const toggle = (event: React.SyntheticEvent<HTMLDetailsElement>) => {
    const next = event.currentTarget.open;
    setOpen(next);
    setPref(prefKey, next);
  };

  return (
    <details className="rail-widget" open={open} onToggle={toggle}>
      <summary>{title}</summary>
      {children}
    </details>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && pnpm exec vitest run src/components/RailWidget.test.tsx`
Expected: PASS (7 tests)

- [ ] **Step 5: Style the widget**

Append to `web/src/styles.css`:

```css
.rail-widget > summary {
  font-weight: 600;
  color: #999;
  cursor: pointer;
  list-style: none;
  padding: 0.2rem 0;
}
.rail-widget > summary::-webkit-details-marker {
  display: none;
}
.rail-widget > summary::before {
  content: "> ";
  display: inline-block;
  transition: transform 0.18s var(--ease);
}
.rail-widget[open] > summary::before {
  transform: rotate(90deg);
}
.rail-widget[open] {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
```

- [ ] **Step 6: Commit**

```bash
git add web/src/components/RailWidget.tsx web/src/components/RailWidget.test.tsx web/src/styles.css
git commit -m "feat(inbox): add the RailWidget disclosure section (#125)"
```

---

### Task 4: split the rail and pin the ingest action

**Files:**
- Modify: `web/src/routes/inbox.tsx` (the `<aside className="rail">` block, currently lines ~255-400)
- Test: `web/src/routes/inbox.test.tsx`

**Interfaces:**
- Consumes: `RailWidget` from `../components/RailWidget` (Task 3); `.rail-scroll` / `.rail-footer` from Task 2.
- Produces: nothing later tasks consume.

**Context:** The rail currently holds four workflows in one flat stack: add-to-queue, profile match, ingest (count + tag chips + thought + button), and job progress. Move each into a `RailWidget`, and move the selected-count and ingest button OUT of the scrollable region into `.rail-footer`. The tag chips and the thought textarea stay inside the ingest widget — only the count and the action are pinned.

Pref keys, exact values:

```ts
const RAIL_QUEUE_PREF = "ytk:inbox:rail:queue";
const RAIL_MATCH_PREF = "ytk:inbox:rail:match";
const RAIL_INGEST_PREF = "ytk:inbox:rail:ingest";
const RAIL_JOB_PREF = "ytk:inbox:rail:job";
```

Put these next to the existing pref constants in `web/src/lib/prefs.ts` and import them, matching how `PROFILE_MATCHES_PREF` is already handled.

- [ ] **Step 1: Write the failing tests**

Append to `web/src/routes/inbox.test.tsx`, following the render/mock helpers already in that file:

```tsx
test("the rail splits into four independently collapsible widgets", async () => {
  renderPage();
  const details = await screen.findAllByRole("group");
  expect(details.length).toBe(4);
});

test("queue and ingest start open, match and job start collapsed", async () => {
  renderPage();
  const openOf = (t: string) =>
    (screen.getByText(t).closest("details") as HTMLDetailsElement).open;
  await screen.findByText("add to queue");
  expect(openOf("add to queue")).toBe(true);
  expect(openOf("ingest")).toBe(true);
  expect(openOf("profile match")).toBe(false);
  expect(openOf("job progress")).toBe(false);
});

test("the ingest action renders outside the rail's scroll region", async () => {
  const { container } = renderPage();
  await screen.findByText("add to queue");
  const footer = container.querySelector(".rail-footer");
  const scroll = container.querySelector(".rail-scroll");
  const ingest = [...container.querySelectorAll("button")].find(
    (b) => b.textContent?.trim() === "ingest",
  );
  expect(footer).toBeTruthy();
  expect(ingest && footer?.contains(ingest)).toBe(true);
  expect(ingest && scroll?.contains(ingest)).toBe(false);
});

test("the selected count renders in the pinned footer", async () => {
  const { container } = renderPage();
  await screen.findByText("add to queue");
  const footer = container.querySelector(".rail-footer");
  expect(footer?.querySelector(".selcount")).toBeTruthy();
});
```

`renderPage()` is the existing helper in that file (line 84). Use it as-is. Do not add a second helper, and do not modify the existing mocks.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && pnpm exec vitest run src/routes/inbox.test.tsx`
Expected: FAIL — no `.rail-footer`, no `<details>` groups.

- [ ] **Step 3: Add the pref keys**

In `web/src/lib/prefs.ts`, next to the existing constants:

```ts
/* Per-widget open state for the inbox rail. Queue and ingest default open:
   they are the common path (paste, select, ingest). */
export const RAIL_QUEUE_PREF = "ytk:inbox:rail:queue";
export const RAIL_MATCH_PREF = "ytk:inbox:rail:match";
export const RAIL_INGEST_PREF = "ytk:inbox:rail:ingest";
export const RAIL_JOB_PREF = "ytk:inbox:rail:job";
```

- [ ] **Step 4: Restructure the rail**

In `web/src/routes/inbox.tsx`, replace the `<aside className="rail">` block. Preserve every existing handler, state variable, and conditional exactly as written — this is a move, not a rewrite. Structure:

```tsx
<aside className="rail">
  <div className="rail-scroll">
    <RailWidget title="add to queue" prefKey={RAIL_QUEUE_PREF} defaultOpen>
      {/* existing textarea + addbox-actions, unchanged */}
    </RailWidget>

    <RailWidget title="profile match" prefKey={RAIL_MATCH_PREF}>
      {/* existing rank button, toggle, batch controls, status, unchanged */}
    </RailWidget>

    <RailWidget title="ingest" prefKey={RAIL_INGEST_PREF} defaultOpen>
      {/* existing chips + thought textarea, unchanged.
          The count and the button move to the footer. */}
    </RailWidget>

    {job.data && (job.data.running || job.data.total > 0) ? (
      <RailWidget
        title="job progress"
        prefKey={RAIL_JOB_PREF}
        forceOpenKey={job.data.running ? job.data.total : null}
      >
        {/* existing progress block, unchanged */}
      </RailWidget>
    ) : null}
  </div>

  <div className="rail-footer">
    <span className="selcount">{sel.size} selected</span>
    <button
      className="btn primary"
      onClick={handleIngest}
      disabled={sel.size === 0 || ingest.isPending}
    >
      ingest
    </button>
  </div>
</aside>
```

Remove the four old `<h2>` elements — `RailWidget`'s `<summary>` replaces them.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd web && pnpm exec vitest run src/routes/inbox.test.tsx`
Expected: PASS

- [ ] **Step 6: Run the whole suite and build**

Run: `cd web && pnpm exec vitest run && pnpm build`
Expected: all tests pass; `tsc -b` clean.

- [ ] **Step 7: Commit**

```bash
git add web/src/routes/inbox.tsx web/src/routes/inbox.test.tsx web/src/lib/prefs.ts
git commit -m "fix(inbox): split the rail and pin the ingest action (#125)"
```

---

### Task 5: prove the geometry in a real browser

**Files:**
- Create: `scripts/probe_inbox_rail.py`

**Interfaces:**
- Consumes: a running hub at `http://127.0.0.1:6969` serving the rebuilt bundle.
- Produces: nothing.

**Context:** jsdom has no layout — every rect is zero — so it cannot represent this bug at all. That is exactly how the sibling #124 defect escaped its unit test. Geometry therefore gets a browser probe, modelled on `scripts/smoke_map.py`. It must NOT live in `tests/`: `tests/conftest.py` fails any test that reaches Playwright (#114).

The hub serves a bundle baked into the installed package, so the probe only sees this work after `cd web && pnpm build && uv tool install --reinstall .` and a hub restart.

- [ ] **Step 1: Write the probe**

Create `scripts/probe_inbox_rail.py`:

```python
"""Geometry gate for the inbox rail (#125).

jsdom reports every rect as zero, so the unit suite cannot see this class of
bug at all — the sibling #124 defect escaped its unit test for exactly that
reason. This asserts the two things the issue actually promises: the rail
never runs past the fold, and the ingest action is genuinely clickable.

Not part of the pytest suite on purpose: it needs a browser and a running
hub, and tests/conftest.py fails any test that reaches Playwright (#114).

Run: uv run python scripts/probe_inbox_rail.py
"""

import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:6969/inbox"
VIEWPORTS = [(1440, 900), (1280, 800), (1280, 700), (1152, 620)]

PROBE = """
() => {
  const rail = document.querySelector('.rail');
  const btns = [...rail.querySelectorAll('button')];
  const ingest = btns.find((b) => b.textContent.trim() === 'ingest');
  const r = rail.getBoundingClientRect();
  const ir = ingest ? ingest.getBoundingClientRect() : null;
  let hittable = false;
  if (ir && ir.width && ir.height) {
    const cx = ir.left + ir.width / 2;
    const cy = ir.top + ir.height / 2;
    if (cy >= 0 && cy <= innerHeight && cx >= 0 && cx <= innerWidth) {
      const hit = document.elementFromPoint(cx, cy);
      hittable = hit === ingest || (hit && ingest.contains(hit));
    }
  }
  return {
    railBottomPastFold: Math.round(r.bottom - innerHeight),
    ingestFound: !!ingest,
    ingestHittable: hittable,
  };
}
"""


def check(page, label: str, failures: list[str]) -> None:
    m = page.evaluate(PROBE)
    ok = m["ingestFound"] and m["ingestHittable"] and m["railBottomPastFold"] <= 0
    print(
        f"  {'PASS' if ok else 'FAIL'} {label}: "
        f"railBottomPastFold={m['railBottomPastFold']} "
        f"ingestHittable={m['ingestHittable']}"
    )
    if not ok:
        failures.append(label)


def main() -> int:
    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for reduced in (False, True):
            motion = "reduce" if reduced else "no-preference"
            for width, height in VIEWPORTS:
                ctx = browser.new_context(
                    viewport={"width": width, "height": height},
                    reduced_motion=motion,
                )
                page = ctx.new_page()
                page.goto(URL)
                page.wait_for_selector(".rail", timeout=20000)
                page.wait_for_timeout(2000)
                check(page, f"{width}x{height} motion={motion}", failures)
                page.evaluate("window.scrollTo(0, 400)")
                page.wait_for_timeout(300)
                check(page, f"{width}x{height} motion={motion} scrolled", failures)
                ctx.close()
        browser.close()
    if failures:
        print(f"\nFAILED {len(failures)} check(s): {failures}")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Deploy the build the hub serves**

```bash
cd web && pnpm build
cd .. && uv tool install --reinstall .
launchctl kickstart -k gui/501/com.ytk.hub
```

Before restarting, check `curl -s localhost:6969/api/ingest/status` — if it reports `"running": true`, an ingest is in flight; wait rather than killing it.

- [ ] **Step 3: Run the probe**

Run: `uv run python scripts/probe_inbox_rail.py`
Expected: `all checks passed` — 16 checks (4 viewports x 2 motion settings x 2 scroll states).

If any check fails, the geometry is still wrong. Do not adjust the probe's thresholds to make it pass.

- [ ] **Step 4: Commit**

```bash
git add scripts/probe_inbox_rail.py
git commit -m "test(inbox): browser geometry gate for the rail (#125)"
```

---

## Self-Review Notes

Spec coverage check against `docs/superpowers/specs/2026-07-25-inbox-rail-design.md`:

| Spec requirement | Task |
|---|---|
| `--sticky-top` variable, both offset and height | 2 |
| Stale `100vh - 46px` on the inbox path only | 2 |
| Four `<details>` widgets | 3, 4 |
| Pinned footer outside scroll area | 2 (CSS), 4 (markup) |
| Per-widget prefs with defaults | 1, 3, 4 |
| `getPref` fallback, `setPref` writes "0", backward compatible | 1 |
| Job progress auto-expands once | 3 (`forceOpenKey`), 4 (wiring) |
| jsdom tests: toggle, defaults, persistence, footer placement | 1, 3, 4 |
| Browser probe: 4 viewports, both motion settings, scrolled and not | 5 |
| Probe in `scripts/`, not pytest | 5 |
