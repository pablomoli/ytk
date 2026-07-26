# Phase 2 — Typography in Motion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Text-level motion on the Phase 1 foundation: SplitText heading stagger, ScrambleText instrument-readout status on the ingest rail, hover decode on tag chips, gsap count-up on the header counts, and a restrained scroll focus-rack on the profile prose.

**Architecture:** Four small components/hooks, all importing exclusively from `web/src/lib/motion.ts`. GSAP mutates DOM text nodes that React owns — every effect here either (a) targets text that never re-renders mid-animation (headings), (b) re-runs idempotently on re-render (ScrambleStatus keys off text change), or (c) restores original text on completion (hover decode).

**Tech Stack:** gsap SplitText, ScrambleTextPlugin, ScrollTrigger (registered in Phase 1), React 19.

**Prerequisite:** Phase 1 complete (`lib/motion.ts` exports `gsap, SplitText, ScrollTrigger, DUR, HOUSE_EASE, reducedMotion`).

## Global Constraints

See `docs/plans/uiux-polish/README.md`. Phase-specific:
- Scramble charset is dots/colons/lowercase only — `'.: abcdefghijklmnopqrstuvwxyz0123456789'`. Wider glyph sets read as hacker pastiche (off-brand).
- Scramble NEVER runs on per-second counters (elapsed clock, done/total) — discrete state transitions only.
- ScrollReveal applies ONLY to the profile prose (bounded length). It is explicitly NOT applied to note-viewer `<pre>` content: transcripts run to thousands of words and SplitText on them is a real performance hazard. This is a deliberate narrowing of the sprint doc — record it as such in the commit message.

**Scope honesty note (SplitHeading):** the hub has exactly one display `<h1>` today (`web/src/routes/transit.tsx:203` — "connections, not clusters"). `/`, `/library`, `/profile` have no display headings (nav + controls only). SplitHeading therefore lands on transit's h1 now and exists as a ready component for future headings. Do not invent headings for other routes.

---

### Task 1: SplitHeading component

**Files:**
- Create: `web/src/components/SplitHeading.tsx`
- Create: `web/src/components/SplitHeading.test.tsx`
- Modify: `web/src/routes/transit.tsx:203`

**Interfaces (Produces):** `SplitHeading({ as = 'h1', children }: { as?: 'h1' | 'h2' | 'h3'; children: string })` — children must be a plain string.

- [ ] **Step 1: Failing test** — `web/src/components/SplitHeading.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { SplitHeading } from './SplitHeading'

test('renders the heading text intact (animation is progressive enhancement)', () => {
  render(<SplitHeading>connections, not clusters</SplitHeading>)
  expect(screen.getByRole('heading')).toHaveTextContent('connections, not clusters')
})
```

- [ ] **Step 2: Verify failure** — `cd web && vp test src/components/SplitHeading.test.tsx` → FAIL (module not found).

- [ ] **Step 3: Implement**:

```tsx
import { createElement, useEffect, useRef } from 'react'
import { DUR, SplitText, gsap, reducedMotion } from '../lib/motion'

/* Word-level baseline-rise stagger for display headings. Word-level (not
   chars) dodges the italic-Newsreader kerning shift; splitting waits for
   fonts.ready so metrics are final. SplitText reverts on cleanup, so the
   DOM returns to the plain string React owns. */
export function SplitHeading({ as = 'h1', children }: { as?: 'h1' | 'h2' | 'h3'; children: string }) {
  const ref = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el || reducedMotion()) return
    let split: InstanceType<typeof SplitText> | undefined
    let cancelled = false
    void (document.fonts?.ready ?? Promise.resolve()).then(() => {
      if (cancelled || !el.isConnected) return
      try {
        split = SplitText.create(el, { type: 'words', aria: 'auto' })
        gsap.from(split.words, {
          y: '0.55em',
          opacity: 0,
          duration: DUR.morph,
          stagger: DUR.reveal / Math.max(6, split.words.length * 2),
        })
      } catch {
        /* A non-layout environment can refuse the split — the heading
           simply stays static, which is the correct degraded state */
      }
    })
    return () => { cancelled = true; split?.revert() }
  }, [children])

  return createElement(as, { ref }, children)
}
```

