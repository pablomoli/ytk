# ytk hub React migration — Phase 1–2 (scaffold + inbox) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a Vite+ React/TypeScript SPA served by the existing FastAPI hub under `/app`, and rebuild the inbox page at `/app/inbox` with feature parity, bounded DOM, and end-to-end typed API calls — leaving the legacy hub fully working.

**Architecture:** Client-side React SPA (no SSR) talking to the unchanged FastAPI backend over a typed fetch client generated from the backend's OpenAPI schema. TanStack Router for typed client routing (filter state in the URL), TanStack Query for server-state/caching/polling/mutations, CSS masonry with infinite-scroll windowing for the 744-card grid. The SPA is mounted under `/app/*` so it coexists with legacy pages until a final flip.

**Tech Stack:** Vite+ (`vp` CLI, beta, MIT) · React 19 + TypeScript · TanStack Router · TanStack Query · (TanStack Virtual deferred) · FastAPI (unchanged) · Vitest · openapi-typescript.

## Global Constraints

- Toolchain is Vite+: use `vp` for dev/build/test/check. Config is `vite.config.ts` using `defineConfig` from `vite-plus`. Fallback to plain Vite is acceptable if a `vp` command is broken in beta — note it in the commit.
- Frontend lives entirely in `web/`. Do NOT change FastAPI handler behavior; only add the `/app` SPA mount + fallback and (where noted) additive Pydantic response models.
- Coexistence: legacy routes (`/`, `/inbox`, `/tags`, `/map`, `/settings`, `/api/*`, `/vault-media/*`, `/static/*`, `/favicon.svg`) must keep working. The `/app` SPA fallback must be registered so it never shadows those.
- No emojis anywhere. No conversational comments in code — document normally and sparingly.
- The backend dev server runs on `:6969` (launchd `com.ytk.hub`). The Vite+ dev server runs on `:5173` and proxies to it.
- `web/dist` is committed so `uv tool install` ships the built assets.
- Commit after every task. Never leave the worktree dirty.

---

### Task 1: Scaffold the Vite+ React/TS app in `web/`

**Files:**
- Create: `web/` (project: `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx`)
- Create: `web/.gitignore` (ignore `node_modules`, keep `dist`)

**Interfaces:**
- Produces: a runnable SPA at dev `:5173`; a production build in `web/dist`.

- [ ] **Step 1: Install Vite+ if absent**

Run: `command -v vp || curl -fsSL https://vite.plus | bash`
Expected: `vp --version` prints a version.

- [ ] **Step 2: Scaffold into `web/`**

Run from repo root: `vp create web`
Select the **React + TypeScript** template interactively. If a non-interactive flag exists (`vp create web --template react-ts`), prefer it. Then `cd web && vp install`.
Expected: `web/` contains `package.json`, `vite.config.ts`, `tsconfig.json`, `src/main.tsx`.

- [ ] **Step 3: Add TanStack deps**

Run in `web/`: `vp add @tanstack/react-router @tanstack/react-query @tanstack/react-virtual` and dev deps `vp add -D openapi-typescript @tanstack/router-plugin`
Expected: they appear in `web/package.json`.

- [ ] **Step 4: Trim the template to a minimal App**

Replace `web/src/App.tsx` with:
```tsx
export default function App() {
  return <div id="app-root">ytk hub (react) — scaffold ok</div>
}
```
Ensure `web/src/main.tsx` mounts `<App/>` into `#root` and imports no template demo CSS beyond a reset.

- [ ] **Step 5: Verify dev + build**

Run in `web/`: `vp dev` (confirm `:5173` serves the text, then stop it), then `vp build`.
Expected: `web/dist/index.html` and `web/dist/assets/*` exist.

- [ ] **Step 6: Commit**

```bash
git add web && git commit -m "feat(web): scaffold Vite+ React/TS app"
```

---

### Task 2: Serve the SPA from FastAPI under `/app`

**Files:**
- Modify: `ytk/ui/server.py` (add SPA mount + fallback near the other page routes, AFTER all `/api/*`, `/vault-media`, `/static`, `/favicon.svg`, and legacy page routes)
- Test: `tests/ui/test_spa_mount.py`

