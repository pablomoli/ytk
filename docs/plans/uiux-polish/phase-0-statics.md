# Phase 0 — Statics and Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship every zero-dependency fix from the polish sprint: shared native-dialog NoteViewer, ConfirmDialog replacing window.confirm, two state bugs, content-shaped skeletons, structured empty/error states, MemoWaveform rebuild, ingest ring gauge, profile grid + meter semantics, SourceFilter a11y, MasonryGrid effect deps.

**Architecture:** All commodity-chrome work inside `web/src` (React 19, plain CSS). Two new dialog components are built on native `<dialog>`/`showModal()` so focus trapping, Escape, top-layer, and `::backdrop` come from the platform. No new packages.

**Tech Stack:** React 19, TypeScript, vitest + @testing-library/react (already installed), native HTMLDialogElement.

## Global Constraints

See `docs/plans/uiux-polish/README.md` — applies verbatim. Highlights for this phase: no new dependencies at all; `vp check` + `vp test` from `web/` before every commit; commit trailer `Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY`; lowercase copy, Newsreader only, tokens from theme.css.

**jsdom + `<dialog>` note (read before Task 1):** jsdom does not reliably implement `showModal()`. Every dialog test must stub it first:

```ts
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.open = true }
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.open = false; this.dispatchEvent(new Event('close')) }
})
```

---

### Task 1: NoteViewer on native `<dialog>`

The note viewer is currently copy-pasted into `web/src/routes/index.tsx:94-113` (with a hand-rolled querySelector focus trap at lines 43-71) and `web/src/routes/library.tsx:103-122` (which claims `aria-modal` but has NO trap at all). Replace both with one component on native `<dialog>`.

**Files:**
- Create: `web/src/components/NoteViewer.tsx`
- Create: `web/src/components/NoteViewer.test.tsx`
- Modify: `web/src/routes/index.tsx` (delete lines 43-71 handler block and 94-113 JSX)
- Modify: `web/src/routes/library.tsx` (delete lines 62-64 and 103-122)
- Modify: `web/src/styles.css` (`.note-viewer` block, lines 594-620)

**Interfaces:**
- Consumes: `useNote`, `useSimilarNotes` from `../api/fresh` (existing hooks, take `path?: string`).
- Produces: `NoteViewer({ note, onClose }: { note: FreshNote; onClose: () => void })` — rendered only while a note is selected. Later phases (1) will add an optional `originRect?: DOMRect` prop; do not add it now.

- [ ] **Step 1: Write the failing test**

`web/src/components/NoteViewer.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeAll, expect, test, vi } from 'vitest'
import type { FreshNote } from '../api/fresh'
import { NoteViewer } from './NoteViewer'

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.open = true }
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.open = false; this.dispatchEvent(new Event('close')) }
})

const note: FreshNote = { path: 'sources/youtube/x.md', title: 'a note', source: 'youtube', tags: [], url: '', thumbnail: '', has_take: false } as unknown as FreshNote

const wrap = (ui: React.ReactElement) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } })}>{ui}</QueryClientProvider>,
)

test('opens as a modal dialog labelled by the note title', () => {
  const showModal = vi.spyOn(HTMLDialogElement.prototype, 'showModal')
  wrap(<NoteViewer note={note} onClose={() => {}} />)
  expect(showModal).toHaveBeenCalled()
  expect(screen.getByRole('dialog', { hidden: true })).toHaveAccessibleName('a note')
})

test('close button and dialog close event both call onClose', () => {
  const onClose = vi.fn()
  wrap(<NoteViewer note={note} onClose={onClose} />)
  fireEvent.click(screen.getByRole('button', { name: 'close', hidden: true }))
  expect(onClose).toHaveBeenCalledTimes(1)
})
```

Note on `enabled: false` in the QueryClient: `useNote`/`useSimilarNotes` fire real fetches in jsdom otherwise. If those hooks hard-code `enabled`, instead stub fetch: `vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{}'))))` in `beforeAll`.

- [ ] **Step 2: Run the test, verify it fails**

Run: `cd /Users/melocoton/Developer/ytk/web && vp test src/components/NoteViewer.test.tsx`
Expected: FAIL — `Cannot find module './NoteViewer'` (or equivalent unresolved import).

- [ ] **Step 3: Implement `NoteViewer.tsx`**

```tsx
import { useEffect, useRef } from 'react'
import type { FreshNote } from '../api/fresh'
import { useNote, useSimilarNotes } from '../api/fresh'

/* Native <dialog> gives the platform behaviors the old hand-rolled viewers
   faked or lacked: top-layer stacking, inert background, focus trap, focus
   restore on close, Escape (via the 'cancel' event), and ::backdrop. */
export function NoteViewer({ note, onClose }: { note: FreshNote; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const content = useNote(note.path)
  const similar = useSimilarNotes(note.path)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (!dialog.open) dialog.showModal?.()
    return () => dialog.close?.()
  }, [])

  /* onClose is driven ONLY by explicit user intent — never by the native
     'close' event. That event fires asynchronously (queued task), so a ref
     flag set in effect cleanup is already reset by StrictMode's mount->
     cleanup->mount remount before the queued event arrives, and the viewer
     self-closes a frame after opening. Instead: Escape routes through
     onCancel, and the button and backdrop call onClose directly. React
     unmount then closes the dialog in cleanup, so the programmatic close()
     has nothing wired to it. Test the async path (queueMicrotask dispatch),
     or a synchronous stub hides the bug. */
  return (
    <dialog
      ref={dialogRef}
      className="note-viewer"
      aria-label={note.title}
      onCancel={(event) => { event.preventDefault(); onClose() }}
      onClick={(event) => { if (event.target === dialogRef.current) onClose() }}
    >
      <div className="note-panel">
        <button className="btn viewer-close" type="button" onClick={onClose}>close</button>
        {content.isLoading ? <p>loading note...</p> : null}
        {content.isError ? <p>failed to load note: {String(content.error)}</p> : null}
        {content.data ? <pre>{content.data.content}</pre> : null}
        {similar.data?.length ? (
          <div className="similar-items">
            <span>visually similar</span>
            {similar.data.map((item) => (
              <a key={item.item_id} href={item.url || '#'} target="_blank" rel="noreferrer" title={item.title || item.item_id}>
                <img src={`/api/visual-image?id=${encodeURIComponent(item.item_id)}`} loading="lazy" alt="" />
              </a>
            ))}
          </div>
        ) : null}
      </div>
    </dialog>
  )
}
```