(The `document.fonts?.ready ?? Promise.resolve()` guard and the try/catch are load-bearing: a non-layout environment can lack `document.fonts` and refuse SplitText's layout reads — the degraded state is a static heading, never a crash.)

- [ ] **Step 4: Wire transit** — `web/src/routes/transit.tsx:203`: replace `<h1>connections, not clusters</h1>` with `<SplitHeading>connections, not clusters</SplitHeading>` and add the import.

- [ ] **Step 5: Gate + commit**

Run: `cd web && vp test && vp check` → PASS.

```bash
git add web/src/components/SplitHeading.tsx web/src/components/SplitHeading.test.tsx web/src/routes/transit.tsx
git commit -m "feat(web): SplitHeading word-stagger for display headings, wired on transit

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 2: ScrambleStatus for the ingest rail

Scrambles on DISCRETE text changes (phase word, current title). The counters ("3/8", elapsed) stay plain — they change every second.

**Files:**
- Create: `web/src/components/ScrambleStatus.tsx`
- Create: `web/src/components/ScrambleStatus.test.tsx`
- Modify: `web/src/routes/inbox.tsx` (progress block)
- Modify: `web/src/styles.css` (append width-lock rule)

**Interfaces (Produces):** `ScrambleStatus({ text, className }: { text: string; className?: string })` — a `<span>` that decodes to `text` whenever `text` changes.

- [ ] **Step 1: Failing test**:

```tsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { ScrambleStatus } from './ScrambleStatus'

test('renders the target text (scramble is enhancement only)', () => {
  render(<ScrambleStatus text="running" />)
  expect(screen.getByText('running')).toBeInTheDocument()
})

test('updates to new text on prop change', () => {
  const { rerender } = render(<ScrambleStatus text="running" />)
  rerender(<ScrambleStatus text="done" />)
  expect(screen.getByText('done')).toBeInTheDocument()
})
```

(In a non-layout environment the scramble tween is skipped — see implementation — so the text is synchronous.)

- [ ] **Step 2: Verify failure**, then implement:

```tsx
import { useEffect, useRef } from 'react'
import { gsap, reducedMotion } from '../lib/motion'

const CHARSET = '.: abcdefghijklmnopqrstuvwxyz0123456789'

/* Instrument-readout text: on each discrete change the span decodes into
   the new reading. React renders the final text; the tween only perturbs
   the DOM in between, so a mid-tween re-render is self-correcting. The
   min-width lock keeps proportional Newsreader from jittering the rail. */
export function ScrambleStatus({ text, className }: { text: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const prev = useRef<string>()

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const changed = prev.current !== undefined && prev.current !== text
    prev.current = text
    if (!changed || reducedMotion()) return
    const tween = gsap.to(el, {
      duration: 0.5,
      scrambleText: { text, chars: CHARSET, speed: 0.4 },
    })
    return () => { tween.kill(); el.textContent = text }
  }, [text])

  return (
    <span ref={ref} className={`scramble-status${className ? ` ${className}` : ''}`} style={{ minWidth: `${text.length}ch` }}>
      {text}
    </span>
  )
}
```

- [ ] **Step 3: Styles** — append to `styles.css`:

```css
.scramble-status {
  display: inline-block;
}
```

- [ ] **Step 4: Wire the rail** — in `web/src/routes/inbox.tsx` progress block: split the combined string so only discrete parts scramble. Replace the inner `<span>` containing `{job.data.running ? "running · " : "done · "}...` with:

```tsx
<span>
  <ScrambleStatus text={job.data.running ? "running" : "done"} />
  {" · "}{job.data.done}/{job.data.total}
  {job.data.running && elapsed ? ` · ${elapsed}` : ""}
</span>
```

and the current-title line becomes:

```tsx
<ScrambleStatus className="progress-current" text={currentTitle} />
```

(`.progress-current` already ellipsizes; keep `title={currentTitle}` by adding a wrapping span if needed — simplest: `<span className="progress-current" title={currentTitle}><ScrambleStatus text={currentTitle} /></span>` and drop className from ScrambleStatus here.) Add the import.

- [ ] **Step 5: Gate + commit**

```bash
git add web/src/components/ScrambleStatus.tsx web/src/components/ScrambleStatus.test.tsx web/src/routes/inbox.tsx web/src/styles.css
git commit -m "feat(web): ingest rail status decodes through ScrambleStatus on discrete transitions

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 3: Hover decode on tag chips and card titles

**Files:**
- Create: `web/src/lib/useHoverDecode.ts`
- Create: `web/src/lib/useHoverDecode.test.ts`
- Modify: `web/src/routes/tags.tsx` (tag-chip buttons)
- Modify: `web/src/components/FreshCard.tsx` (title div)

**Interfaces (Produces):** `useHoverDecode(): { onMouseEnter: (e: ReactMouseEvent<HTMLElement>) => void }` — spread onto any element whose textContent is a short static string.