**Interfaces:**
- Consumes: `web/dist` from Task 1.
- Produces: `GET /app` and `GET /app/<anything>` return the SPA `index.html`; `/app/assets/*` serve built assets.

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_spa_mount.py
from fastapi.testclient import TestClient
from ytk.ui.server import app

client = TestClient(app)

def test_app_route_serves_spa_index():
    r = client.get("/app/inbox")
    assert r.status_code == 200
    assert 'id="root"' in r.text  # SPA shell

def test_legacy_inbox_still_served():
    r = client.get("/inbox")
    assert r.status_code == 200
    assert "showSkeletons" in r.text  # legacy inbox JS still present

def test_api_not_shadowed_by_spa():
    r = client.get("/api/fresh?n=1")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/ui/test_spa_mount.py -v`
Expected: `test_app_route_serves_spa_index` FAILS (404).

- [ ] **Step 3: Implement the SPA mount**

In `ytk/ui/server.py`, after the existing legacy page routes and the `_STATIC_DIR` setup, add:
```python
_WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

if (_WEB_DIST / "assets").is_dir():
    app.mount("/app/assets", StaticFiles(directory=_WEB_DIST / "assets"), name="app-assets")

@app.get("/app", response_class=HTMLResponse)
@app.get("/app/{path:path}", response_class=HTMLResponse)
def _spa(path: str = "") -> HTMLResponse:
    index = _WEB_DIST / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>web/dist not built — run vp build</h1>", status_code=404)
    return HTMLResponse(index.read_text(encoding="utf-8"))