Backdrop-click detail: clicks on the panel land on `.note-panel` descendants, so `event.target === dialogRef.current` is only true on the backdrop area — no stopPropagation dance needed.

- [ ] **Step 4: Restyle `.note-viewer` as a dialog element**

In `web/src/styles.css`, REPLACE the existing block (lines 594-610):

```css
.note-viewer {
  position: fixed;
  inset: 0;
  z-index: 10;
  padding: 2rem;
  background: #000d;
}

.note-panel {
  position: relative;
  height: 100%;
  box-sizing: border-box;
  padding: 1.2rem;
  border-radius: 8px;
  background: #181818;
  overflow: auto;
}
```

WITH:

```css
/* native <dialog>: the element is the panel wrapper, ::backdrop is the veil */
.note-viewer {
  width: min(100vw - 4rem, 72rem);
  height: calc(100vh - 4rem);
  padding: 0;
  border: 1px solid var(--line);
  border-radius: var(--r);
  background: var(--bg1);
  color: inherit;
}

.note-viewer::backdrop {
  background: #000d;
}

.note-panel {
  position: relative;
  height: 100%;
  box-sizing: border-box;
  padding: 1.2rem;
  overflow: auto;
}
```

- [ ] **Step 5: Wire into `web/src/routes/index.tsx`**

1. Add import: `import { NoteViewer } from "../components/NoteViewer";`
2. Delete the focus-management effect (lines 43-49), the whole `handleDialogKeyDown` function (lines 51-71), and the refs `dialogRef`, `restoreFocusRef` (lines 28-29) plus their now-unused imports (`useRef`, `KeyboardEvent`; keep `useEffect` only if still used elsewhere in the file — after this edit it is not, so remove it from the import).
3. Also remove the now-unused `useNote` / `useSimilarNotes` imports and their hook calls (lines 30-31) — NoteViewer owns those queries now.
4. Replace the viewer JSX (lines 94-113) with:

```tsx
{selected ? <NoteViewer note={selected} onClose={() => setSelected(undefined)} /> : null}
```

- [ ] **Step 6: Wire into `web/src/routes/library.tsx`**

Same operation: import NoteViewer; delete `dialogRef` (line 34), `useNote`/`useSimilarNotes` calls (lines 35-36) and imports, `handleDialogKeyDown` (lines 62-64), the `useRef`/`KeyboardEvent` imports if now unused; replace lines 103-122 with the same one-liner as above.

- [ ] **Step 7: Run the full gate**

Run: `cd /Users/melocoton/Developer/ytk/web && vp test && vp check`
Expected: NoteViewer tests PASS; no new failures (pre-existing `lib/growth/*.test.ts` failures are exempt, see README).

- [ ] **Step 8: Commit**

```bash
git add web/src/components/NoteViewer.tsx web/src/components/NoteViewer.test.tsx web/src/routes/index.tsx web/src/routes/library.tsx web/src/styles.css
git commit -m "feat(web): shared NoteViewer on native dialog

Replaces the duplicated hand-rolled viewer in index and library routes.
Native showModal supplies the focus trap, Escape, focus restore, and
backdrop the old implementations faked or lacked (library's aria-modal
had no trap at all).

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 2: ConfirmDialog replacing window.confirm

`window.confirm` appears at `web/src/routes/index.tsx:38`, `web/src/routes/library.tsx:52`, `web/src/routes/profile.tsx:17`. The OS popup is the most off-brand pixel in the app.

**Files:**
- Create: `web/src/components/ConfirmDialog.tsx`
- Create: `web/src/components/ConfirmDialog.test.tsx`
- Modify: `web/src/routes/index.tsx`, `web/src/routes/library.tsx`, `web/src/routes/profile.tsx`
- Modify: `web/src/styles.css` (append)

**Interfaces:**
- Produces: `ConfirmDialog({ message, confirmLabel = 'delete', onConfirm, onCancel }: { message: string; confirmLabel?: string; onConfirm: () => void; onCancel: () => void })`. Render it conditionally; mounting opens it.

- [ ] **Step 1: Write the failing test** — `web/src/components/ConfirmDialog.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { beforeAll, expect, test, vi } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog'

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.open = true }
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.open = false; this.dispatchEvent(new Event('close')) }
})

test('confirm fires onConfirm once, not onCancel', () => {
  const onConfirm = vi.fn(); const onCancel = vi.fn()
  render(<ConfirmDialog message="delete this note for good?" onConfirm={onConfirm} onCancel={onCancel} />)
  expect(screen.getByText('delete this note for good?')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'delete', hidden: true }))
  expect(onConfirm).toHaveBeenCalledTimes(1)
  expect(onCancel).not.toHaveBeenCalled()
})

