# UI/UX Polish Sprint — the superlist

One unified sprint merging the component-scout run (verified punch-list + visual shortlist)
and the GSAP/viz scout run (phased scope). Six phases, each independently shippable and
screenshot-verifiable. Full rationale lives in the two scout reports; this is the working list.

Identity contract (binding for every item): observatory — dark warm neutrals, Newsreader
serif only, brass `#e2b04a` accent, 180ms `cubic-bezier(.25,.1,.25,1)` house ease
(sanctioned longer registers: 250-350ms morphs, 350-450ms wipes, 500-700ms staggered
reveals), Bayer-dither texture language, `prefers-reduced-motion` honored at the JS level
on every effect. Identity surfaces (/growth, /grove, /map) are augmented, never replaced.

Dependency bill for the whole sprint: `gsap` (core + CustomEase, Flip, SplitText,
ScrambleTextPlugin, ScrollTrigger; ~58KB gz, free license) and `postprocessing`
(pmndrs, ~45KB gz, Zlib). Nothing else. All gallery components are rewritten as owned
code against `theme.css`; shaders are vendored `.glsl` files.

---

## Phase 0 — Statics and fixes (no dependencies, ~8h)

Confirmed bugs, a11y defects, and perceived-quality statics. Ships first; item 1 is the
foundation the Phase 1 morph animates into.

- [ ] **Shared `NoteViewer` on native `<dialog>`/`showModal()`** — dedupe the copy-pasted
  viewer in `web/src/routes/library.tsx` (62-64, 103-122) and `web/src/routes/index.tsx`
  (43-71); delete the querySelector focus trap; fixes the confirmed a11y defect
  (`aria-modal` with no trap/restore in library). Top-layer, Escape, focus restore,
  `::backdrop` come free. ~40-60 lines.
- [ ] **`ConfirmDialog`** replacing `window.confirm` at `routes/index.tsx:38`,
  `library.tsx:52`, `profile.tsx:17` — same native-dialog foundation; hairline border,
  brass action. The OS popup is the most off-brand pixel in the app.
- [ ] **Bug: inbox elapsed-time memo** (`routes/inbox.tsx:63-68`) — keyed on
  `job.dataUpdatedAt`, stops ticking when polling stops; use a real `setInterval`.
- [ ] **Bug: `useInfiniteWindow.ts:9-11`** — resets window count on items array identity
  instead of content.
- [ ] **Content-shaped skeletons** (pattern: animata Wide Card / List,
  animata.design/docs/skeleton/wide-card) — replace the six modulo-cycled gray bars in
  `Skeletons` with thumbnail + title + meta-line anatomy matching real card shapes.
- [ ] **Structured empty/error states** (pattern: coss ui Empty,
  coss.com/ui/docs/components/empty) — glyph + title + description + retry action in
  `StateViews`, using the existing hand-rolled source icons.
- [ ] **`MemoWaveform` rebuild on the ElevenLabs Waveform pattern**
  (ui.elevenlabs.io/docs/components/waveform, MIT) — theme-token colors instead of
  hard-coded greens, ResizeObserver redraw, single decode with precomputed peaks,
  kills the four module-level globals.
- [ ] **Ingest gauge** (pattern: magicui animated-circular-progress-bar) — SVG ring
  stepped per completed item on the inbox ingest rail, elapsed-time text kept alongside
  (coarse done/total makes a smooth bar lie; a stepped ring does not).
- [ ] **Profile CSS surgery** (`routes/profile.tsx`, `styles.css:820,824`) — `minmax`
  grid instead of 15rem magic columns; `role="meter"` + aria values on weight bars;
  180ms `scaleX` fill transition.
- [ ] **`aria-pressed` on SourceFilter chips** + export a single `SOURCES` module to
  kill duplication with `icons.tsx` `ICON_PATHS`.
- [ ] **MasonryGrid hygiene** — add the missing effect dependency array
  (`components/MasonryGrid.tsx`); prerequisite for clean Flip integration in Phase 1.

## Phase 1 — Motion foundation and the grid-to-detail morph (~12h)

- [ ] Install `gsap`; create **`web/src/lib/motion.ts`** — registers CustomEase/Flip/
  SplitText/ScrambleText/ScrollTrigger, builds the house ease, sets
  `gsap.defaults({ duration: 0.18 })`, exports the `gsap.matchMedia` reduced-motion
  wrapper. Rule: no file imports `gsap` directly, ever — only `lib/motion.ts`.
- [ ] **Flip masonry reflow** (`components/MasonryGrid.tsx`) — `Flip.getState` before the
  width-assignment pass, `Flip.from` after; gated to intentional reflows only
  (filter/density/expand), never ResizeObserver or image-onload; `overwrite: true`.