```
Confirm this block is registered AFTER every `/api/*`, `/vault-media`, `/static`, `/favicon.svg`, and legacy page route so ordering doesn't shadow them.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/ui/test_spa_mount.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ytk/ui/server.py tests/ui/test_spa_mount.py
git commit -m "feat(hub): serve the react SPA under /app, legacy untouched"
```

---

### Task 3: Dev proxy so `:5173` reaches the backend

**Files:**
- Modify: `web/vite.config.ts`

**Interfaces:**
- Produces: dev requests to `/api`, `/vault-media`, `/favicon.svg` from `:5173` proxy to `:6969`.

- [ ] **Step 1: Configure the proxy**

```ts
// web/vite.config.ts
import { defineConfig } from 'vite-plus'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'

export default defineConfig({
  plugins: [TanStackRouterVite()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:6969',
      '/vault-media': 'http://127.0.0.1:6969',
      '/favicon.svg': 'http://127.0.0.1:6969',
    },
  },
})
```
(If the scaffolded config already imports the React plugin, keep it alongside these.)

- [ ] **Step 2: Verify the proxy**

Run in `web/`: `vp dev`, then in another shell `curl -s localhost:5173/api/fresh?n=1 | head -c 80`
Expected: JSON (proxied from :6969), not the SPA HTML.

- [ ] **Step 3: Commit**

```bash
git add web/vite.config.ts && git commit -m "feat(web): dev proxy /api and /vault-media to :6969"
```

---

### Task 4: Generated types + typed fetch client + Query provider

**Files:**
- Create: `web/src/api/schema.ts` (generated — do not hand-edit)
- Create: `web/src/api/client.ts`
- Create: `web/src/api/gen.sh` (regeneration helper)
- Modify: `web/src/main.tsx` (wrap app in `QueryClientProvider`)
- Test: `web/src/api/client.test.ts`

**Interfaces:**
- Produces: `apiGet<T>(path)` typed fetch; a shared `queryClient`; `components['schemas']` types from OpenAPI.

- [ ] **Step 1: Generate types from the running backend**

```bash
# web/src/api/gen.sh
npx openapi-typescript http://127.0.0.1:6969/openapi.json -o web/src/api/schema.ts
```
Run: `bash web/src/api/gen.sh` (backend must be up on :6969).
Expected: `web/src/api/schema.ts` created with a `paths` and `components` export.

- [ ] **Step 2: Write the failing test for the client**

```ts
// web/src/api/client.test.ts
import { expect, test, vi } from 'vitest'
import { apiGet } from './client'

test('apiGet returns parsed json', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([{ path: 'a' }]), { status: 200 })))
  const data = await apiGet<{ path: string }[]>('/api/fresh?n=1')
  expect(data[0].path).toBe('a')
})

test('apiGet throws on non-2xx', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('nope', { status: 500 })))
  await expect(apiGet('/api/fresh')).rejects.toThrow()
})
```

- [ ] **Step 3: Run to verify it fails**

Run in `web/`: `vp test src/api/client.test.ts`
Expected: FAIL (no `client.ts`).

- [ ] **Step 4: Implement the client + provider**

```ts
// web/src/api/client.ts
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
})

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

export async function apiSend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${path} -> ${res.status}: ${await res.text()}`)
  return res.json() as Promise<T>
}
```
In `web/src/main.tsx`, wrap the router/app in `<QueryClientProvider client={queryClient}>`.

- [ ] **Step 5: Run tests**

Run in `web/`: `vp test src/api/client.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/api web/src/main.tsx
git commit -m "feat(web): openapi-generated types + typed fetch client + Query provider"
```

---

### Task 5: TanStack Router with `/app` + `/app/inbox`

**Files:**
- Create: `web/src/router.tsx`, `web/src/routes/__root.tsx`, `web/src/routes/index.tsx`, `web/src/routes/inbox.tsx`
- Modify: `web/src/main.tsx` (render `<RouterProvider>`)

**Interfaces:**
- Produces: client routes under basepath `/app`; `/app/inbox` renders the inbox route component; source filter read from typed search params.

- [ ] **Step 1: Configure the router with basepath `/app`**

```tsx
// web/src/router.tsx
import { createRouter } from '@tanstack/react-router'
import { routeTree } from './routeTree.gen'
export const router = createRouter({ routeTree, basepath: '/app' })
declare module '@tanstack/react-router' {
  interface Register { router: typeof router }
}
```

- [ ] **Step 2: Root + inbox routes**

```tsx
// web/src/routes/__root.tsx
import { createRootRoute, Link, Outlet } from '@tanstack/react-router'
export const Route = createRootRoute({
  component: () => (<><nav><Link to="/inbox">inbox</Link></nav><Outlet /></>),
})
```
```tsx
// web/src/routes/inbox.tsx
import { createFileRoute } from '@tanstack/react-router'
export const Route = createFileRoute('/inbox')({
  validateSearch: (s: Record<string, unknown>): { source?: string } => ({
    source: typeof s.source === 'string' ? s.source : undefined,
  }),
  component: InboxPage,
})
function InboxPage() {
  const { source } = Route.useSearch()
  return <div id="inbox-page">inbox route ok{source ? ` (filter: ${source})` : ''}</div>
}
```

- [ ] **Step 3: Render the router**

In `web/src/main.tsx`, render `<RouterProvider router={router} />` inside `<QueryClientProvider>`.

- [ ] **Step 4: Verify**

Run in `web/`: `vp dev`, open `localhost:5173/app/inbox?source=youtube`.
Expected: renders "inbox route ok (filter: youtube)".

- [ ] **Step 5: Commit**

```bash
git add web/src && git commit -m "feat(web): TanStack Router, /app/inbox route with typed search params"
```

---

### Task 6: `useQueue` — the inbox data hook

**Files:**
- Create: `web/src/api/queue.ts`
- Test: `web/src/api/queue.test.ts`

**Interfaces:**
- Consumes: `apiGet` (Task 4).
- Produces: `type QueueItem` (fields: `url`, `source`, `title?`, `thumbnail?`, `channel?`, plus what `/api/queue` returns — confirm shape against the live endpoint); `useQueue()` returning `{ data, isLoading, isError }`.

- [ ] **Step 1: Confirm the live shape**

Run: `curl -s 'http://127.0.0.1:6969/api/queue' | python3 -m json.tool | head -40`
Record the actual keys; define `QueueItem` to match (do not invent fields).

- [ ] **Step 2: Write the failing test**

```ts
// web/src/api/queue.test.ts
import { expect, test, vi } from 'vitest'
import { fetchQueue } from './queue'

test('fetchQueue returns items', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([{ url: 'u', source: 'youtube' }]), { status: 200 })))
  const items = await fetchQueue()
  expect(items[0].source).toBe('youtube')
})
```

- [ ] **Step 3: Run to verify it fails**

Run in `web/`: `vp test src/api/queue.test.ts` — FAIL.

- [ ] **Step 4: Implement**

```ts
// web/src/api/queue.ts
import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'

export type QueueItem = {
  url: string
  source: string
  title?: string
  thumbnail?: string
  channel?: string
}

export const fetchQueue = () => apiGet<QueueItem[]>('/api/queue')
export const useQueue = () => useQuery({ queryKey: ['queue'], queryFn: fetchQueue })
```

- [ ] **Step 5: Run + commit**

Run: `vp test src/api/queue.test.ts` — PASS.
```bash
git add web/src/api/queue.ts web/src/api/queue.test.ts
git commit -m "feat(web): useQueue hook over /api/queue"
```

---

### Task 7: `<Card>` — one component for all source types

**Files:**
- Create: `web/src/components/Card.tsx`, `web/src/components/icons.tsx`
- Test: `web/src/components/Card.test.tsx`

**Interfaces:**
- Consumes: `QueueItem` (Task 6).
- Produces: `<Card item={QueueItem} onOpen={(item)=>void} />`.

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/components/Card.test.tsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { Card } from './Card'

test('renders a youtube card with title and source badge', () => {
  render(<Card item={{ url: 'u', source: 'youtube', title: 'Hello' }} onOpen={() => {}} />)
  expect(screen.getByText('Hello')).toBeInTheDocument()
  expect(screen.getByTestId('card-source')).toHaveTextContent('youtube')
})
```
(Historical note: the first migration plan used Testing Library with a synthetic DOM. The current suite runs in Chromium.)

- [ ] **Step 2: Run to verify it fails** — `vp test src/components/Card.test.tsx` → FAIL.

- [ ] **Step 3: Implement Card**

```tsx
// web/src/components/Card.tsx
import type { QueueItem } from '../api/queue'

export function Card({ item, onOpen }: { item: QueueItem; onOpen: (i: QueueItem) => void }) {
  return (
    <div className="card" onClick={() => onOpen(item)}>
      {item.thumbnail
        ? <img src={`/vault-media/${item.thumbnail}`} loading="lazy" alt="" />
        : <div className="noimg">{item.source}</div>}
      <div className="meta">
        <div className="title">{item.title ?? item.url}</div>
        <div className="sub"><span data-testid="card-source">{item.source}</span></div>
      </div>
    </div>
  )
}
```
Port source icons into `icons.tsx` from `ytk/ui/static/fresh.html` (the `ICONS` map) as small components; wire into the badge. Keep styling minimal for now (a `card.css` port comes with assembly, Task 13).

- [ ] **Step 4: Run + commit**

`vp test src/components/Card.test.tsx` → PASS.
```bash
git add web/src/components && git commit -m "feat(web): shared Card component for all source types"
```

---

### Task 8: `<SourceFilter>` bound to URL search params

**Files:**
- Create: `web/src/components/SourceFilter.tsx`
- Test: `web/src/components/SourceFilter.test.tsx`

**Interfaces:**
- Produces: `<SourceFilter value={string|undefined} onChange={(s?:string)=>void} />` over the fixed source list `['instagram','youtube','pinterest','tiktok','web','memo']`.

- [ ] **Step 1: Failing test** — clicking a chip calls `onChange` with that source; clicking the active chip calls `onChange(undefined)`.

```tsx
// web/src/components/SourceFilter.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { SourceFilter } from './SourceFilter'

test('toggles source', () => {
  const onChange = vi.fn()
  const { rerender } = render(<SourceFilter value={undefined} onChange={onChange} />)
  fireEvent.click(screen.getByText('youtube'))
  expect(onChange).toHaveBeenCalledWith('youtube')
  rerender(<SourceFilter value="youtube" onChange={onChange} />)
  fireEvent.click(screen.getByText('youtube'))
  expect(onChange).toHaveBeenCalledWith(undefined)
})
```

- [ ] **Step 2: Verify fails** — `vp test src/components/SourceFilter.test.tsx` → FAIL.

- [ ] **Step 3: Implement**

```tsx
// web/src/components/SourceFilter.tsx
const SOURCES = ['instagram', 'youtube', 'pinterest', 'tiktok', 'web', 'memo']
export function SourceFilter({ value, onChange }: { value?: string; onChange: (s?: string) => void }) {
  return (
    <span className="filters">
      {SOURCES.map(s => (
        <button key={s} className={`fchip${value === s ? ' on' : ''}`}
          onClick={() => onChange(value === s ? undefined : s)}>{s}</button>
      ))}
    </span>
  )
}
```

- [ ] **Step 4: Run + commit** — PASS; `git commit -m "feat(web): SourceFilter chips"`.

---

### Task 9: Masonry grid with batched relayout

**Files:**
- Create: `web/src/lib/masonry.ts`, `web/src/components/MasonryGrid.tsx`
- Test: `web/src/lib/masonry.test.ts`

**Interfaces:**
- Produces: `spanFor(scrollHeight:number, rowH=8, gap=12): number` (pure); `<MasonryGrid>{children}</MasonryGrid>` that measures children in a batched read-then-write `requestAnimationFrame` pass (all `scrollHeight` reads before any `gridRowEnd` writes).

- [ ] **Step 1: Failing test for the pure span math**

```ts
// web/src/lib/masonry.test.ts
import { expect, test } from 'vitest'
import { spanFor } from './masonry'
test('spanFor computes row span from height', () => {
  expect(spanFor(200)).toBe(Math.ceil((200 + 12) / (8 + 12)))
})
```

- [ ] **Step 2: Verify fails** — FAIL.

- [ ] **Step 3: Implement**

```ts
// web/src/lib/masonry.ts
export const spanFor = (h: number, rowH = 8, gap = 12) => Math.ceil((h + gap) / (rowH + gap))
```
```tsx
// web/src/components/MasonryGrid.tsx
import { useEffect, useRef } from 'react'
import { spanFor } from '../lib/masonry'

export function MasonryGrid({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const grid = ref.current
    if (!grid) return
    let raf = 0
    const relayout = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const cards = [...grid.querySelectorAll<HTMLElement>('.card')]
        const spans = cards.map(c => spanFor(c.scrollHeight)) // READ all
        cards.forEach((c, i) => { c.style.gridRowEnd = `span ${spans[i]}` }) // WRITE all
      })
    }
    relayout()
    const ro = new ResizeObserver(relayout)
    ro.observe(grid)
    grid.querySelectorAll('img').forEach(img => img.addEventListener('load', relayout))
    return () => { ro.disconnect(); if (raf) cancelAnimationFrame(raf) }
  })
  return <main ref={ref} className="masonry">{children}</main>
}
```
Add `.masonry` CSS (grid, `grid-auto-rows: 8px`, `grid-auto-flow: row dense`) to a `web/src/styles.css` ported from the legacy `#fresh` rules.

- [ ] **Step 4: Run + commit** — PASS; `git commit -m "feat(web): batched-relayout MasonryGrid"`.

---

### Task 10: Infinite-scroll windowing hook

**Files:**
- Create: `web/src/lib/useInfiniteWindow.ts`
- Test: `web/src/lib/useInfiniteWindow.test.ts`

**Interfaces:**
- Produces: `useInfiniteWindow<T>(items: T[], step=60): { visible: T[]; sentinelRef: (el: HTMLElement|null)=>void }`. Grows `visible` by `step` when the sentinel intersects. Resets to `step` when `items` identity changes (e.g. filter change).

- [ ] **Step 1: Failing test for the pure paging logic**

Extract the count logic as a pure function to test without a DOM:
```ts
// web/src/lib/useInfiniteWindow.test.ts
import { expect, test } from 'vitest'
import { nextCount } from './useInfiniteWindow'
test('nextCount grows by step, clamped to total', () => {
  expect(nextCount(60, 744, 60)).toBe(120)
  expect(nextCount(720, 744, 60)).toBe(744)
})
```

- [ ] **Step 2: Verify fails** — FAIL.

- [ ] **Step 3: Implement**

```ts
// web/src/lib/useInfiniteWindow.ts
import { useCallback, useEffect, useRef, useState } from 'react'

export const nextCount = (cur: number, total: number, step: number) => Math.min(cur + step, total)

export function useInfiniteWindow<T>(items: T[], step = 60) {
  const [count, setCount] = useState(step)
  useEffect(() => { setCount(step) }, [items, step])
  const obs = useRef<IntersectionObserver | null>(null)
  const sentinelRef = useCallback((el: HTMLElement | null) => {
    obs.current?.disconnect()
    if (!el) return
    obs.current = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting) setCount(c => nextCount(c, items.length, step))
    })
    obs.current.observe(el)
  }, [items.length, step])
  return { visible: items.slice(0, count), sentinelRef }
}
```

- [ ] **Step 4: Run + commit** — PASS; `git commit -m "feat(web): infinite-scroll windowing hook"`.

---

### Task 11: Loading skeletons, empty, and error states

**Files:**
- Create: `web/src/components/Skeletons.tsx`, `web/src/components/StateViews.tsx`
- Test: `web/src/components/Skeletons.test.tsx`

**Interfaces:**
- Produces: `<Skeletons count?=12 />` (varied-span pulsing placeholders), `<EmptyState label />`, `<ErrorState error />`.

- [ ] **Step 1: Failing test** — `<Skeletons count={5}/>` renders 5 `.skel` nodes.

```tsx
import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { Skeletons } from './Skeletons'
test('renders N skeletons', () => {
  const { container } = render(<Skeletons count={5} />)
  expect(container.querySelectorAll('.skel')).toHaveLength(5)
})
```

- [ ] **Step 2: Verify fails** — FAIL.

- [ ] **Step 3: Implement** (port `.skel`/`@keyframes pulse` CSS from master's fresh.html into `styles.css`):

```tsx
// web/src/components/Skeletons.tsx
const SPANS = [22, 30, 18, 26, 34, 20]
export function Skeletons({ count = 12 }: { count?: number }) {
  return <>{Array.from({ length: count }, (_, i) =>
    <div key={i} className="skel" style={{ gridRowEnd: `span ${SPANS[i % SPANS.length]}` }} />)}</>
}
```
```tsx
// web/src/components/StateViews.tsx
export const EmptyState = ({ label }: { label: string }) => <div className="empty">{label}</div>
export const ErrorState = ({ error }: { error: unknown }) =>
  <div className="empty">failed to load: {String(error)}</div>
```

- [ ] **Step 4: Run + commit** — PASS; `git commit -m "feat(web): skeleton/empty/error state views"`.

---

### Task 12: Mutations (add / refresh / ingest) + job-progress polling

**Files:**
- Create: `web/src/api/mutations.ts`, `web/src/api/job.ts`
- Test: `web/src/api/mutations.test.ts`

**Interfaces:**
- Consumes: `apiSend`, `queryClient` (Task 4).
- Produces: `useAddUrls()`, `useRefreshSources()`, `useIngest()` (each invalidates `['queue']` on success); `useJobStatus()` polling `/api/ingest/status` every 1s. Confirm the exact request/response shapes of `/api/queue/add`, `/api/queue/refresh`, `/api/ingest`, `/api/ingest/status` against the live backend before coding (curl each).

- [ ] **Step 1: Confirm live shapes**

Run: `curl -s http://127.0.0.1:6969/api/ingest/status | python3 -m json.tool` and inspect `server.py` handlers for the POST bodies. Record fields.

- [ ] **Step 2: Failing test** — `useAddUrls` posts to `/api/queue/add` and invalidates the queue.

```ts
// web/src/api/mutations.test.ts
import { expect, test, vi } from 'vitest'
import { addUrls } from './mutations'
test('addUrls posts urls', async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ added: 1 }), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  await addUrls(['https://x'])
  expect(fetchMock).toHaveBeenCalledWith('/api/queue/add', expect.objectContaining({ method: 'POST' }))
})
```

- [ ] **Step 3: Verify fails** — FAIL.

- [ ] **Step 4: Implement** the plain async fns (`addUrls`, `refreshSources`, `ingest`) with `apiSend`, then wrap each in a `useMutation` that calls `queryClient.invalidateQueries({ queryKey: ['queue'] })` on success; `useJobStatus` = `useQuery({ queryKey:['job'], queryFn: fetchJob, refetchInterval: 1000 })`.

- [ ] **Step 5: Run + commit** — PASS; `git commit -m "feat(web): queue mutations + job-status polling"`.

---

### Task 13: Assemble `/app/inbox` + parity smoke test

**Files:**
- Modify: `web/src/routes/inbox.tsx` (compose everything)
- Create: `web/src/styles.css` (final port of inbox/fresh card + grid + chrome CSS)
- Test: manual + headless smoke (Puppeteer) checklist

**Interfaces:**
- Consumes: `useQueue`, `SourceFilter`, `Card`, `MasonryGrid`, `useInfiniteWindow`, `Skeletons`/`EmptyState`/`ErrorState`, mutations, `useJobStatus`.

- [ ] **Step 1: Compose the route**

`InboxPage` reads `source` from `Route.useSearch()`, writes it via `useNavigate` (URL-as-state), filters `useQueue().data`, feeds the filtered list to `useInfiniteWindow`, renders `<MasonryGrid>` of `<Card>`s plus a sentinel `<div ref={sentinelRef}/>`, shows `<Skeletons/>` while `isLoading`, `<EmptyState/>` when empty, `<ErrorState/>` on error, the add box + refresh button (mutations), and a progress bar from `useJobStatus`.

- [ ] **Step 2: Build + serve via FastAPI**

Run: `cd web && vp build`, then reinstall/restart the hub:
```bash
uv tool install --reinstall . && launchctl kickstart -k "gui/$(id -u)/com.ytk.hub"
```

- [ ] **Step 3: Headless parity + bounded-DOM smoke test**

Navigate headless to `http://127.0.0.1:6969/app/inbox` and assert: cards render; no console errors; DOM `.card` count starts near the window size (~60), not 744; scrolling appends more; the source filter updates the URL and the grid. Compare visually against legacy `/inbox`.
Expected: parity, and `.card` count stays bounded (does not equal the full queue length on first paint).

- [ ] **Step 4: Commit**

```bash
git add web ytk && git commit -m "feat(web): /app/inbox with windowed masonry, filters, mutations, job progress"
```

---

## Self-Review

- **Spec coverage:** scaffold (T1), `/app` mount + coexistence (T2), dev proxy (T3), typed OpenAPI client + Query (T4), Router + URL filter state (T5), inbox data (T6), shared Card (T7), filter (T8), masonry batched relayout (T9), infinite-scroll windowing (T10), loading/empty/error (T11), mutations + job polling (T12), assembly + bounded-DOM smoke (T13). Phases 3–4 (fresh/tags/settings/map port, then flip to root) are intentionally out of this plan.
- **Placeholder scan:** the deliberately-verify-against-live steps (T6.1, T12.1) are explicit "curl and record the real shape" actions, not code placeholders — the backend is the source of truth for those shapes and inventing fields would be worse than reading them. Types are pinned to observed keys.
- **Type consistency:** `QueueItem` defined in T6 is consumed by T7/T13; `apiGet`/`apiSend`/`queryClient` from T4 consumed by T6/T12; `spanFor` (T9) used by MasonryGrid; `nextCount`/`useInfiniteWindow` (T10) used by T13. Names consistent across tasks.

## Risks / notes

- Vite+ is beta: any broken `vp` subcommand → fall back to the underlying tool (`vite`, `vitest`) and note it. Low lock-in by design.
- `vp create` is interactive; the executor must select React + TypeScript (or use a `--template` flag if available).
- Testing Library may not be in the template — Task 7 adds it on first need.