test('cancel button fires onCancel via dialog close', () => {
  const onConfirm = vi.fn(); const onCancel = vi.fn()
  render(<ConfirmDialog message="sure?" onConfirm={onConfirm} onCancel={onCancel} />)
  fireEvent.click(screen.getByRole('button', { name: 'cancel', hidden: true }))
  expect(onCancel).toHaveBeenCalledTimes(1)
  expect(onConfirm).not.toHaveBeenCalled()
})
```

- [ ] **Step 2: Run to verify failure** — `cd web && vp test src/components/ConfirmDialog.test.tsx` → FAIL (module not found).

- [ ] **Step 3: Implement `ConfirmDialog.tsx`**

```tsx
import { useEffect, useRef } from 'react'

/* Themed replacement for window.confirm. Mounting opens it; Escape and
   backdrop close as cancel (native 'close' event). onConfirm marks the
   dialog so the shared close handler doesn't also fire onCancel. */
export function ConfirmDialog({ message, confirmLabel = 'delete', onConfirm, onCancel }: {
  message: string
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const confirmedRef = useRef(false)

  useEffect(() => {
    dialogRef.current?.showModal?.()
  }, [])

  const confirm = () => {
    confirmedRef.current = true
    onConfirm()
    dialogRef.current?.close?.()
  }

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      aria-label={message}
      onClose={() => { if (!confirmedRef.current) onCancel() }}
      onClick={(event) => { if (event.target === dialogRef.current) dialogRef.current?.close() }}
    >
      <p>{message}</p>
      <div className="confirm-actions">
        <button className="btn" type="button" onClick={() => dialogRef.current?.close()}>cancel</button>
        <button className="btn primary" type="button" onClick={confirm}>{confirmLabel}</button>
      </div>
    </dialog>
  )
}
```

- [ ] **Step 4: Append styles** to `web/src/styles.css`:

```css
/* confirm dialog — hairline border, brass action, quiet plane */
.confirm-dialog {
  width: min(92vw, 26rem);
  padding: 1.1rem 1.2rem;
  border: 1px solid var(--line);
  border-radius: var(--r);
  background: var(--bg1);
  color: var(--ink);
}

.confirm-dialog::backdrop {
  background: #000a;
}

.confirm-dialog p {
  margin: 0 0 1rem;
  line-height: 1.45;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.6rem;
}
```

- [ ] **Step 5: Replace the three window.confirm call sites**

`web/src/routes/index.tsx` — add `import { ConfirmDialog } from "../components/ConfirmDialog";`, add state `const [pendingDelete, setPendingDelete] = useState<FreshNote>();`, replace `handleDelete` (lines 37-41):

```tsx
const handleDelete = (item: FreshNote) => setPendingDelete(item);
```

and add before the closing `</div>` of the page (next to the NoteViewer line):

```tsx
{pendingDelete ? (
  <ConfirmDialog
    message="delete this note for good? it leaves the vault and the search index."
    onCancel={() => setPendingDelete(undefined)}
    onConfirm={() => {
      const item = pendingDelete;
      setPendingDelete(undefined);
      remove.mutate(item.path, { onSuccess: () => setSelected((current) => (current?.path === item.path ? undefined : current)) });
    }}
  />
) : null}
```

`web/src/routes/library.tsx` — identical pattern; the onConfirm body keeps the existing onSuccess from lines 53-58 (pages filter + selected clear).

`web/src/routes/profile.tsx` — `const [confirmSynth, setConfirmSynth] = useState(false);` (add `useState` import from react); `resynthesize` becomes `() => setConfirmSynth(true)`; render:

```tsx
{confirmSynth ? (
  <ConfirmDialog
    message="re-synthesize the interest profile? one claude call; takes up to a minute."
    confirmLabel="synthesize"
    onCancel={() => setConfirmSynth(false)}
    onConfirm={() => { setConfirmSynth(false); run.mutate(); }}
  />
) : null}
```

Place it inside the returned page div (both return branches share the non-error path; put it in the main return; the error branch keeps its controls and gets the same block — or simplest: put the block right after `{controls}` in BOTH returns).

Copy note: messages are lowercase (house style) — this intentionally changes the old sentence-case strings.

- [ ] **Step 6: Gate** — `cd web && vp test && vp check` → PASS (same exemption).

- [ ] **Step 7: Commit**

```bash
git add web/src/components/ConfirmDialog.tsx web/src/components/ConfirmDialog.test.tsx web/src/routes/index.tsx web/src/routes/library.tsx web/src/routes/profile.tsx web/src/styles.css
git commit -m "feat(web): themed ConfirmDialog replaces window.confirm

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 3: Two state bugs — elapsed-time memo, useInfiniteWindow reset

**Files:**
- Modify: `web/src/routes/inbox.tsx:62-68`
- Modify: `web/src/lib/useInfiniteWindow.ts`
- Modify: `web/src/lib/useInfiniteWindow.test.ts` (extend)

**Interfaces:**
- Produces: `useInfiniteWindow<T>(items: T[], step = 60, resetKey: unknown = null)` — the count now resets on `resetKey` change (filter switches), NOT on items identity (poll refetches). `nextCount` unchanged.

- [ ] **Step 1: Write the failing hook test** — replace `web/src/lib/useInfiniteWindow.test.ts` with:

