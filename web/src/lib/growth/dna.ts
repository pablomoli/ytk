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

export const OPERATORS: OperatorName[] = ['DEEPEN', 'BUD', 'LACE', 'STIPPLE', 'BLEED', 'MEMBRANE']

// Tag families → operator emphasis, weighted by the theme's real tag counts.
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
        acc[op as OperatorName] += w * count
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