- [ ] **Card-to-detail Flip morph** (`FreshCard.tsx`, `routes/index.tsx`,
  `routes/library.tsx`; pattern: Codrops Palmer's-grid) — clone-overlay morph of the
  clicked thumbnail into the NoteViewer media slot (250-350ms), reverse on close.
  Clone overlay, never reparenting — React 19 owns the img node.
- [ ] **PixelTransition dither reveal** on NoteViewer body content
  (reactbits.dev/animations/pixel-transition, rewritten) — reveal order driven by the
  house Bayer matrix, seeded from the note path, keyed to the morph timeline.

## Phase 2 — Typography in motion (~10h)

- [ ] **`SplitHeading` component** (GSAP SplitText) — word-level split, awaits
  `document.fonts.ready`, baseline-rise stagger; wired into `/` , `/library`,
  `/profile` hero, `/transit` h1.
- [ ] **`ScrambleStatus` component** (ScrambleTextPlugin) — discrete state transitions
  only, lowercase + digits charset, `min-width` in `ch`; ingest rail status line and
  queued/ingesting badges in `routes/inbox.tsx` (~228-254). Supersedes round-one
  ShinyText pick.
- [ ] **Hover decode hook** (~30-40 lines, `.:` glyph set, width-locked) on `.tag-chip`
  in `routes/tags.tsx` and card titles in `FreshCard.tsx`.
- [ ] **Count-up on stats** — gsap tween + `Intl.NumberFormat`, tabular numerals.
  Supersedes round-one CountUp pick (no `motion` package; gsap already in).
- [ ] **Scroll Reveal focus-rack** (ScrollTrigger scrub, restrained: ~1deg rotation,
  0.25 base opacity) on note-detail prose and `/profile` portrait — plain-prose
  paragraphs only; `ScrollTrigger.refresh()` after query payload resolves.

## Phase 3 — Surface reveals and the reticle cursor (~9h)

- [ ] **`useMaskReveal` hook** (pattern: Codrops SVG-mask transitions) — play-once-on-load
  staggered slat/grid mask on card thumbnails, seeded shuffle for determinism, applied
  on `/` and `/library`; must coordinate with lazy-load `onload` and keep
  `naturalWidth` wide-card measurement working. Covers round-one Pixel Image /
  Vertical Tiles territory in one treatment.
- [ ] **`PixelCard` hover bloom** (reactbits.dev/components/pixel-card, rewritten) —
  canvas center-out pixel bloom on card hover, palette from theme tokens, rAF-driven,
  zero deps.
- [ ] **`TargetCursor`** (reactbits.dev/animations/target-cursor, reskinned) — brass
  1.5px corner brackets, no blend-mode, no idle spin; per-route mount, I-beam preserved
  over text; ships behind a settings toggle in `routes/settings.tsx` (the sprint's one
  UX gamble — killable without touching anything else).

## Phase 4 — Viz track A: map feel + grove compositor (~10h)

- [ ] **Inertial pan + eased zoom** (`lib/mapRenderer.ts`, MapLibre technique port,
  ~40-60 lines, zero deps) — velocity buffer on `up` (line ~345), integrate with the
  file's own `1 - Math.exp(-k*dt)` idiom; `wheel` (line ~348) routed through an eased
  `scaleTarget`, cursor-anchored via per-frame anchor correction; momentum canceled on
  `down`/`wheel`/`flyTo`/`setView`. Orbit drags stay momentum-free.
- [ ] **Grove postprocessing** (`lib/grove/scene.ts:~213`) — install `postprocessing`;
  EffectComposer with Vignette + ToneMapping + SMAA + custom seeded-grain effect
  (hash-based GLSL, never the stock unseeded noise — replays must reproduce);
  `composer.setSize` wired into resize.

## Phase 5 — Viz track B: growth compositor + shader wipes (~14h)

- [ ] **Growth render-target refactor** (`lib/growth/scene.ts:371-383`, own commit) —
  redirect the scissored tile loop to an offscreen `WebGLRenderTarget`; acceptance
  gate: pixel-identical screenshot before/after.
- [ ] **Growth effect pass** — vignette + seeded grain + SMAA only. The one-dither rule
  stands: no second dither layer, ever.
- [ ] **`lib/transitionPass.ts` + vendored gl-transitions** (2-3 MIT `.glsl` files:
  pixelize, crosshatch) — state/gallery swaps on `/growth`, node focus on `/grove`,
  detail zoom on `/map`; bare rAF tween on the house ease, 350-450ms; reduced motion =
  hard cut. Out of scope: DOM route transitions, masonry re-sorts (Flip's job).

---

## Superseded / declined (from the two runs, for the record)

- ShinyText -> ScrambleStatus; CountUp (motion pkg) -> gsap tween; magicui Pixel Image +
  animata Vertical Tiles -> `useMaskReveal`.
- Declined: component-library dialogs (native `<dialog>` wins), reactbits Masonry
  component (Flip on the existing grid wins), Lenis/ScrollSmoother, Draggable/Inertia
  feed physics, staggered menu, ordered-dither post pass on /growth, animated Bayer
  background on /growth, bloom/glitch/chromatic-aberration catalog.
- Deferred with re-entry conditions: curtains.js (if clone-overlay morph proves
  insufficient), d3-quadtree (when point counts 10x and `pick()` is the measured
  hotspot), Shuffle headers (needs display headers to exist first), interactive Bayer
  idle pass on /map (taste call, parked).

## Verification (every phase, before merge)

1. `vp check` and `vp test` green from `web/`; bundle-size delta reported (only gsap
   and postprocessing may grow it).
2. Determinism tests untouched and green — Flip animates layout, it must not change
   `masonry.ts` outputs.
3. Headless screenshot pass (headless from first navigate): affected routes at rest and
   mid-transition, fixed seed and viewport. Phase 5 refactor commit: zero pixel diff.
4. Reduced-motion pass: re-run screenshots with `prefers-reduced-motion: reduce`
   emulated; mid-transition capture must equal settled state.
5. Live smoke on the hub (:6969): morph open/close, map coast/zoom, scramble on a real
   ingest, cursor over inputs; console clean.

Estimated total: ~63 focused hours. Order is dependency-driven: 0 before 1 (dialog is
the morph target), 1 before 2/3 (motion.ts), 4 before 5 (composer learnings on the
simpler scene first).