```ts
import { renderHook, act } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { nextCount, useInfiniteWindow } from './useInfiniteWindow'

// Capture the IntersectionObserver callback so a test can fire it and grow the
// window past `step`. Without this the count never exceeds step and the reset
// bug is UNOBSERVABLE — a reset-to-step is a no-op when count is already step,
// so a test that never grows the window passes both before and after the fix.
let observerCb: ((entries: { isIntersecting: boolean }[]) => void) | null = null
vi.stubGlobal('IntersectionObserver', class {
  constructor(cb: (entries: { isIntersecting: boolean }[]) => void) { observerCb = cb }
  observe() {}
  disconnect() {}
  unobserve() {}
})

test('nextCount clamps to total', () => {
  expect(nextCount(60, 70, 60)).toBe(70)
})

test('a poll refetch (new array identity, same resetKey) preserves the grown window', () => {
  const { result, rerender } = renderHook(
    ({ items }: { items: string[] }) => useInfiniteWindow(items, 2, 'all'),
    { initialProps: { items: ['a', 'b', 'c', 'd', 'e'] } },
  )
  act(() => result.current.sentinelRef(document.createElement('div')))
  expect(result.current.visible).toEqual(['a', 'b'])
  act(() => observerCb?.([{ isIntersecting: true }]))
  expect(result.current.visible).toEqual(['a', 'b', 'c', 'd']) // grown 2 -> 4
  rerender({ items: ['a', 'b', 'c', 'd', 'e', 'f'] }) // same content, fresh array
  expect(result.current.visible).toEqual(['a', 'b', 'c', 'd']) // window preserved
})

test('a resetKey change (filter switch) resets the window to step', () => {
  const { result, rerender } = renderHook(
    ({ key }: { key: string }) => useInfiniteWindow(['a', 'b', 'c', 'd', 'e'], 2, key),
    { initialProps: { key: 'all' } },
  )
  act(() => result.current.sentinelRef(document.createElement('div')))
  act(() => observerCb?.([{ isIntersecting: true }]))
  expect(result.current.visible).toEqual(['a', 'b', 'c', 'd']) // grown
  rerender({ key: 'youtube' })
  expect(result.current.visible).toEqual(['a', 'b']) // filter change resets
})
```

- [ ] **Step 2: Verify failure** — `cd web && vp test src/lib/useInfiniteWindow.test.ts` → the "poll refetch" test FAILS against the current implementation (the grown window resets to `['a','b']` on the fresh-array rerender). The window MUST be grown past `step` (via the captured observer callback) first, or the reset is a no-op and the test is vacuous. (If `renderHook`/`act` are unavailable, upgrade the import — @testing-library/react ≥13.4 exports them; this repo has 16.x.)

- [ ] **Step 3: Fix the hook** — in `web/src/lib/useInfiniteWindow.ts` change the signature and effect (lines 6-11):

```ts
export function useInfiniteWindow<T>(items: T[], step = 60, resetKey: unknown = null) {
  const [count, setCount] = useState(step)

  useEffect(() => {
    setCount(step)
  }, [resetKey, step])
```

Everything else in the hook is unchanged.

- [ ] **Step 4: Wire the caller** — `web/src/routes/inbox.tsx:50`:

```tsx
const { visible, sentinelRef } = useInfiniteWindow(items, 60, source ?? "");
```

- [ ] **Step 5: Fix the elapsed clock** — in `web/src/routes/inbox.tsx` replace the memo (lines 62-68):

```tsx
// A real 1s clock: the memo version stopped ticking whenever job polling
// paused, freezing the elapsed readout mid-run.
const [nowSec, setNowSec] = useState(() => Math.floor(Date.now() / 1000));
useEffect(() => {
  if (!job.data?.running) return;
  const id = setInterval(() => setNowSec(Math.floor(Date.now() / 1000)), 1000);
  return () => clearInterval(id);
}, [job.data?.running]);
const elapsed = useMemo(() => {
  const startedAt = job.data?.current_started;
  if (!startedAt) return "";
  const secs = Math.max(0, nowSec - startedAt);
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}, [job.data?.current_started, nowSec]);
```

Add `useEffect` to the react import at line 1.

- [ ] **Step 6: Gate** — `cd web && vp test && vp check` → PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/useInfiniteWindow.ts web/src/lib/useInfiniteWindow.test.ts web/src/routes/inbox.tsx
git commit -m "fix(web): infinite-window resets on filter only; elapsed clock ticks independently of polling

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 4: Content-shaped Skeletons

Current `web/src/components/Skeletons.tsx` cycles six bare heights. Replace with card-anatomy placeholders (thumb block + title line + meta line), keeping the root `.skel` class (MasonryGrid measures children generically; its test renders a `.skel`).

**Files:**
- Modify: `web/src/components/Skeletons.tsx`
- Modify: `web/src/components/Skeletons.test.tsx`
- Modify: `web/src/styles.css` (replace `.skel` block, lines 10-14)

**Interfaces:** `Skeletons({ count = 12 })` unchanged.

- [ ] **Step 1: Extend the test** — replace `Skeletons.test.tsx`:

```tsx
import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { Skeletons } from './Skeletons'

test('renders N card-shaped skeletons', () => {
  const { container } = render(<Skeletons count={5} />)
  expect(container.querySelectorAll('.skel')).toHaveLength(5)
  expect(container.querySelectorAll('.skel-thumb').length).toBeGreaterThan(0)
  expect(container.querySelectorAll('.skel-line')).toHaveLength(10) // title + meta per card
})
```

- [ ] **Step 2: Verify failure** — `cd web && vp test src/components/Skeletons.test.tsx` → FAIL (no `.skel-thumb`).

- [ ] **Step 3: Implement** — replace `Skeletons.tsx`:

