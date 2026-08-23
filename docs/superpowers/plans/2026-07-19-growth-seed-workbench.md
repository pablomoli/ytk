# Growth Seed Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `/growth` as a moodboard-style DNA-seed workbench where each profile theme is an organism whose visuals derive from its real note metadata, with an M01-M04 mutation picker replacing the locked art direction.

**Architecture:** Pure derivation modules (dna, topology, palette, events, philosophy) feed a single-renderer WebGL workbench (main stage + mutation tiles as viewport regions of one canvas; gallery as 2D snapshots). Data comes from existing hub endpoints (`/api/profile`, `/api/library`, `/api/cover`) plus one new endpoint pair (`/api/growth/philosophy`). Adopted DNA and replay position persist in localStorage.

**Tech Stack:** React + TanStack Router SPA in `web/`, three.js WebGL2, vitest, FastAPI (`ytk/ui/server.py`).

## Global Constraints

- Growth is incremental: old tissue never reshuffles (spec "Kept from the demo").
- All derivation functions are deterministic: same input → same output. No `Math.random()` in lib code.
- Organisms key on stable theme ids; adopted DNA survives profile re-runs (localStorage keys `growth:adopted:<themeId>`, `growth:replay:<themeId>`).
- Philosophy constraints are hard clamps, applied after derivation and after mutation.
- No emojis anywhere. No conversational comments in code.
- Test commands run from `web/`: `npm test -- run <file>`; full build: `npm run build`.
- Commits end with the Claude-Session trailer already in use this session.

---

### Task 1: Baseline commit of the prior demo

**Files:**
- Commit as-is: `web/src/routes/growth.tsx`, `web/src/routes/growth.css`, `web/src/lib/growth/scene.ts`, `web/src/lib/growth/shaders.ts`, `web/src/routes/transit.tsx`, `web/src/routes/transit.css`, `web/src/routeTree.gen.ts`, `web/src/routes/__root.tsx`, current `web/dist/*`

**Interfaces:** none — history preservation so the #80 handoff state exists as a commit before rework.

- [ ] **Step 1: Commit the untracked prior-session demo files**

```bash
git add web/src/routes/growth.tsx web/src/routes/growth.css web/src/lib/growth/ \
        web/src/routes/transit.tsx web/src/routes/transit.css \
        web/src/routeTree.gen.ts web/src/routes/__root.tsx web/dist
git commit -m "feat(web): wip growth study + transit demos (pre-#80-retake baseline)"
```

Expected: clean `git status` for those paths. `prose.scratch` and `scratch` stay untracked (user scratch files, not ours).

### Task 2: SeedDNA derivation (`dna.ts`)

**Files:**
- Create: `web/src/lib/growth/dna.ts`
- Test: `web/src/lib/growth/dna.test.ts`

**Interfaces:**
- Produces: `OperatorName`, `OperatorWeights`, `SeedParams`, `SeedDNA`, `ThemeInput`, `Constraints`, `DEFAULT_CONSTRAINTS`, `hashString(s: string): number`, `seededRand(hash: number, salt: number): number` (0..1), `deriveDNA(theme: ThemeInput, constraints: Constraints): SeedDNA`, `mutateDNA(dna: SeedDNA, mutationSeed: number, constraints: Constraints): SeedDNA`, `RELIQUARY: SeedDNA`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/growth/dna.test.ts
import { expect, test } from 'vitest'
import { DEFAULT_CONSTRAINTS, deriveDNA, mutateDNA, RELIQUARY, type ThemeInput } from './dna'

const theme: ThemeInput = {
  id: 'th-creative', label: 'creative coding', weight: 0.8,
  n_notes: 40, fresh_notes: 10,
  tagCounts: { 'creative-coding': 18, 'cool-vis': 12, 'touchdesigner': 4 },
}

test('derivation is deterministic and complete', () => {
  const a = deriveDNA(theme, DEFAULT_CONSTRAINTS)
  const b = deriveDNA(theme, DEFAULT_CONSTRAINTS)
  expect(a).toEqual(b)
  expect(a.palette).toHaveLength(5)
  const ops = Object.values(a.operators)
  expect(Math.max(...ops)).toBeLessThanOrEqual(1)
  expect(Math.min(...ops)).toBeGreaterThanOrEqual(0)
})

test('creative-coding themes emphasize LACE and BLEED', () => {
  const dna = deriveDNA(theme, DEFAULT_CONSTRAINTS)
  expect(dna.operators.LACE).toBeGreaterThan(dna.operators.DEEPEN)
  expect(dna.operators.BLEED).toBeGreaterThan(dna.operators.MEMBRANE)
})

test('fitness themes emphasize DEEPEN and BUD', () => {
  const dna = deriveDNA({ ...theme, id: 'th-fit', tagCounts: { fitness: 10, mma: 6 } }, DEFAULT_CONSTRAINTS)
  expect(dna.operators.DEEPEN).toBeGreaterThan(dna.operators.LACE)
  expect(dna.operators.BUD).toBeGreaterThan(dna.operators.STIPPLE)
})

test('constraints clamp asymmetry floor', () => {
  const dna = deriveDNA(theme, { ...DEFAULT_CONSTRAINTS, asymmetry_min: 0.9 })
  expect(dna.params.asymmetry).toBeGreaterThanOrEqual(0.9)
})

test('mutations are deterministic, distinct, and clamped', () => {
  const dna = deriveDNA(theme, DEFAULT_CONSTRAINTS)
  const m1 = mutateDNA(dna, 1, DEFAULT_CONSTRAINTS)
  expect(mutateDNA(dna, 1, DEFAULT_CONSTRAINTS)).toEqual(m1)
  expect(m1).not.toEqual(mutateDNA(dna, 2, DEFAULT_CONSTRAINTS))
  expect(m1.params.asymmetry).toBeGreaterThanOrEqual(DEFAULT_CONSTRAINTS.asymmetry_min)
  expect(m1.themeId).toBe(dna.themeId)
})

