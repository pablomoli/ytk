# ytk hub → Vite+ React SPA migration — design

Date: 2026-07-10
Branch: `feat/hub-react-migration`
Status: design (awaiting spec review)

## Problem

The ytk ingest hub (`ytk ui`, FastAPI on :6969) is a set of hand-written,
server-rendered HTML pages with inline vanilla JS: `fresh.html` (/),
`inbox.html` (/inbox), `map.html` (/map), `settings.html`, `tags.html`. The UI
is the user's primary interface to ytk (the MCP server is the assistant's
interface). It has three structural problems:

1. **No reactivity.** Every state change is a manual `innerHTML = ...` followed
   by re-attaching event listeners and re-measuring layout. That manual DOM sync
   is the bug surface — e.g. the masonry layout-thrashing bug that dropped the
   fresh feed to ~1 FPS existed in *two* files because the card + masonry code is
   copy-pasted between `fresh.html` and `inbox.html`.
2. **No windowing.** The inbox renders all queue items at once (measured: 744
   cards in the DOM simultaneously), each with a cover image.
3. **Full-page reloads between routes.** Navigation is `<a href>`, so each route
   change reloads the page and refetches its whole dataset.

The layout-thrash and missing-loading-state symptoms were fixed directly on
master (commit `af09b5a`) as a stopgap. This migration addresses the root cause:
the hand-rolled DOM architecture.

## Goals

- A reactive component-based frontend where shared UI (cards, filters, grids) is
  written once.
- Client-side routing so route changes are instant, no full reload.
- Bounded DOM on large lists (inbox) via windowing.
- End-to-end type safety between the FastAPI backend and the frontend.
- Incremental, low-risk migration — never a broken hub during the transition,
  with the option to abandon cheaply.

## Non-goals

- No SSR / server-side rendering. This is a localhost tool; there is no SEO or
  cold-first-paint concern, and FastAPI is already the backend.
- No second server runtime. FastAPI stays the only backend.
- Not migrating the map's 1.3 MB payload problem here — that is issue #68 and
  stays its own task. The map *page* gets ported like the others; the data
  windowing is separate.

## Stack (locked)

| Concern | Choice | Why |
|---|---|---|
| Toolchain | **Vite+** (beta, MIT) | One CLI for dev/test/lint/build; Rust core. Superset of standard Vite, so fallback to plain Vite is trivial. Now MIT after Cloudflare's VoidZero acquisition — no licensing risk. |
| Framework | **React + TypeScript**, client-side SPA | User wants to reuse React's component ecosystem. TS for type safety. |
| Routing | **TanStack Router** | Type-safe client routing; kills full-reload navigation. |
| Data | **TanStack Query** | Fetch + cache against FastAPI; loading/error/empty states become declarative. |
| Large lists | **TanStack Virtual** (later) + infinite-scroll (v1) | See "Grid strategy". |
| Backend | **FastAPI, unchanged** | Already serves clean JSON; becomes the single source of truth for API types. |

Explicitly rejected: Next.js and TanStack Start (both full-stack meta-frameworks
that want to own a JS server — duplicating FastAPI for zero benefit on a local
tool).

## Architecture

```
Browser (React SPA, TanStack Router)
   |  fetch /api/*  (typed client)
   v
FastAPI (:6969)  — unchanged handlers, plus SPA mount
   |
   v
vault / chroma / etc.
```

- Dev: `vite-plus dev` on :5173 with HMR, proxying `/api`, `/vault-media`,
  `/favicon.svg` to FastAPI :6969. FastAPI runs as today.
- Prod: `vite-plus build` → `web/dist`. FastAPI serves `dist/index.html` and
  `/assets/*`, with a SPA-fallback route so client routes survive a hard refresh.

## Repo layout

```
ytk/
  web/                       # new frontend project (own package.json, tsconfig)
    index.html
    vite.config.ts
    src/
      main.tsx
      router.tsx             # TanStack Router route tree
      routes/
        inbox.tsx            # first migrated page
      components/            # Card, SourceFilter, MasonryGrid, Skeletons — built ONCE
      api/
        schema.ts            # generated from FastAPI OpenAPI (do not hand-edit)
        client.ts            # typed fetch wrapper + TanStack Query hooks
      lib/                   # masonry layout, infinite-scroll hook
    dist/                    # build output, shipped with the package
  ytk/ui/server.py           # keeps all /api/* handlers; gains SPA mount + fallback
  ytk/ui/static/*.html       # legacy pages — deleted page-by-page as migrated
```

## Coexistence strategy (de-risks "another SPA you rip out")

During migration the React SPA is mounted under a dedicated prefix; legacy pages
stay exactly where they are.

- React SPA served at **`/app/*`** (its own SPA fallback under that prefix →
  `dist/index.html`). New inbox lives at `/app/inbox`.