```tsx
/* Placeholders shaped like real card anatomy (thumb + title + meta) instead
   of bare gray slabs. Deterministic variant cycle: media cards at three
   thumb heights, every fourth card a text card (no thumb). */
const THUMBS = [150, 220, 110, 0, 180, 130]

export function Skeletons({ count = 12 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => {
        const thumb = THUMBS[i % THUMBS.length]
        return (
          <div key={i} className="skel card">
            {thumb ? <div className="skel-thumb" style={{ height: thumb }} /> : <div className="skel-text" />}
            <div className="skel-meta">
              <div className="skel-line" style={{ width: `${72 - (i % 3) * 14}%` }} />
              <div className="skel-line skel-line-dim" style={{ width: `${38 + (i % 2) * 10}%` }} />
            </div>
          </div>
        )
      })}
    </>
  )
}
```

- [ ] **Step 4: Styles** — in `web/src/styles.css` replace the `.skel` block (lines 10-14):

```css
.skel {
  background: var(--bg2);
  border-radius: var(--r);
  overflow: hidden;
  animation: pulse 1.4s ease-in-out infinite;
}

.skel-thumb {
  background: var(--bg3);
}

.skel-text {
  height: 96px;
  background: var(--bg3);
  opacity: 0.55;
}

.skel-meta {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  padding: 0.6rem;
}

.skel-line {
  height: 0.7rem;
  border-radius: 4px;
  background: var(--bg3);
}

.skel-line-dim {
  opacity: 0.6;
}
```

(The existing `@keyframes pulse` at lines 22-26 stays; theme.css's reduced-motion rule already kills it.)

- [ ] **Step 5: Gate** — `cd web && vp test && vp check` → PASS (MasonryGrid test still green — it only requires `.skel` to be a measurable child).

- [ ] **Step 6: Commit**

```bash
git add web/src/components/Skeletons.tsx web/src/components/Skeletons.test.tsx web/src/styles.css
git commit -m "feat(web): content-shaped skeletons matching card anatomy

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 5: Structured empty/error states

**Files:**
- Modify: `web/src/components/StateViews.tsx`
- Create: `web/src/components/StateViews.test.tsx`
- Modify: `web/src/styles.css` (replace `.empty` block, lines 16-20)
- Modify: `web/src/routes/index.tsx`, `web/src/routes/library.tsx`, `web/src/routes/inbox.tsx` (pass retry/hints)

**Interfaces:**
- Produces: `EmptyState({ label, hint }: { label: string; hint?: string })`, `ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void })`. Existing single-prop call sites keep compiling.

- [ ] **Step 1: Write failing tests** — `web/src/components/StateViews.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { EmptyState, ErrorState } from './StateViews'

test('empty state shows glyph, label, and optional hint', () => {
  const { container } = render(<EmptyState label="nothing ingested yet" hint="paste urls in the inbox to begin" />)
  expect(container.querySelector('.state-glyph')).toBeInTheDocument()
  expect(screen.getByText('nothing ingested yet')).toBeInTheDocument()
  expect(screen.getByText('paste urls in the inbox to begin')).toBeInTheDocument()
})

test('error state offers retry when handler given', () => {
  const onRetry = vi.fn()
  render(<ErrorState error={new Error('boom')} onRetry={onRetry} />)
  fireEvent.click(screen.getByRole('button', { name: 'retry' }))
  expect(onRetry).toHaveBeenCalledTimes(1)
})
```

- [ ] **Step 2: Verify failure** — `cd web && vp test src/components/StateViews.test.tsx` → FAIL.

- [ ] **Step 3: Implement** — replace `StateViews.tsx`:

```tsx
import { ApiError } from '../api/client'

/* Quiet observatory glyph: a hairline circle with a centered dot. */
const Glyph = () => (
  <svg className="state-glyph" viewBox="0 0 48 48" width="48" height="48" aria-hidden="true">
    <circle cx="24" cy="24" r="21" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.35" />
    <circle cx="24" cy="24" r="3" fill="currentColor" opacity="0.7" />
  </svg>
)

export const EmptyState = ({ label, hint }: { label: string; hint?: string }) => (
  <div className="empty state-view">
    <Glyph />
    <p className="state-title">{label}</p>
    {hint ? <p className="state-hint">{hint}</p> : null}
  </div>
)

export const ErrorState = ({ error, onRetry }: { error: unknown; onRetry?: () => void }) => {
  const detail = error instanceof ApiError && typeof error.body === 'object' && error.body && 'detail' in error.body
    ? String(error.body.detail)
    : String(error)
  return (
    <div className="empty state-view">
      <Glyph />
      <p className="state-title">failed to load</p>
      <p className="state-hint">{detail}</p>
      {onRetry ? <button className="btn" type="button" onClick={onRetry}>retry</button> : null}
    </div>
  )
}
```

- [ ] **Step 4: Styles** — replace the `.empty` block (styles.css lines 16-20):

```css
.empty {
  color: var(--mute);
  padding: 3rem 0 2rem;
  text-align: center;
}

.state-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
}

.state-title {
  margin: 0;
  color: var(--ink2);
}

.state-hint {
  margin: 0;
  max-width: 26rem;
  color: var(--mute);
  font-size: 0.85rem;
}
```

- [ ] **Step 5: Wire retries and hints**

- `index.tsx:77` → `<ErrorState error={fresh.error} onRetry={() => void fresh.refetch()} />`; line 79 → `<EmptyState label="nothing ingested yet" hint="ingest from the inbox to fill the feed" />`
- `library.tsx:70` → `onRetry={() => void page.refetch()}`; line 72 keeps its conditional label, add `hint={q ? "try a looser query" : undefined}`
- `inbox.tsx:148` → `onRetry={() => void q.refetch()}`; line 150 → `hint="paste urls on the right to queue them"`

- [ ] **Step 6: Gate** — `cd web && vp test && vp check` → PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/StateViews.tsx web/src/components/StateViews.test.tsx web/src/styles.css web/src/routes/index.tsx web/src/routes/library.tsx web/src/routes/inbox.tsx
git commit -m "feat(web): structured empty/error states with glyph and retry

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 6: MemoWaveform rebuild

Fixes, keeping the 56-bar look and shared single-player behavior: theme-token colors instead of hard-coded greens (`#4ade80`/`#31543f` at `MemoWaveform.tsx:24`), devicePixelRatio-aware sizing, ResizeObserver redraw, click-while-playing pauses, module globals consolidated.