- [ ] **Step 1: Failing test** — `web/src/lib/useHoverDecode.test.ts`:

```tsx
import { renderHook } from '@testing-library/react'
import { expect, test } from 'vitest'
import { useHoverDecode } from './useHoverDecode'

test('returns a stable mouseenter handler', () => {
  const { result, rerender } = renderHook(() => useHoverDecode())
  const first = result.current.onMouseEnter
  rerender()
  expect(result.current.onMouseEnter).toBe(first)
  expect(typeof first).toBe('function')
})
```

- [ ] **Step 2: Verify failure**, then implement `useHoverDecode.ts`:

```tsx
import { useCallback } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import { gsap, reducedMotion } from './motion'

const CHARSET = '.: abcdefghijklmnopqrstuvwxyz'

/* Short decode flicker on hover. Width/height are locked for the tween so
   layout never breathes; original text is restored on kill. Only safe on
   elements whose text is static between renders (chips, titles). */
export function useHoverDecode() {
  const onMouseEnter = useCallback((event: ReactMouseEvent<HTMLElement>) => {
    const el = event.currentTarget
    if (reducedMotion()) return
    const original = el.textContent ?? ''
    if (!original || original.length > 80) return
    const rect = el.getBoundingClientRect()
    el.style.width = `${rect.width}px`
    el.style.height = `${rect.height}px`
    gsap.to(el, {
      duration: 0.25,
      scrambleText: { text: original, chars: CHARSET, speed: 0.5 },
      onComplete: () => { el.style.width = ''; el.style.height = ''; el.textContent = original },
      onInterrupt: () => { el.style.width = ''; el.style.height = ''; el.textContent = original },
    })
  }, [])
  return { onMouseEnter }
}
```

- [ ] **Step 3: Wire** —
- `web/src/routes/tags.tsx`: in TagsPage add `const decode = useHoverDecode()`; on the `.tag-chip` button add `onMouseEnter={decode.onMouseEnter}`. CAUTION: the chip contains a nested `<span>{count}</span>` — scrambling `textContent` would flatten it. So wrap the tag name in its own span first: `{tag} <span>{...}</span>` becomes `<span className="tag-name" onMouseEnter={decode.onMouseEnter}>{tag}</span> <span>{group.counts[tag] ?? ''}</span>` and put the handler on the inner `.tag-name` span, NOT the button.
- `web/src/components/FreshCard.tsx`: add `const decode = useHoverDecode()` and `onMouseEnter={decode.onMouseEnter}` on the `.title` div (its content is a plain string).

- [ ] **Step 4: Gate + commit**

```bash
git add web/src/lib/useHoverDecode.ts web/src/lib/useHoverDecode.test.ts web/src/routes/tags.tsx web/src/components/FreshCard.tsx
git commit -m "feat(web): hover decode flicker on tag names and card titles

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 4: CountUp on the header counts

**Files:**
- Create: `web/src/components/CountUp.tsx`
- Create: `web/src/components/CountUp.test.tsx`
- Modify: `web/src/routes/index.tsx:88`, `web/src/routes/library.tsx:97`, `web/src/routes/inbox.tsx:174-177`

**Interfaces (Produces):** `CountUp({ value }: { value: number })` — a `<span>` whose number tweens to `value` on change (tabular numerals come from the `.count` parent's theme rule).

- [ ] **Step 1: Failing test**:

```tsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { CountUp } from './CountUp'

test('renders the value', () => {
  render(<CountUp value={128} />)
  expect(screen.getByText('128')).toBeInTheDocument()
})
```

- [ ] **Step 2: Verify failure**, then implement:

```tsx
import { useEffect, useRef } from 'react'
import { DUR, gsap, reducedMotion } from '../lib/motion'

const fmt = new Intl.NumberFormat('en-US')

/* Number settles onto its new reading instead of flipping. First render is
   instant; only CHANGES tween. React renders the final value, the tween
   perturbs textContent in between (self-correcting on re-render). */