- Legacy pages untouched at `/`, `/inbox`, `/tags`, `/map`, `/settings`.
- This lets the user compare **new `/app/inbox` next to old `/inbox`** with
  nothing broken. If the migration is abandoned, delete `web/` and the `/app`
  mount — legacy is undisturbed.
- **Flip step (end of migration):** once every page is ported and validated,
  one commit remounts the SPA at root and deletes `ytk/ui/static/*.html`.

FastAPI route ordering must keep `/api/*`, `/vault-media/*`, `/static/*`,
`/favicon.svg`, and the legacy page routes ahead of the `/app` SPA fallback so
nothing is shadowed.

## First slice — inbox (`/app/inbox`)

Rebuild the inbox page as the first migrated route, because it is the heaviest
(744 cards) and exercises every hard problem (windowing, live job progress,
actions, filters).

Components:
- `<Card>` — one component for all source types (youtube, instagram, memo, ...),
  replacing the copy-pasted card markup. Reused later by the fresh feed.
- `<SourceFilter>` — the filter chips.
- `<MasonryGrid>` — CSS-column / dense-grid masonry wrapper.
- `<Skeletons>` — declarative loading state.
- Job-progress bar bound to `/api/ingest/status` (or existing status endpoint)
  via TanStack Query polling.

Data: TanStack Query hooks over the existing `/api/queue`, `/api/queue/add`,
`/api/queue/refresh`, `/api/ingest`, `/api/ingest/status`, `/api/cover`,
`/api/inbox-search` endpoints. No backend changes expected; if a shape is
awkward for the client, prefer a small additive endpoint over reshaping an
existing one.

## Grid strategy

**v1: infinite-scroll windowing, masonry preserved.** Render ~60 cards; append
the next batch when a sentinel enters view (IntersectionObserver). Keeps the
Pinterest-style varied-height look, bounds the DOM to ~60–180 nodes, and needs
no height-measurement gymnastics. Row-span measurement uses the same batched
read-then-write discipline as the master-branch fix (all reads before any
writes) so it never thrashes.

**Later (optional): TanStack Virtual masonry** — only visible cards in the DOM at
any count. Deferred because virtualized masonry (column assignment + measured
heights) is the genuinely hard case and infinite-scroll already bounds the DOM.

## Typed API client

FastAPI auto-generates an OpenAPI schema at `/openapi.json`. Generate TypeScript
types from it with `openapi-typescript`:

```
npx openapi-typescript http://127.0.0.1:6969/openapi.json -o web/src/api/schema.ts
```

`src/api/client.ts` wraps `fetch` with those types and exposes TanStack Query
hooks. Regenerating `schema.ts` after a backend route change surfaces any
frontend mismatch as a compile error. This makes the Python backend the single
source of truth for API shapes.

Caveat: some existing endpoints may return loosely-typed dicts; where OpenAPI
types come through as `unknown`/`any`, add Pydantic response models on the
FastAPI side incrementally (additive, no behavior change) to tighten them.

## Testing

- **Vitest** (bundled in Vite+) for component and hook logic.
- **Headless-browser smoke test** (Puppeteer, as already used) for end-to-end
  sanity: page renders, cards present, no console errors, windowing bounds the
  DOM node count.

## Packaging

`ytk ui` is installed via `uv tool install`. The built `web/dist` must ship with
the package so the installed copy can serve it. v1: commit `web/dist` (personal
tool, simplest). If that proves noisy, move to a build step in packaging later.

## Migration phases

1. **Scaffold** — `web/` Vite+ React TS project; FastAPI `/app` SPA mount +
   fallback; dev proxy; OpenAPI→TS type generation wired; a trivial `/app`
   route renders. Legacy untouched.
2. **Inbox** — full `/app/inbox` with shared components, TanStack Query,
   infinite-scroll masonry, job progress, filters, actions. Validate against
   legacy `/inbox`.
3. **Fresh, tags, settings, map** — port page-by-page, reusing `<Card>` etc.
4. **Flip** — remount SPA at root, delete legacy `static/*.html`, remove `/app`
   prefix.

This spec covers phases 1–2 (scaffold + inbox) as the first implementation plan.
Phases 3–4 get their own plans once the pattern is proven on inbox.

## Success criteria (phases 1–2)

- `vite-plus dev` runs with HMR, proxying to FastAPI; `vite-plus build` produces
  `dist` that FastAPI serves at `/app`.
- `/app/inbox` reaches feature parity with legacy `/inbox`: same cards, filters,
  add box, refresh, ingest actions, job progress.
- Inbox DOM node count stays bounded while scrolling the full 744-item queue
  (verified: node count does not grow unboundedly).
- API calls are typed from the generated schema; a deliberate wrong-shape call
  fails at compile time.
- Legacy hub fully functional throughout (nothing at `/`, `/inbox`, etc. breaks).

## Open questions

- None blocking. Minor: whether to add Pydantic response models now vs.
  incrementally (decided: incrementally, only where types come through as
  `any`).