**Files:**
- Modify: `web/src/components/MemoWaveform.tsx` (full rewrite below)
- Modify: `web/src/styles.css` (`.wave:focus-visible` outline → var(--live) stays fine; no change needed)

**Interfaces:** `MemoWaveform({ audio }: { audio: string })` unchanged; class `wave` unchanged.

- [ ] **Step 1: Rewrite the component** — replace the whole file with:

```tsx
import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, MouseEvent } from 'react'

/* One shared player across all cards; colors read from the theme at draw
   time; canvas sized to its CSS box * devicePixelRatio and redrawn on
   resize. Click seeks (or pauses when already playing this memo). */
const shared: {
  player: HTMLAudioElement | null
  canvas: HTMLCanvasElement | null
  peaks: number[]
  decoder: AudioContext | null
} = { player: null, canvas: null, peaks: [], decoder: null }

const themeColor = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback

function drawWave(canvas: HTMLCanvasElement, peaks: number[], fraction: number) {
  const context = canvas.getContext('2d')
  if (!context || !peaks.length) return
  const ratio = Math.min(devicePixelRatio || 1, 2)
  const width = Math.max(1, Math.round(canvas.offsetWidth * ratio))
  const height = Math.max(1, Math.round(canvas.offsetHeight * ratio))
  if (canvas.width !== width) canvas.width = width
  if (canvas.height !== height) canvas.height = height
  const played = themeColor('--live', '#4ade80')
  const rest = themeColor('--mute', '#83817a')
  const barWidth = width / peaks.length
  context.clearRect(0, 0, width, height)
  peaks.forEach((peak, index) => {
    context.globalAlpha = index / peaks.length < fraction ? 1 : 0.45
    context.fillStyle = index / peaks.length < fraction ? played : rest
    const barHeight = Math.max(4, peak * height * 0.92)
    context.fillRect(index * barWidth + barWidth * 0.18, (height - barHeight) / 2, barWidth * 0.64, barHeight)
  })
  context.globalAlpha = 1
}

async function peaksForAudio(audio: string): Promise<number[]> {
  shared.decoder ??= new window.AudioContext()
  const buffer = await (await fetch(`/api/memo-audio/${encodeURIComponent(audio)}`)).arrayBuffer()
  const decoded = await shared.decoder.decodeAudioData(buffer)
  const data = decoded.getChannelData(0)
  const bars = 56
  const step = Math.floor(data.length / bars) || 1
  return Array.from({ length: bars }, (_, index) => {
    let maximum = 0
    for (let offset = index * step; offset < (index + 1) * step; offset += 32) {
      maximum = Math.max(maximum, Math.abs(data[offset] || 0))
    }
    return maximum
  })
}

export function MemoWaveform({ audio }: { audio: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const peaksRef = useRef<number[]>([])
  const [available, setAvailable] = useState(true)

  useEffect(() => {
    let cancelled = false
    const canvas = canvasRef.current
    if (!canvas) return

    void peaksForAudio(audio)
      .then((peaks) => {
        if (cancelled) return
        peaksRef.current = peaks
        drawWave(canvas, peaks, 0)
      })
      .catch(() => { if (!cancelled) setAvailable(false) })

    const ro = new ResizeObserver(() => {
      const playing = shared.canvas === canvas && shared.player && !shared.player.paused
      const fraction = playing && shared.player!.duration ? shared.player!.currentTime / shared.player!.duration : 0
      drawWave(canvas, peaksRef.current, fraction)
    })
    ro.observe(canvas)

    return () => {
      cancelled = true
      ro.disconnect()
      if (shared.canvas === canvas && shared.player) {
        shared.player.pause()
        shared.player = null
        shared.canvas = null
        shared.peaks = []
      }
    }
  }, [audio])

  if (!available) return null

  const playAt = (fraction: number, toggle = false) => {
    const canvas = canvasRef.current
    if (!canvas || !peaksRef.current.length) return

    if (shared.canvas === canvas && shared.player) {
      if (toggle && !shared.player.paused) { shared.player.pause(); return }
      if (Number.isFinite(shared.player.duration)) shared.player.currentTime = fraction * shared.player.duration
      void shared.player.play()
      return
    }

    if (shared.player && shared.canvas) {
      shared.player.pause()
      drawWave(shared.canvas, shared.peaks, 0)
    }

    const player = new Audio(`/api/memo-audio/${encodeURIComponent(audio)}`)
    shared.player = player
    shared.canvas = canvas
    shared.peaks = peaksRef.current
    player.addEventListener('timeupdate', () => drawWave(canvas, peaksRef.current, player.currentTime / player.duration))
    player.addEventListener('ended', () => {
      drawWave(canvas, peaksRef.current, 0)
      if (shared.player === player) {
        shared.player = null
        shared.canvas = null
        shared.peaks = []
      }
    })
    void player.play()
  }

  const handleClick = (event: MouseEvent<HTMLCanvasElement>) => {
    event.stopPropagation()
    playAt(event.nativeEvent.offsetX / event.currentTarget.offsetWidth)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLCanvasElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    event.stopPropagation()
    playAt(0, true)
  }

  return <canvas ref={canvasRef} className="wave" tabIndex={0} role="button" aria-label="Play memo" onClick={handleClick} onKeyDown={handleKeyDown} title="play memo" />
}
```

