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

  const branch = (
    parentIndex: number,
    angle: number,
    radius: number,
    depth: number,
    salt: number,
  ) => {
    if (depth > maxDepth || radius < 0.028 || nodes.length > 42) return
    const parent = nodes[parentIndex]
    const childCount = 1 + Math.floor(rand(salt) * (1 + params.density * 2.2))
    for (let c = 0; c < childCount; c++) {
      const s = salt * 7 + c * 13 + depth * 29
      // Asymmetric spread: one side bends persistently (curvature), the other jitters.
      const side = c % 2 === 0 ? 1 : -1
      const bend = side * curvature * (0.5 + rand(s + 1) * 0.8)
      const childAngle = angle + bend + (rand(s + 2) - 0.5) * 0.7
      // Short reach keeps child lobes overlapping the parent: one connected
      // mass with an irregular silhouette, never islands joined by lines.
      const reach = radius * (0.95 + rand(s + 3) * 0.65)
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