test('reliquary preset is a valid seed', () => {
  expect(RELIQUARY.palette).toHaveLength(5)
  expect(RELIQUARY.name).toMatch(/reliquary/i)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- run src/lib/growth/dna.test.ts`
Expected: FAIL — module `./dna` not found.

- [ ] **Step 3: Implement `dna.ts`**

```ts
// web/src/lib/growth/dna.ts
export type OperatorName = 'DEEPEN' | 'BUD' | 'LACE' | 'STIPPLE' | 'BLEED' | 'MEMBRANE'
export type OperatorWeights = Record<OperatorName, number>
export type SeedParams = { density: number; motion: number; granularity: number; asymmetry: number }
export type SeedDNA = {
  themeId: string
  name: string
  palette: string[]
  operators: OperatorWeights
  params: SeedParams
}
export type ThemeInput = {
  id: string
  label: string
  weight: number
  n_notes: number
  fresh_notes: number
  tagCounts: Record<string, number>
  palette?: string[]
}
export type Constraints = {
  glow_max: number
  asymmetry_min: number
  curvature_min: number
  saturation_max: number
}

export const DEFAULT_CONSTRAINTS: Constraints = {
  glow_max: 0.35,
  asymmetry_min: 0.45,
  curvature_min: 0.3,
  saturation_max: 0.8,
}

const OPERATORS: OperatorName[] = ['DEEPEN', 'BUD', 'LACE', 'STIPPLE', 'BLEED', 'MEMBRANE']

// Tag families → operator emphasis. Weighted by the theme's real tag counts.
const TAG_FAMILIES: Array<{ match: RegExp; ops: Partial<OperatorWeights> }> = [
  { match: /creative-coding|generative|touchdesigner|shader|glitch|code-art|vj|art/, ops: { LACE: 1, BLEED: 0.8, STIPPLE: 0.3 } },
  { match: /fitness|mma|combat|muay|workout|yoga|training|nutrition|diet/, ops: { DEEPEN: 1, BUD: 0.8 } },
  { match: /physics|math|quantum|geometry|probability|fractal|dynamical/, ops: { STIPPLE: 1, MEMBRANE: 0.7, LACE: 0.3 } },
  { match: /^ai$|machine-learning|ai-|llm|neural|neuroscience|cognitive/, ops: { LACE: 0.9, STIPPLE: 0.7, BLEED: 0.3 } },
  { match: /design|typography|ui-|motion-design|film|cinema|movies|anime/, ops: { BLEED: 1, MEMBRANE: 0.8 } },
  { match: /hardware|diy|3d-print|electronics|gizmo|maker/, ops: { BUD: 1, MEMBRANE: 0.5 } },
]

export function hashString(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

export function seededRand(hash: number, salt: number): number {
  const x = Math.sin((hash % 100000) * 0.0137 + salt * 91.733) * 43758.5453123
  return x - Math.floor(x)
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v))

const FALLBACK_PALETTE = ['#1a1d24', '#3d4455', '#7c8499', '#c7ccd9', '#e8e4d8']

function applyConstraints(dna: SeedDNA, c: Constraints): SeedDNA {
  return {
    ...dna,
    params: { ...dna.params, asymmetry: Math.max(dna.params.asymmetry, c.asymmetry_min) },
  }
}

export function deriveDNA(theme: ThemeInput, constraints: Constraints): SeedDNA {
  const h = hashString(theme.id)
  const acc: OperatorWeights = { DEEPEN: 0.15, BUD: 0.15, LACE: 0.15, STIPPLE: 0.15, BLEED: 0.15, MEMBRANE: 0.15 }
  for (const [tag, count] of Object.entries(theme.tagCounts)) {
    for (const family of TAG_FAMILIES) {
      if (!family.match.test(tag)) continue
      for (const [op, w] of Object.entries(family.ops)) {
        acc[op as OperatorName] += (w as number) * count
      }
    }
  }
  const top = Math.max(...OPERATORS.map((op) => acc[op]))
  const operators = Object.fromEntries(
    OPERATORS.map((op) => [op, clamp01(acc[op] / top)]),
  ) as OperatorWeights
  const dna: SeedDNA = {
    themeId: theme.id,
    name: theme.label,
    palette: theme.palette && theme.palette.length === 5 ? theme.palette : FALLBACK_PALETTE,
    operators,
    params: {
      density: clamp01(0.35 + theme.weight * 0.55),
      motion: clamp01(theme.fresh_notes / Math.max(1, theme.n_notes)),
      granularity: clamp01(Math.log10(theme.n_notes + 1) / 2),
      asymmetry: 0.3 + seededRand(h, 3) * 0.6,
    },
  }
  return applyConstraints(dna, constraints)
}

export function mutateDNA(dna: SeedDNA, mutationSeed: number, constraints: Constraints): SeedDNA {
  const h = hashString(dna.themeId) ^ Math.imul(mutationSeed, 2654435761)
  const jitter = (v: number, salt: number, amount: number) =>
    clamp01(v + (seededRand(h, salt) - 0.5) * 2 * amount)
  const operators = Object.fromEntries(
    OPERATORS.map((op, i) => [op, jitter(dna.operators[op], 10 + i, 0.18)]),
  ) as OperatorWeights
  const mutated: SeedDNA = {
    ...dna,
    operators,
    params: {
      density: jitter(dna.params.density, 30, 0.12),
      motion: jitter(dna.params.motion, 31, 0.12),
      granularity: jitter(dna.params.granularity, 32, 0.12),
      asymmetry: jitter(dna.params.asymmetry, 33, 0.12),
    },
  }
  return applyConstraints(mutated, constraints)
}

// The old locked direction, demoted to one competing preset.
export const RELIQUARY: SeedDNA = {
  themeId: 'preset-reliquary',
  name: 'bio-digital reliquary',
  palette: ['#050607', '#8c2f1b', '#c65a2e', '#e8dfc9', '#3fb8af'],
  operators: { DEEPEN: 0.9, BUD: 0.6, LACE: 1, STIPPLE: 0.5, BLEED: 0.3, MEMBRANE: 0.7 },
  params: { density: 0.7, motion: 0.25, granularity: 0.6, asymmetry: 0.6 },
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- run src/lib/growth/dna.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/growth/dna.ts web/src/lib/growth/dna.test.ts
git commit -m "feat(growth): SeedDNA derivation from theme metadata with constraint clamps"
```

### Task 3: Palette extraction (`palette.ts`)

**Files:**
- Create: `web/src/lib/growth/palette.ts`
- Test: `web/src/lib/growth/palette.test.ts`

**Interfaces:**
- Produces: `kmeansPalette(pixels: Uint8ClampedArray, k?: number): string[]` (pure, deterministic, returns hex sorted by cluster size desc), `paletteFromCovers(urls: string[]): Promise<string[] | null>` (browser-only helper; returns null when nothing loads).

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/growth/palette.test.ts
import { expect, test } from 'vitest'
import { kmeansPalette } from './palette'

function block(r: number, g: number, b: number, n: number): number[] {
  return Array.from({ length: n }, () => [r, g, b, 255]).flat()
}

test('recovers dominant colors from synthetic pixels', () => {
  const pixels = new Uint8ClampedArray([
    ...block(200, 40, 30, 600),
    ...block(20, 30, 40, 300),
    ...block(240, 230, 210, 100),
  ])
  const palette = kmeansPalette(pixels, 3)
  expect(palette).toHaveLength(3)
  expect(palette[0]).toMatch(/^#[0-9a-f]{6}$/)
  const [r] = palette
  const red = parseInt(r.slice(1, 3), 16)
  expect(red).toBeGreaterThan(150)
})

test('deterministic across calls', () => {
  const pixels = new Uint8ClampedArray(block(10, 200, 100, 500).concat(block(90, 10, 200, 500)))
  expect(kmeansPalette(pixels, 4)).toEqual(kmeansPalette(pixels, 4))
})

test('handles fewer distinct colors than k', () => {
  const pixels = new Uint8ClampedArray(block(50, 50, 50, 64))
  const palette = kmeansPalette(pixels, 5)
  expect(palette).toHaveLength(5)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- run src/lib/growth/palette.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `palette.ts`**

```ts
// web/src/lib/growth/palette.ts
const hex = (v: number) => Math.round(v).toString(16).padStart(2, '0')

export function kmeansPalette(pixels: Uint8ClampedArray, k = 5): string[] {
  const points: Array<[number, number, number]> = []
  for (let i = 0; i + 3 < pixels.length; i += 16) {
    if (pixels[i + 3] < 128) continue
    points.push([pixels[i], pixels[i + 1], pixels[i + 2]])
  }
  if (!points.length) points.push([0, 0, 0])
  // Deterministic init: evenly spaced samples.
  let centroids = Array.from({ length: k }, (_, i) => {
    const p = points[Math.floor((i * points.length) / k)]
    return [p[0], p[1], p[2]] as [number, number, number]
  })
  const assignment = new Array<number>(points.length).fill(0)
  for (let iter = 0; iter < 10; iter++) {
    for (let p = 0; p < points.length; p++) {
      let best = 0
      let bestDist = Infinity
      for (let c = 0; c < k; c++) {
        const dr = points[p][0] - centroids[c][0]
        const dg = points[p][1] - centroids[c][1]
        const db = points[p][2] - centroids[c][2]
        const d = dr * dr + dg * dg + db * db
        if (d < bestDist) { bestDist = d; best = c }
      }
      assignment[p] = best
    }
    const sums = Array.from({ length: k }, () => [0, 0, 0, 0])
    for (let p = 0; p < points.length; p++) {
      const s = sums[assignment[p]]
      s[0] += points[p][0]; s[1] += points[p][1]; s[2] += points[p][2]; s[3]++
    }
    centroids = sums.map((s, c) =>
      s[3] ? ([s[0] / s[3], s[1] / s[3], s[2] / s[3]] as [number, number, number]) : centroids[c],
    )
  }
  const sizes = new Array<number>(k).fill(0)
  for (const a of assignment) sizes[a]++
  return centroids
    .map((c, i) => ({ c, size: sizes[i] }))
    .sort((a, b) => b.size - a.size)
    .map(({ c }) => `#${hex(c[0])}${hex(c[1])}${hex(c[2])}`)
}

export async function paletteFromCovers(urls: string[]): Promise<string[] | null> {
  const pixels: number[] = []
  for (const url of urls.slice(0, 3)) {
    try {
      const img = new Image()
      img.decoding = 'async'
      img.src = url
      await img.decode()
      const canvas = document.createElement('canvas')
      canvas.width = 48
      canvas.height = 48
      const ctx = canvas.getContext('2d')
      if (!ctx) continue
      ctx.drawImage(img, 0, 0, 48, 48)
      pixels.push(...ctx.getImageData(0, 0, 48, 48).data)
    } catch {
      continue
    }
  }
  if (!pixels.length) return null
  return kmeansPalette(new Uint8ClampedArray(pixels), 5)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- run src/lib/growth/palette.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/growth/palette.ts web/src/lib/growth/palette.test.ts
git commit -m "feat(growth): deterministic k-means palette extraction from note covers"
```

### Task 4: Generated topology (`topology.ts`)

**Files:**
- Create: `web/src/lib/growth/topology.ts`
- Test: `web/src/lib/growth/topology.test.ts`

**Interfaces:**
- Consumes: `hashString`, `seededRand`, `SeedParams`, `Constraints` from `./dna`.
- Produces: `type TopologyNode = { x: number; y: number; radius: number; parent: number }`, `generateTopology(seedKey: string, params: SeedParams, constraints: Constraints): TopologyNode[]`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/growth/topology.test.ts
import { expect, test } from 'vitest'
import { DEFAULT_CONSTRAINTS } from './dna'
import { generateTopology } from './topology'

const params = { density: 0.6, motion: 0.3, granularity: 0.5, asymmetry: 0.6 }

test('deterministic for a given seed key', () => {
  expect(generateTopology('th-1', params, DEFAULT_CONSTRAINTS))
    .toEqual(generateTopology('th-1', params, DEFAULT_CONSTRAINTS))
})

test('different keys give different shapes', () => {
  const a = generateTopology('th-1', params, DEFAULT_CONSTRAINTS)
  const b = generateTopology('th-2', params, DEFAULT_CONSTRAINTS)
  expect(a).not.toEqual(b)
})

test('all nodes in frame, radii sane, parents valid', () => {
  const nodes = generateTopology('th-3', params, DEFAULT_CONSTRAINTS)
  expect(nodes.length).toBeGreaterThan(6)
  for (const [i, n] of nodes.entries()) {
    expect(n.x).toBeGreaterThan(0.05)
    expect(n.x).toBeLessThan(0.95)
    expect(n.y).toBeGreaterThan(0.05)
    expect(n.y).toBeLessThan(0.95)
    expect(n.radius).toBeGreaterThan(0.015)
    expect(n.radius).toBeLessThan(0.2)
    expect(n.parent).toBeLessThan(i)
  }
})

test('silhouette is asymmetric: centroid offset from center', () => {
  const nodes = generateTopology('th-4', { ...params, asymmetry: 0.9 }, DEFAULT_CONSTRAINTS)
  const cx = nodes.reduce((s, n) => s + n.x, 0) / nodes.length
  const cy = nodes.reduce((s, n) => s + n.y, 0) / nodes.length
  expect(Math.hypot(cx - 0.5, cy - 0.5)).toBeGreaterThan(0.03)
})

test('density raises node count', () => {
  const sparse = generateTopology('th-5', { ...params, density: 0.2 }, DEFAULT_CONSTRAINTS)
  const dense = generateTopology('th-5', { ...params, density: 0.95 }, DEFAULT_CONSTRAINTS)
  expect(dense.length).toBeGreaterThan(sparse.length)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- run src/lib/growth/topology.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `topology.ts`**

```ts
// web/src/lib/growth/topology.ts
import { hashString, seededRand, type Constraints, type SeedParams } from './dna'

export type TopologyNode = { x: number; y: number; radius: number; parent: number }

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

export function generateTopology(
  seedKey: string,
  params: SeedParams,
  constraints: Constraints,
): TopologyNode[] {
  const h = hashString(seedKey)
  const rand = (salt: number) => seededRand(h, salt)
  const nodes: TopologyNode[] = []
  // Off-center trunk root: asymmetry displaces the whole organism.
  const drift = 0.06 + params.asymmetry * 0.12
  const rootAngle = rand(1) * Math.PI * 2
  const root: TopologyNode = {
    x: clamp(0.5 + Math.cos(rootAngle) * drift, 0.15, 0.85),
    y: clamp(0.5 + Math.sin(rootAngle) * drift, 0.15, 0.85),
    radius: 0.11 + params.density * 0.05,
    parent: -1,
  }
  nodes.push(root)
  const maxDepth = 4
  const curvature = Math.max(constraints.curvature_min, 0.25 + params.asymmetry * 0.4)

  const branch = (parentIndex: number, angle: number, radius: number, depth: number, salt: number) => {
    if (depth > maxDepth || radius < 0.028 || nodes.length > 42) return
    const parent = nodes[parentIndex]
    const childCount = 1 + Math.floor(rand(salt) * (1 + params.density * 2.2))
    for (let c = 0; c < childCount; c++) {
      const s = salt * 7 + c * 13 + depth * 29
      // Asymmetric spread: one side bends persistently (curvature), the other jitters.
      const side = c % 2 === 0 ? 1 : -1
      const bend = side * curvature * (0.5 + rand(s + 1) * 0.8)
      const childAngle = angle + bend + (rand(s + 2) - 0.5) * 0.7
      const reach = radius * (1.5 + rand(s + 3) * 1.3)
      const child: TopologyNode = {
        x: clamp(parent.x + Math.cos(childAngle) * reach, 0.08, 0.92),
        y: clamp(parent.y + Math.sin(childAngle) * reach, 0.08, 0.92),
        radius: radius * (0.55 + rand(s + 4) * 0.25),
        parent: parentIndex,
      }
      nodes.push(child)
      branch(nodes.length - 1, childAngle, child.radius, depth + 1, s + 5)
    }
  }

  const trunkCount = 2 + Math.floor(rand(2) * 2 + params.density * 1.5)
  for (let t = 0; t < trunkCount; t++) {
    // Trunks cluster toward one hemisphere instead of radiating evenly.
    const hemisphere = rootAngle + Math.PI * (0.35 + params.asymmetry * 0.5)
    const angle = hemisphere + (t / trunkCount - 0.5) * Math.PI * (1.6 - params.asymmetry * 0.7)
    branch(0, angle, root.radius * (0.62 + rand(40 + t) * 0.2), 1, 50 + t * 17)
  }
  return nodes
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- run src/lib/growth/topology.test.ts`
Expected: PASS (5 tests). If the asymmetry or density assertions fail, tune `drift`, `curvature`, or `childCount` factors — the invariants under test are the contract, the constants are free.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/growth/topology.ts web/src/lib/growth/topology.test.ts
git commit -m "feat(growth): seeded asymmetric branch topology replaces hardcoded nodes"
```

### Task 5: Evidence events (`events.ts`)

**Files:**
- Create: `web/src/lib/growth/events.ts`
- Test: `web/src/lib/growth/events.test.ts`

**Interfaces:**
- Produces: `type LibraryItem = { stem: string; title: string; url: string | null; tags: string[]; date: string | null; added: string; thumbnail: string | null; source: string }`, `joinEvidence(evidenceIds: string[], items: LibraryItem[]): LibraryItem[]` (chronological by `date ?? added`), `dominantTags(items: LibraryItem[], n?: number): string[]`, `classifyEvent(noteTags: string[], dominant: string[]): 'related' | 'novel'`, `tagCountsOf(items: LibraryItem[]): Record<string, number>`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/growth/events.test.ts
import { expect, test } from 'vitest'
import { classifyEvent, dominantTags, joinEvidence, tagCountsOf, type LibraryItem } from './events'

const item = (stem: string, tags: string[], date: string): LibraryItem => ({
  stem, title: stem, url: null, tags, date, added: date, thumbnail: null, source: 'instagram',
})

const items = [
  item('b-2026-05-01-xyz', ['ai', 'cool-vis'], '2026-05-01'),
  item('a-2026-03-01-abc', ['creative-coding', 'cool-vis'], '2026-03-01'),
  item('c-2026-06-01-def', ['fitness'], '2026-06-01'),
]

test('joins chroma-style evidence ids to library stems, chronologically', () => {
  const joined = joinEvidence(
    ['note_sources_instagram_b-2026-05-01-xyz', 'note_sources_instagram_a-2026-03-01-abc'],
    items,
  )
  expect(joined.map((i) => i.stem)).toEqual(['a-2026-03-01-abc', 'b-2026-05-01-xyz'])
})

test('unmatched evidence ids are dropped', () => {
  expect(joinEvidence(['note_sources_youtube_missing'], items)).toEqual([])
})

test('dominant tags rank by frequency', () => {
  expect(dominantTags(items, 2)[0]).toBe('cool-vis')
})

test('classification: tag overlap with dominants means related', () => {
  const dom = ['cool-vis', 'creative-coding']
  expect(classifyEvent(['cool-vis', 'shaders'], dom)).toBe('related')
  expect(classifyEvent(['fitness'], dom)).toBe('novel')
  expect(classifyEvent([], dom)).toBe('novel')
})

test('tag counts accumulate across items', () => {
  expect(tagCountsOf(items)['cool-vis']).toBe(2)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- run src/lib/growth/events.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `events.ts`**

```ts
// web/src/lib/growth/events.ts
export type LibraryItem = {
  stem: string
  title: string
  url: string | null
  tags: string[]
  date: string | null
  added: string
  thumbnail: string | null
  source: string
}

export function joinEvidence(evidenceIds: string[], items: LibraryItem[]): LibraryItem[] {
  // Chroma ids come in two schemes (ingest pipeline and vault reindexer); both
  // end with the note's file stem, and stems are globally unique in the vault.
  const matched = new Map<string, LibraryItem>()
  for (const id of evidenceIds) {
    for (const it of items) {
      if (id.endsWith(it.stem)) {
        matched.set(it.stem, it)
        break
      }
    }
  }
  return [...matched.values()].sort((a, b) =>
    (a.date ?? a.added).localeCompare(b.date ?? b.added),
  )
}

export function tagCountsOf(items: LibraryItem[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const it of items) {
    for (const t of it.tags) counts[t] = (counts[t] ?? 0) + 1
  }
  return counts
}

export function dominantTags(items: LibraryItem[], n = 6): string[] {
  return Object.entries(tagCountsOf(items))
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([t]) => t)
}

export function classifyEvent(noteTags: string[], dominant: string[]): 'related' | 'novel' {
  return noteTags.some((t) => dominant.includes(t)) ? 'related' : 'novel'
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- run src/lib/growth/events.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/growth/events.ts web/src/lib/growth/events.test.ts
git commit -m "feat(growth): evidence-to-library join and derived related/novel classification"
```

### Task 6: Philosophy parsing (`philosophy.ts`)

**Files:**
- Create: `web/src/lib/growth/philosophy.ts`
- Test: `web/src/lib/growth/philosophy.test.ts`

**Interfaces:**
- Consumes: `Constraints`, `DEFAULT_CONSTRAINTS` from `./dna`.
- Produces: `parsePhilosophy(text: string): Constraints` — reads numeric keys from YAML frontmatter, falls back to defaults per-key; missing/malformed frontmatter returns `DEFAULT_CONSTRAINTS`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/growth/philosophy.test.ts
import { expect, test } from 'vitest'
import { DEFAULT_CONSTRAINTS } from './dna'
import { parsePhilosophy } from './philosophy'

test('reads constraint numbers from frontmatter', () => {
  const text = `---\nglow_max: 0.2\nasymmetry_min: 0.6\ncurvature_min: 0.4\nsaturation_max: 0.7\n---\n\nNever reads as a graph.`
  expect(parsePhilosophy(text)).toEqual({
    glow_max: 0.2, asymmetry_min: 0.6, curvature_min: 0.4, saturation_max: 0.7,
  })
})

test('missing keys fall back per-key', () => {
  const text = `---\nglow_max: 0.1\n---\nprose`
  const c = parsePhilosophy(text)
  expect(c.glow_max).toBe(0.1)
  expect(c.asymmetry_min).toBe(DEFAULT_CONSTRAINTS.asymmetry_min)
})

test('no frontmatter returns defaults', () => {
  expect(parsePhilosophy('just prose')).toEqual(DEFAULT_CONSTRAINTS)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- run src/lib/growth/philosophy.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `philosophy.ts`**

```ts
// web/src/lib/growth/philosophy.ts
import { DEFAULT_CONSTRAINTS, type Constraints } from './dna'

export function parsePhilosophy(text: string): Constraints {
  const m = /^---\n([\s\S]*?)\n---/.exec(text.trim())
  const out = { ...DEFAULT_CONSTRAINTS }
  if (!m) return out
  for (const key of Object.keys(out) as Array<keyof Constraints>) {
    const line = new RegExp(`^${key}:\\s*([0-9.]+)\\s*$`, 'm').exec(m[1])
    if (line) {
      const v = Number(line[1])
      if (Number.isFinite(v)) out[key] = v
    }
  }
  return out
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- run src/lib/growth/philosophy.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/growth/philosophy.ts web/src/lib/growth/philosophy.test.ts
git commit -m "feat(growth): constraint parsing from growth philosophy frontmatter"
```

### Task 7: Philosophy endpoints (server)

**Files:**
- Modify: `ytk/ui/server.py` (after the grove-buckets endpoints, ~line 352)

**Interfaces:**
- Produces: `GET /api/growth/philosophy` → `{"text": str, "path": str}` (creates a default file on first call), `PUT /api/growth/philosophy` body `{"text": str}` → `{"saved": true}`. Follows the grove-buckets verbatim-roundtrip pattern.

- [ ] **Step 1: Add endpoints to `server.py`**

```python
_GROWTH_PHILOSOPHY_PATH = Path.home() / ".ytk" / "growth_philosophy.md"

_GROWTH_PHILOSOPHY_DEFAULT = """---
glow_max: 0.35
asymmetry_min: 0.45
curvature_min: 0.3
saturation_max: 0.8
---

# Growth philosophy

Hard constraints live in the frontmatter above and are enforced by the
workbench. The prose below is for you (and a future LLM steering layer).

- Never reads as a graph: no hub-and-spoke, no straight radial spokes.
- Organic before geometric; asymmetric before balanced.
- Color belongs to the content: palettes come from the notes themselves.
"""


@app.get("/api/growth/philosophy")
async def growth_philosophy_get():
    if not _GROWTH_PHILOSOPHY_PATH.exists():
        _GROWTH_PHILOSOPHY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GROWTH_PHILOSOPHY_PATH.write_text(_GROWTH_PHILOSOPHY_DEFAULT, encoding="utf-8")
    return {"text": _GROWTH_PHILOSOPHY_PATH.read_text(encoding="utf-8"),
            "path": str(_GROWTH_PHILOSOPHY_PATH)}


@app.put("/api/growth/philosophy")
async def growth_philosophy_put(request: Request):
    """Save verbatim — hand-authored markdown, same contract as grove-buckets."""
    raw = (await request.json()).get("text", "")
    if not raw.strip():
        raise HTTPException(status_code=422, detail="empty philosophy")
    _GROWTH_PHILOSOPHY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GROWTH_PHILOSOPHY_PATH.write_text(raw, encoding="utf-8")
    return {"saved": True}
```

- [ ] **Step 2: Verify import and route registration**

Run: `uv run python -c "from ytk.ui import server; routes=[r.path for r in server.app.routes]; assert '/api/growth/philosophy' in routes; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add ytk/ui/server.py
git commit -m "feat(hub): growth philosophy endpoints following grove-buckets pattern"
```

### Task 8: DNA-parameterized shaders (`shaders.ts`)

**Files:**
- Modify: `web/src/lib/growth/shaders.ts` (full rewrite of both fragments; keep `growthVertex`)

**Interfaces:**
- Consumes: uniform values set by `scene.ts`.
- Produces: `growthVertex` (unchanged), `growthUpdateFragment` (adds `uOpsA: vec3` = DEEPEN/BUD/LACE, `uOpsB: vec3` = STIPPLE/BLEED/MEMBRANE, `uHue: vec3` per-event stroke color), `growthRenderFragment` (adds `uPalette: vec3[5]`, `uOpsA`, `uOpsB`, `uGlowMax: float`, `uAbstraction: float`).

State texture channels stay: r = body, g = vessel, b = activity, a = settled. A third texture channel pair is NOT added; per-event hue tints the activity contribution at render time via the palette, so state stays 4-channel and old states remain loadable.

- [ ] **Step 1: Rewrite the update fragment**

Operator hooks, applied to the existing injection math (keep `hash21`, `noise`, `segmentDistance` helpers as-is):

```glsl
// new uniforms
uniform vec3 uOpsA; // DEEPEN, BUD, LACE
uniform vec3 uOpsB; // STIPPLE, BLEED, MEMBRANE

// inside the uActive block, replacing the fixed injections:
float pathWidth = mix(uRadius * 0.24, uRadius * 0.48, eased) * (0.6 + 0.8 * uOpsA.x);
float lobeScale = organicRadius * (0.7 + 0.6 * uOpsA.y);
float bodyInjection = max(
  smoothstep(pathWidth, pathWidth * 0.2, capsule) * (0.5 + 0.5 * uOpsA.x),
  smoothstep(lobeScale, lobeScale * 0.14, lobe) * (0.5 + 0.5 * uOpsA.y)
);
float veinInjection = max(
  smoothstep(uRadius * 0.11, uRadius * 0.018, capsule),
  smoothstep(uRadius * 0.17, uRadius * 0.025, lobe) * (0.35 + 0.65 * fine)
) * (0.35 + 0.65 * uOpsA.z);
float grainAmp = mix(0.82, 1.0 - 0.36 * uOpsB.x, 0.5); // STIPPLE roughens radius
body = max(body, bodyInjection * (0.72 + grain * 0.28 * (0.5 + uOpsB.x)));
vessel = max(vessel, veinInjection);
activity = max(activity, bodyInjection * (0.72 + 0.28 * eased));
settled = min(settled, 1.0 - bodyInjection * 0.85);
// BLEED controls how far the touched neighborhood relaxes
float bleed = 0.015 + 0.06 * uOpsB.y;
body += (average.r - body) * bleed * local;
vessel += (average.g - vessel) * (bleed * 0.4) * local;
```

- [ ] **Step 2: Rewrite the render fragment**

Contract (write the full shader; structure below is normative):

```glsl
uniform vec3 uPalette[5]; // [0] deep field, [1] mid tissue, [2] high tissue, [3] vessel, [4] membrane
uniform vec3 uOpsA;
uniform vec3 uOpsB;
uniform float uGlowMax;
uniform float uAbstraction;
// keep uState, uTexel, uTime, uAspect, uPulse and voronoi/hash helpers

void main() {
  vec4 s = texture2D(uState, vUv);
  float body = s.r; float vessel = s.g; float activity = s.b; float settled = s.a;
  // figurative pass
  vec3 col = uPalette[0] * 0.55;                               // field
  float tissue = smoothstep(0.12, 0.75, body);
  col = mix(col, uPalette[1], tissue);
  col = mix(col, uPalette[2], smoothstep(0.55, 0.95, body) * 0.8);
  float voro = voronoiEdge(vUv * (26.0 + 30.0 * uOpsB.x));     // STIPPLE scales cell grain
  col *= 1.0 - voro * 0.14 * tissue;
  col = mix(col, uPalette[3], smoothstep(0.25, 0.9, vessel) * (0.4 + 0.6 * uOpsA.z));
  float edge = smoothstep(0.02, 0.3, body) * (1.0 - smoothstep(0.3, 0.55, body));
  col = mix(col, uPalette[4], edge * (0.3 + 0.7 * uOpsB.z));   // MEMBRANE holds the rim
  float stip = step(0.985 - uOpsB.x * 0.012, hash21(floor(vUv * 340.0))) * (1.0 - tissue);
  col += uPalette[4] * stip * 0.35;                            // peripheral stipple
  col += uPalette[3] * activity * min(uGlowMax, uGlowMax * (0.6 + uPulse)); // clamped glow
  // abstraction pass: posterized operator field, palette bands only
  float bands = floor(body * 5.0) / 5.0;
  vec3 flat = uPalette[int(clamp(bands * 5.0, 0.0, 4.0))];
  col = mix(col, flat, uAbstraction);
  gl_FragColor = vec4(col, 1.0);
}
```

Note: GLSL1 disallows dynamic array index by non-constant int in some drivers — implement the `flat` lookup as a chain of `mix(...)`/`step(...)` selections instead of `uPalette[int(...)]`.

- [ ] **Step 3: Verify compilation via build**

Run: `cd web && npm run build`
Expected: build passes (shader strings are not compiled at build time; runtime check happens in Task 10's screenshot step — any GLSL error shows as a black canvas plus console error).

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/growth/shaders.ts
git commit -m "feat(growth): operator- and palette-parameterized growth shaders"
```

### Task 9: Workbench engine (`scene.ts`)

**Files:**
- Rewrite: `web/src/lib/growth/scene.ts`
- Test: `web/src/lib/growth/layout.test.ts` (pure region math only)
- Create: `web/src/lib/growth/layout.ts`

**Interfaces:**
- Consumes: `SeedDNA`, `Constraints` (`./dna`); `TopologyNode`, `generateTopology` (`./topology`); shader exports (`./shaders`); `LibraryItem`, `classifyEvent`, `dominantTags` (`./events`).
- Produces:
  - `layout.ts`: `type Region = { x: number; y: number; w: number; h: number }`, `workbenchRegions(width: number, height: number): { stage: Region; mutations: Region[] }` — stage takes the left ~72%, four mutation tiles stack on the right column with 8px gutters.
  - `scene.ts`: `type EventInput = { stem: string; title: string; kind: 'related' | 'novel' }`, `type OrganismSpec = { dna: SeedDNA; events: EventInput[]; replayFrom?: number }`, `mountWorkbench(canvas: HTMLCanvasElement, onStatus: (s: WorkbenchStatus) => void): WorkbenchHandle` with `WorkbenchHandle = { setOrganism(spec: OrganismSpec): void; setMutations(dnas: SeedDNA[]): void; setAbstraction(v: number): void; setPaused(p: boolean): void; injectDebug(kind: 'related' | 'novel'): void; reset(): void; snapshot(): string; replayPosition(): number; destroy(): void }` and `WorkbenchStatus = { themeId: string | null; replayed: number; total: number; phase: 'resting' | 'growing' | 'paused'; message: string }`.

Engine rules (adapting the existing single-organism engine):

- One `WebGLRenderer`, one update material, one display material. Five state-texture ping-pong pairs: stage at 384, mutation tiles at 192.
- Scissor + viewport per region each frame; mutation tiles render the SAME topology and event history as the stage but with their mutated DNA uniforms — they are alternate readings of the same organism, so their state pairs re-simulate the shared event queue with their own operator uniforms.
- `setOrganism` seeds all five pairs from `generateTopology(dna.themeId, dna.params, constraints)` via the existing `makeSeedTexture` path (keep that function, it takes nodes), then queues `events` from `replayFrom`, one growth event per ~1.4s. Event target selection reuses the demo's `eventFor` logic: related events attach to random interior nodes, novel events extend the perimeter node — but the node list comes from the generated topology.
- `snapshot()` returns `canvas.toDataURL('image/png')` cropped server-side by the caller (gallery thumbs draw the stage region into a small 2D canvas).
- `injectDebug` pushes a synthetic event labeled `debug`.
- Keep the localized-relaxation invariant comment and behavior from the old update loop.

- [ ] **Step 1: Write the failing layout test**

```ts
// web/src/lib/growth/layout.test.ts
import { expect, test } from 'vitest'
import { workbenchRegions } from './layout'

test('stage dominates, four tiles fill the right column', () => {
  const { stage, mutations } = workbenchRegions(1200, 800)
  expect(mutations).toHaveLength(4)
  expect(stage.w).toBeGreaterThan(700)
  expect(stage.h).toBe(800)
  for (const m of mutations) {
    expect(m.x).toBeGreaterThanOrEqual(stage.w)
    expect(m.w).toBeGreaterThan(100)
  }
  const ys = mutations.map((m) => m.y)
  expect(new Set(ys).size).toBe(4)
})

test('regions never overlap or exceed bounds', () => {
  const { stage, mutations } = workbenchRegions(900, 620)
  for (const m of mutations) {
    expect(m.x + m.w).toBeLessThanOrEqual(900)
    expect(m.y + m.h).toBeLessThanOrEqual(620)
    expect(m.x).toBeGreaterThanOrEqual(stage.x + stage.w)
  }
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- run src/lib/growth/layout.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `layout.ts`**

```ts
// web/src/lib/growth/layout.ts
export type Region = { x: number; y: number; w: number; h: number }

export function workbenchRegions(width: number, height: number): { stage: Region; mutations: Region[] } {
  const gutter = 8
  const stageW = Math.floor(width * 0.72)
  const colX = stageW + gutter
  const colW = width - colX
  const tileH = Math.floor((height - gutter * 3) / 4)
  const mutations = Array.from({ length: 4 }, (_, i) => ({
    x: colX,
    y: i * (tileH + gutter),
    w: colW,
    h: tileH,
  }))
  return { stage: { x: 0, y: 0, w: stageW, h: height }, mutations }
}
```

- [ ] **Step 4: Run layout test to verify it passes**

Run: `cd web && npm test -- run src/lib/growth/layout.test.ts`
Expected: PASS. (Adjust the 0.72 split only if the assertions force it; they should not.)

- [ ] **Step 5: Rewrite `scene.ts` to the WorkbenchHandle contract**

Port from the existing file: `makeSeedTexture` (now takes generated nodes), the ping-pong `simulate` pattern, `eventFor` (parameterized by node list), the render loop. New: five texture pairs, region scissor rendering, per-region uniform swap (each mutation tile sets its own `uOpsA/uOpsB/uPalette` before its draw call), event replay timer, `snapshot`, `replayPosition`. Uniform values for `vec3` palettes convert hex via `new Color(hex)`.

- [ ] **Step 6: Verify types compile**

Run: `cd web && npm run build`
Expected: PASS (growth.tsx still imports the old API and will break — acceptable only if Task 10 lands in the same push; to keep every commit green, update `growth.tsx` minimally in this commit to mount the new engine with empty data, full UI arrives in Task 10).

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/growth/scene.ts web/src/lib/growth/layout.ts web/src/lib/growth/layout.test.ts web/src/routes/growth.tsx
git commit -m "feat(growth): multi-region workbench engine with per-mutation DNA uniforms"
```

### Task 10: Workbench UI (`growth.tsx` + `growth.css`)

**Files:**
- Rewrite: `web/src/routes/growth.tsx`
- Rewrite: `web/src/routes/growth.css`

**Interfaces:**
- Consumes: everything above, plus `GET /api/profile`, `GET /api/library?n=800`, `GET /api/growth/philosophy`, `/api/cover?u=`.
- Produces: the `/growth` route. localStorage keys `growth:adopted:<themeId>` (JSON SeedDNA) and `growth:replay:<themeId>` (number).

Page assembly logic (implement in `growth.tsx` with TanStack `useQuery`-style fetches matching the repo's existing data-fetch pattern in `profile.tsx`):

1. Fetch profile + library + philosophy in parallel. `constraints = parsePhilosophy(philosophy.text)`.
2. Per theme: `evidence = joinEvidence(theme.evidence_ids, library.items)`; `tagCounts = tagCountsOf(evidence)`; `palette = await paletteFromCovers(evidence.filter(e => e.url).slice(-3).map(e => '/api/cover?u=' + encodeURIComponent(e.url)))`; `dna = localStorage adopted ?? deriveDNA({...theme fields, tagCounts, palette}, constraints)`.
3. Organisms list = themes + `RELIQUARY` preset (no events, empty evidence).
4. Selecting an organism: `setOrganism({ dna, events, replayFrom: saved })`; `setMutations([1,2,3,4].map(s => mutateDNA(dna, s + mutationEpoch * 4, constraints)))`.
5. `adopt(i)`: write mutation `i`'s DNA to localStorage, make it the stage DNA, regenerate the mutation row from it.
6. `new mutation set`: increment `mutationEpoch` (state), regenerate row.
7. `random dna seed`: `mutateDNA(dna, hashString(String(Date.now())) % 9973, constraints)` on the stage only — exploration, not persisted until adopted.
8. Persist `replayPosition()` to localStorage on an interval and on unmount.
9. Metadata chips panel: theme label, note count, replay position, tag chips (top 8), palette swatches, operator bars (six rows, width = weight).
10. Debug drawer (collapsed by default): `+ related`, `+ novel`, `reset`, abstraction slider (0..1 → `setAbstraction`), pause.
11. Gallery strip: one thumb per organism — 2D canvas snapshots refreshed on selection change and every 10 replayed events; click selects.

Layout (CSS grid): gallery strip top (64px), stage+mutations canvas center (the single WebGL canvas fills this cell), chips panel right-bottom overlay, debug drawer bottom-left. Dark field `#050607`, monospace labels, chip styling consistent with the hub's existing `fchip` class.

- [ ] **Step 1: Implement the page and styles per the assembly logic above**

- [ ] **Step 2: Full test suite and build**

Run: `cd web && npm test -- run && npm run build`
Expected: all suites PASS, build green.

- [ ] **Step 3: Live smoke test against real data**

Start the dev server (vite proxies `/api` per existing `vp dev` config) or use the built bundle through the hub. Verify with the webapp-testing skill (headless): page loads, organisms appear, canvas is non-black, mutation tiles differ from the stage, adopt persists across reload.

- [ ] **Step 4: Commit**

```bash
git add web/src/routes/growth.tsx web/src/routes/growth.css
git commit -m "feat(growth): seed workbench UI — gallery, stage, mutation picker, philosophy clamps"
```

### Task 11: Deploy to the hub and verify

**Files:**
- Modify: `web/dist/*` (build output), commit separately.

- [ ] **Step 1: Build and commit dist**

```bash
cd web && npm run build && cd ..
git add web/dist web/src/routeTree.gen.ts
git commit -m "build(web): growth seed workbench bundle"
```

- [ ] **Step 2: Reinstall and restart the hub — ONLY if idle**

```bash
uv tool install --reinstall .
curl -s localhost:6969/api/ingest/status   # verify no ingest job running
launchctl kickstart -k gui/501/com.ytk.hub # reinstall does NOT restart the hub
sleep 3 && curl -s -o /dev/null -w '%{http_code}' localhost:6969/growth
```

Expected: `200`. If an ingest job is running, wait and poll; do not kill it.

- [ ] **Step 3: Headless screenshot of /growth for the morning report**

Use the webapp-testing skill against `localhost:6969/growth`; save screenshots (default state + a mutation adopted) to the scratchpad, attach via SendUserFile in the wrap-up message.

- [ ] **Step 4: Push and update issue #80**

```bash
git push
gh issue comment 80 --repo pablomoli/ytk --body "<direction-change comment: metadata-driven seeds + mutation picker; reliquary demoted to one preset; spec + plan paths; what shipped; how to try it>"
```

### Task 12: Session wrap (per CLAUDE.md, non-negotiable)

- [ ] Write the next session brief through `vault_write` at `second-brain/projects/ytk/session-NNN-brief.md`; update `wiki/index.md`. Session briefs remain vault-only.
- [ ] `vault_remember` the decisions (moodboard steering, taste-at-selection-time, philosophy clamps).
- [ ] Verify `git status` clean (scratch files excepted), all commits pushed.

## Self-Review Notes

- Spec coverage: concept unit (T10 organisms per theme), SeedDNA derivation (T2), palette (T3), topology (T4), events + classification (T5), philosophy file + endpoints + clamps (T6, T7), operator shaders + abstraction slider (T8), workbench zones + mutation picker + localStorage persistence (T9, T10), reliquary preset (T2, T10), stability rule (localStorage keyed on themeId, T10), testing section (every pure module has a suite; build + headless screenshots). Out-of-scope items from the spec are not planned. No gaps found.
- Type consistency: `SeedDNA`/`Constraints` defined once in T2 and imported everywhere; `LibraryItem` defined in T5 and consumed in T9/T10; `WorkbenchHandle` names in T9 match T10 usage (`setOrganism`, `setMutations`, `setAbstraction`, `injectDebug`, `snapshot`, `replayPosition`).
- Placeholders: Task 9 Step 5 and Task 10 Step 1 describe ports/assembly rather than full listings; the normative contracts (types, behaviors, invariants) are complete and the executor holds the old file content in context. Accepted for single-session inline execution.