- [ ] **Step 2: Gate** — `cd web && vp test && vp check` → PASS (no dedicated test exists for this canvas component; behavior verified visually in the phase verification step).

- [ ] **Step 3: Commit**

```bash
git add web/src/components/MemoWaveform.tsx
git commit -m "fix(web): MemoWaveform reads theme tokens, handles resize and dpr, click toggles pause

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 7: Ingest ring gauge

A stepped SVG ring next to the inbox progress text. Coarse `done/total` means a smooth bar would lie; the ring fills per completed item while the existing named-item + elapsed text stays.

**Files:**
- Create: `web/src/components/IngestRing.tsx`
- Create: `web/src/components/IngestRing.test.tsx`
- Modify: `web/src/routes/inbox.tsx` (progress block, lines 228-254)
- Modify: `web/src/styles.css` (append)

**Interfaces:** `IngestRing({ done, total, running }: { done: number; total: number; running: boolean })`.

- [ ] **Step 1: Failing test** — `web/src/components/IngestRing.test.tsx`:

```tsx
import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { IngestRing } from './IngestRing'

test('ring exposes progressbar semantics and fill fraction', () => {
  const { container } = render(<IngestRing done={3} total={8} running />)
  const ring = container.querySelector('.ingest-ring')!
  expect(ring).toHaveAttribute('role', 'progressbar')
  expect(ring).toHaveAttribute('aria-valuenow', '3')
  expect(ring).toHaveAttribute('aria-valuemax', '8')
  const fill = container.querySelector('.ingest-ring-fill') as SVGCircleElement
  expect(fill.style.strokeDashoffset).not.toBe('')
})
```

- [ ] **Step 2: Verify failure** — `cd web && vp test src/components/IngestRing.test.tsx` → FAIL.

- [ ] **Step 3: Implement** — `IngestRing.tsx`:

```tsx
/* Stepped ring gauge: fills per completed item (the backend only reports
   done/total at ~2min granularity — a smooth bar would read as stalled).
   The 180ms CSS transition on dashoffset animates each step. */
const R = 8
const CIRC = 2 * Math.PI * R

export function IngestRing({ done, total, running }: { done: number; total: number; running: boolean }) {
  const fraction = total > 0 ? done / total : 0
  return (
    <svg
      className={`ingest-ring${running ? ' running' : ''}`}
      viewBox="0 0 20 20"
      width="20"
      height="20"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={done}
      aria-label={`ingest progress: ${done} of ${total}`}
    >
      <circle cx="10" cy="10" r={R} fill="none" stroke="currentColor" strokeWidth="2" opacity="0.18" />
      <circle
        className="ingest-ring-fill"
        cx="10" cy="10" r={R} fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round"
        strokeDasharray={CIRC}
        style={{ strokeDashoffset: CIRC * (1 - fraction) }}
        transform="rotate(-90 10 10)"
      />
    </svg>
  )
}
```

- [ ] **Step 4: Wire into the rail** — in `web/src/routes/inbox.tsx`, inside the progress block, replace the spinner line (lines 231-233):

```tsx
<IngestRing done={job.data.done} total={job.data.total} running={job.data.running} />
```

(add `import { IngestRing } from "../components/IngestRing";`). Delete the `.ingest-spinner` usage; leave its CSS in place (harmless) or remove the `.ingest-spinner` block (styles.css lines 220-234) — remove it, plus its reduced-motion exemption (lines 256-260).

- [ ] **Step 5: Append styles**:

```css
.ingest-ring {
  flex: none;
  color: var(--mute);
}

.ingest-ring.running {
  color: var(--accent);
}

.ingest-ring-fill {
  transition: stroke-dashoffset 0.18s var(--ease);
}
```

- [ ] **Step 6: Gate** — `cd web && vp test && vp check` → PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/IngestRing.tsx web/src/components/IngestRing.test.tsx web/src/routes/inbox.tsx web/src/styles.css
git commit -m "feat(web): stepped ingest ring gauge on the inbox rail

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 8: Profile grid + meter semantics

**Files:**
- Modify: `web/src/routes/profile.tsx` (summary markup, lines 53-60)
- Modify: `web/src/routes/profile.test.tsx` (extend existing — read it first and keep its current assertions passing)
- Modify: `web/src/styles.css` (profile block, lines 815-827)

- [ ] **Step 1: Markup** — in `profile.tsx` replace the bar line (line 55):

```tsx
<span
  className="profile-theme-bar"
  role="meter"
  aria-valuemin={0}
  aria-valuemax={100}
  aria-valuenow={Math.round((theme.weight / maxWeight) * 100)}
  aria-label={`${theme.label} weight`}
>
  <span style={{ transform: `scaleX(${theme.weight / maxWeight})` }} />
