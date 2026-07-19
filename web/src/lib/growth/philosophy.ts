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