export function CountUp({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const shown = useRef<number>()

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const from = shown.current
    shown.current = value
    if (from === undefined || from === value || reducedMotion()) { el.textContent = fmt.format(value); return }
    const counter = { n: from }
    const tween = gsap.to(counter, {
      n: value,
      duration: DUR.wipe,
      onUpdate: () => { el.textContent = fmt.format(Math.round(counter.n)) },
    })
    return () => { tween.kill(); el.textContent = fmt.format(value) }
  }, [value])

  return <span ref={ref}>{fmt.format(value)}</span>
}
```

- [ ] **Step 3: Wire the three counts**:
- `index.tsx:88` → `<span className="count"><CountUp value={notes.length} /> recently ingested</span>`
- `library.tsx:97` → `<span className="count"><CountUp value={total} /> in the store</span>`
- `inbox.tsx:174-177` → `<span className="count"><CountUp value={items.length} />{q.data && q.data.length !== items.length ? <> of <CountUp value={q.data.length} /></> : ""} pending</span>`

- [ ] **Step 4: Gate + commit**

```bash
git add web/src/components/CountUp.tsx web/src/components/CountUp.test.tsx web/src/routes/index.tsx web/src/routes/library.tsx web/src/routes/inbox.tsx
git commit -m "feat(web): header counts settle via gsap count-up

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 5: ScrollReveal on profile prose

**Files:**
- Create: `web/src/components/ScrollReveal.tsx`
- Create: `web/src/components/ScrollReveal.test.tsx`
- Modify: `web/src/routes/profile.tsx` (prose section, lines 75-77)

**Interfaces (Produces):** `ScrollReveal({ children }: { children: string })` — one paragraph; words rack from soft (opacity .25, blur 4px, rotate 1deg) to sharp as the paragraph scrolls through the viewport, scrubbed by ScrollTrigger.

- [ ] **Step 1: Failing test**:

```tsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { ScrollReveal } from './ScrollReveal'

test('renders paragraph text intact', () => {
  render(<ScrollReveal>the observatory is a private instrument</ScrollReveal>)
  expect(screen.getByText('the observatory is a private instrument')).toBeInTheDocument()
})
```

- [ ] **Step 2: Verify failure**, then implement:

```tsx
import { useEffect, useRef } from 'react'
import { ScrollTrigger, SplitText, gsap, reducedMotion } from '../lib/motion'

/* Restrained focus-rack for bounded prose: profile portrait only. Not for
   note transcripts — SplitText on thousand-word content is a perf hazard,
   which is why this takes a single paragraph string. */
export function ScrollReveal({ children }: { children: string }) {
  const ref = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el || reducedMotion()) return
    let split: InstanceType<typeof SplitText> | undefined
    let trigger: ScrollTrigger | undefined
    let cancelled = false
    void (document.fonts?.ready ?? Promise.resolve()).then(() => {
      if (cancelled || !el.isConnected) return
      try {
        split = SplitText.create(el, { type: 'words', aria: 'auto' })
        const tween = gsap.fromTo(split.words,
          { opacity: 0.25, filter: 'blur(4px)', rotate: 1 },
          { opacity: 1, filter: 'blur(0px)', rotate: 0, stagger: 0.02, ease: 'none' })
        trigger = ScrollTrigger.create({ trigger: el, start: 'top 85%', end: 'top 40%', scrub: true, animation: tween })
      } catch {
        /* degraded state: static prose */
      }
    })
    return () => { cancelled = true; trigger?.kill(); split?.revert() }
  }, [children])

  return <p ref={ref}>{children}</p>
}
```

- [ ] **Step 3: Wire profile** — `profile.tsx:75-77`:

```tsx
<section className="profile-prose">
  {portrait.map((paragraph, i) => <ScrollReveal key={i}>{paragraph}</ScrollReveal>)}
</section>
```

- [ ] **Step 4: Gate + commit**

```bash
git add web/src/components/ScrollReveal.tsx web/src/components/ScrollReveal.test.tsx web/src/routes/profile.tsx
git commit -m "feat(web): profile portrait racks into focus on scroll (bounded prose only)

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 6: Phase verification

- [ ] Dev server screenshots (normal + reduced): `/transit` right after load (heading mid-stagger at +150ms vs settled at +1200ms); `/profile` scrolled halfway (words mid-rack); `/inbox` during a real or simulated job (ScrambleStatus needs a running job — if none is available, verify by temporarily driving state in the browser via Playwright evaluate; do NOT commit any test scaffolding).
- [ ] Reduced-motion runs: all mids equal settleds; scramble/count-up/hover effects absent.
- [ ] `grep -rn "from 'gsap'" web/src --include='*.ts*' | grep -v lib/motion.ts` → still empty.
- [ ] `vp test && vp check && vp build` clean; tree clean; push.

## Self-review checklist

1. No scramble on per-second values (elapsed, done/total stay plain text).
2. Charsets are the restrained sets defined above — no symbols beyond `.:`.
3. Every component tolerates missing browser APIs (fonts.ready guarded, matchMedia stubbed in test-setup from Phase 1).
4. React-vs-GSAP text ownership: each effect restores or re-renders the final text (see per-component comments).