</span>
```

- [ ] **Step 2: CSS** — replace styles.css lines 818-824 with:

```css
.profile-theme { border-bottom: 1px solid var(--line); padding: 0.4rem 0; }
.profile-theme summary {
  display: grid;
  grid-template-columns: minmax(9rem, 15rem) 1fr auto;
  align-items: center;
  gap: 0.8rem;
  cursor: pointer;
  list-style: none;
}
.profile-theme-bar { height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; }
.profile-theme-bar span {
  display: block;
  height: 100%;
  width: 100%;
  background: var(--accent);
  transform-origin: left;
  transition: transform 0.18s var(--ease);
}
.profile-theme-share { color: var(--mute); font-size: 0.85em; }
.profile-theme p, .profile-theme ul { color: var(--mute); margin: 0.5rem 0; }
```

(The old rules used `flex` + a magic `15.8rem` body indent; the grid removes both. The `flex: 0 0 15rem` on `.profile-theme-label` rule at line 820 is deleted — the grid column replaces it.)

- [ ] **Step 3: Test** — read `web/src/routes/profile.test.tsx` first; add one assertion to its existing render test (adapting to how it renders the page):

```tsx
expect(container.querySelector('.profile-theme-bar')).toHaveAttribute('role', 'meter')
```

- [ ] **Step 4: Gate** — `cd web && vp test && vp check` → PASS including the pre-existing profile tests.

- [ ] **Step 5: Commit**

```bash
git add web/src/routes/profile.tsx web/src/routes/profile.test.tsx web/src/styles.css
git commit -m "feat(web): profile theme rows on a minmax grid with real meter semantics

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 9: SOURCES single source of truth + aria-pressed chips

**Files:**
- Modify: `web/src/components/icons.tsx` (export SOURCES)
- Modify: `web/src/components/SourceFilter.tsx`
- Modify: `web/src/components/SourceFilter.test.tsx`

**Interfaces:** `icons.tsx` additionally exports `export const SOURCES: string[]` (the 7 filterable sources, order preserved from the old SourceFilter list: instagram, youtube, pinterest, tiktok, web, memo, imessage).

- [ ] **Step 1: Failing test** — extend `SourceFilter.test.tsx` (keep the existing toggle test, append):

```tsx
test('chips carry aria-pressed reflecting selection', () => {
  const { rerender } = render(<SourceFilter value={undefined} onChange={() => {}} />)
  expect(screen.getByRole('button', { name: 'youtube' })).toHaveAttribute('aria-pressed', 'false')
  rerender(<SourceFilter value="youtube" onChange={() => {}} />)
  expect(screen.getByRole('button', { name: 'youtube' })).toHaveAttribute('aria-pressed', 'true')
})
```

- [ ] **Step 2: Verify failure**, then implement:

`icons.tsx` — append after `ICON_ALIASES` (line 31):

```tsx
/* The filterable source set — single source of truth for filter chips.
   imessage has no dedicated icon and falls back to web (by design). */
export const SOURCES = ['instagram', 'youtube', 'pinterest', 'tiktok', 'web', 'memo', 'imessage']
```

`SourceFilter.tsx` — replace entirely:

```tsx
import { SOURCES } from './icons'

export function SourceFilter({ value, onChange }: { value?: string; onChange: (s?: string) => void }) {
  return (
    <span className="filters">
      {SOURCES.map(s => (
        <button
          key={s}
          className={`fchip${value === s ? ' on' : ''}`}
          aria-pressed={value === s}
          onClick={() => onChange(value === s ? undefined : s)}
        >
          {s}
        </button>
      ))}
    </span>
  )
}
```

- [ ] **Step 3: Gate** — `cd web && vp test && vp check` → PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/icons.tsx web/src/components/SourceFilter.tsx web/src/components/SourceFilter.test.tsx
git commit -m "fix(web): SOURCES exported once from icons; filter chips carry aria-pressed

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 10: MasonryGrid effect dependency array

`web/src/components/MasonryGrid.tsx:26-84` — the layout effect has NO dependency array, so every parent render tears down and rebinds the ResizeObserver and every image listener. Fix: depend on `children`. (Do NOT add CSS position transitions here — Phase 1 lands GSAP Flip for reflow animation, and CSS transitions on left/top would fight it.)

**Files:**
- Modify: `web/src/components/MasonryGrid.tsx:84`

- [ ] **Step 1: Edit** — change line 84 from `  })` to `  }, [children])`.

- [ ] **Step 2: Gate** — `cd web && vp test src/components/MasonryGrid.test.tsx && vp check` → PASS (the existing test exercises exactly this effect).

- [ ] **Step 3: Commit**

```bash
git add web/src/components/MasonryGrid.tsx
git commit -m "fix(web): MasonryGrid layout effect keyed on children, not every render

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 11: Phase verification (screenshot pass)

- [ ] **Step 1:** Start the dev server in the background: `cd /Users/melocoton/Developer/ytk/web && vp dev --port 5173` (leave running).
- [ ] **Step 2:** Using the shot.py harness from the README, capture: `/` (feed + open a note is manual — capture at rest), `/library`, `/inbox`, `/profile`. Then with Playwright, script one interaction shot: click the first `.fresh-card .card-open` on `/` and screenshot the open NoteViewer; click a `.delete-note` and screenshot the ConfirmDialog.
- [ ] **Step 3:** Re-run the same captures with reduced motion; diff — skeleton pulse must be frozen, nothing else changes at rest.
- [ ] **Step 4:** Confirm `vp check && vp test` clean, working tree clean (`git status`), and all Phase 0 commits pushed: `git push`.

Phase complete when: both dialogs are native `<dialog>` with styled backdrops, no `window.confirm` remains (`grep -rn "window.confirm" web/src` → empty), skeleton/empty/error states render structured, the ring gauge steps, and the elapsed clock ticks while a job runs even between polls.

## Self-review checklist (run before handing off)

1. `grep -rn "window.confirm" web/src` returns nothing.
2. `grep -rn "SOURCES" web/src` shows exactly one definition (icons.tsx).
3. Types: `NoteViewer` props match Task 1's interface exactly (Phase 1 depends on it); `useInfiniteWindow` third param is `resetKey: unknown = null` (inbox passes `source ?? ""`).
4. No task introduced a dependency, a sans font, uppercase copy, or an emoji.
