// PROTOTYPE (grove workshop) - throwaway until a look wins a real spec.
// Faithful port of Marius Ballot's procedural data-tree pipeline
// (sources/youtube/procedural-3d-data-trees-in-three-js-a-shader-geometry-breakdown.md):
// BFS node tree -> chain decomposition -> centripetal Catmull-Rom -> hand-built
// TNB frames -> weight-sized vertex rings -> hand-stitched quad index buffer,
// with a backpropagated 0-1 depth attribute driving growth in the shaders.
import { CatmullRomCurve3, Vector3 } from 'three'

export type GroveParams = {
  seed: number
  trees: number
  initialChildren: number // 1-4, sphere-distributed around the root
  branchChance: number // probability a node forks into two children
  stepScale: number // world distance per BFS step
  noise: number // noise vector amplitude added to each step
  reach: number // distance-from-root threshold that stops growth
  upBias: number // 0-1 pull of every step toward +y
  girth: number // trunk radius at the root
  girthDecay: number // weight multiplier per generation
  ringSegments: number // vertices per tube ring
  growSeconds: number
  leafDensity: number // points per leaf site (foliage look)
  leafSpread: number // world radius of a leaf cluster
  leafSize: number // point size multiplier for leaves
}

export const DEFAULT_PARAMS: GroveParams = { seed: 7, trees: 1, initialChildren: 1, branchChance: 0.5, stepScale: 0.32, noise: 0.16, reach: 4, upBias: 0.55, girth: 0.12, girthDecay: 0.92, ringSegments: 7, growSeconds: 5, leafDensity: 60, leafSpread: 0.4, leafSize: 2.2 }

type TreeNode = { position: Vector3; weight: number; pathLength: number; children: TreeNode[] }

// mulberry32 - seeded so "regenerate" is reproducible from the seed knob
export function rng(seed: number): () => number {
  let a = seed >>> 0
  return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}

const randomUnit = (rand: () => number): Vector3 => { const z = rand() * 2 - 1; const a = rand() * Math.PI * 2; const r = Math.sqrt(1 - z * z); return new Vector3(r * Math.cos(a), z, r * Math.sin(a)) }

// Complexity budget: BFS growth is exponential in branchChance and
// reach/step, so a hard node cap keeps every knob combination interactive
// (a hung main thread is a workshop failure, not a user error). The scene
// shares the budget across trees via maxNodes.
const MAX_NODES = 2200

export function generateTree(params: GroveParams, rand: () => number, origin: Vector3, maxNodes: number = MAX_NODES): TreeNode {
  const root: TreeNode = { position: origin.clone(), weight: 1, pathLength: 0, children: [] }
  const up = new Vector3(0, 1, 0)
  const queue: TreeNode[] = []
  let nodes = 1
  // Initial 1-4 children sphere-distributed around the root, biased upward so
  // the sapling leaves the ground (Ballot's sphere distribution, our bias).
  for (let i = 0; i < params.initialChildren; i++) {
    const direction = randomUnit(rand).multiplyScalar(1 - params.upBias).add(up.clone().multiplyScalar(params.upBias + rand() * 0.4)).normalize()
    const child: TreeNode = { position: origin.clone().add(direction.multiplyScalar(params.stepScale * (0.7 + rand() * 0.6))), weight: params.girthDecay, pathLength: params.stepScale, children: [] }
    root.children.push(child)
    queue.push(child)
  }
  // BFS: each node extends along its root-to-node direction, scaled by a
  // random scalar, plus a noise vector; growth stops past the reach threshold.
  while (queue.length) {
    const node = queue.shift()!
    const outward = node.position.clone().sub(origin).normalize()
    const count = rand() < params.branchChance ? 2 : 1
    for (let i = 0; i < count; i++) {
      // fork siblings get a strong lateral kick so branches visibly diverge
      // instead of hugging the shared root-outward direction
      const lateral = i === 0 ? params.noise : params.noise + params.stepScale * 0.8
      const step = outward.clone().multiplyScalar(params.stepScale * (0.6 + rand() * 0.8)).add(randomUnit(rand).multiplyScalar(lateral)).add(up.clone().multiplyScalar(params.upBias * params.stepScale * 0.3))
      const position = node.position.clone().add(step)
      if (position.distanceTo(origin) > params.reach) continue
      if (nodes >= maxNodes) return root
      const child: TreeNode = { position, weight: node.weight * params.girthDecay, pathLength: node.pathLength + step.length(), children: [] }
      node.children.push(child)
      queue.push(child)
      nodes++
    }
  }
  return root
}

// Chains: maximal single-child runs between branch points, each starting at
// its parent branch node so tubes stay connected. Ballot's "segments".
type Chain = { points: Vector3[]; weights: number[]; depths: number[] }

function decompose(root: TreeNode): { chains: Chain[]; tips: Array<{ position: Vector3; depth: number }> } {
  let maxPath = 0
  const walkMax = (n: TreeNode) => { maxPath = Math.max(maxPath, n.pathLength); n.children.forEach(walkMax) }
  walkMax(root)
  const depthOf = (n: TreeNode) => (maxPath > 0 ? n.pathLength / maxPath : 0)
  const chains: Chain[] = []
  const tips: Array<{ position: Vector3; depth: number }> = []
  const walk = (start: TreeNode) => {
    for (const first of start.children) {
      const points = [start.position]
      const weights = [start.weight]
      const depths = [depthOf(start)]
      let node = first
      while (true) {
        points.push(node.position); weights.push(node.weight); depths.push(depthOf(node))
        if (node.children.length !== 1) break
        node = node.children[0]
      }
      chains.push({ points, weights, depths })
      if (node.children.length === 0) tips.push({ position: node.position, depth: depthOf(node) })
      else walk(node)
    }
  }
  walk(root)
  return { chains, tips }
}

export type TreeGeometry = {
  // tube mesh: position = spine point, roff = ring offset from spine, depth 0-1
  position: Float32Array
  roff: Float32Array
  depth: Float32Array
  index: Uint32Array
  // wireframe look: line segment pairs along the smoothed spines
  linePosition: Float32Array
  lineDepth: Float32Array
  // leaf tips (buds / future notes)
  tips: Array<{ position: Vector3; depth: number }>
  // canopy sites: outer-branch spine samples where foliage accumulates,
  // each carrying its branch frame so instanced geometry can orient to the limb
  leafSites: Array<{ position: Vector3; depth: number; tangent: Vector3; normal: Vector3; radius: number }>
}

export function buildTreeGeometry(params: GroveParams, root: TreeNode): TreeGeometry {
  const { chains, tips } = decompose(root)
  const ring = params.ringSegments
  const pos: number[] = []; const off: number[] = []; const dep: number[] = []; const idx: number[] = []
  const lpos: number[] = []; const ldep: number[] = []
  const leafSites: Array<{ position: Vector3; depth: number; tangent: Vector3; normal: Vector3; radius: number }> = []
  for (const chain of chains) {
    if (chain.points.length < 2) continue
    const curve = new CatmullRomCurve3(chain.points, false, 'centripetal')
    // polyline length estimate: curve.getLength() subdivides 200x per chain
    // and was the generation hotspot; control-point distances are plenty
    // accurate for picking a sample count
    let length = 0
    for (let i = 1; i < chain.points.length; i++) length += chain.points[i].distanceTo(chain.points[i - 1])
    const samples = Math.min(72, Math.max(4, Math.round(length / (params.stepScale * 0.22))))
    const spine: Vector3[] = []
    const radii: number[] = []
    const depths: number[] = []
    for (let i = 0; i <= samples; i++) {
      const t = i / samples
      spine.push(curve.getPoint(t))
      const f = t * (chain.points.length - 1)
      const j = Math.min(chain.points.length - 2, Math.floor(f))
      const local = f - j
      radii.push((chain.weights[j] + (chain.weights[j + 1] - chain.weights[j]) * local) * params.girth)
      depths.push(chain.depths[j] + (chain.depths[j + 1] - chain.depths[j]) * local)
    }
    // TNB frames by parallel transport: tangent from neighbors, first normal
    // from a cross with an arbitrary reference, then carried along the spine.
    let normal = new Vector3()
    const base = pos.length / 3
    for (let i = 0; i <= samples; i++) {
      const tangent = spine[Math.min(samples, i + 1)].clone().sub(spine[Math.max(0, i - 1)]).normalize()
      if (i === 0) {
        const ref = Math.abs(tangent.y) < 0.9 ? new Vector3(0, 1, 0) : new Vector3(1, 0, 0)
        normal = new Vector3().crossVectors(tangent, ref).normalize()
      } else {
        normal.sub(tangent.clone().multiplyScalar(normal.dot(tangent))).normalize()
      }
      const binormal = new Vector3().crossVectors(tangent, normal)
      for (let s = 0; s < ring; s++) {
        const a = (s / ring) * Math.PI * 2
        const o = normal.clone().multiplyScalar(Math.cos(a)).add(binormal.clone().multiplyScalar(Math.sin(a))).multiplyScalar(radii[i])
        pos.push(spine[i].x, spine[i].y, spine[i].z)
        off.push(o.x, o.y, o.z)
        dep.push(depths[i])
      }
      if (i > 0) {
        // stitch ring i-1 to ring i as quads = two triangles per segment pair
        const a0 = base + (i - 1) * ring
        const b0 = base + i * ring
        for (let s = 0; s < ring; s++) {
          const s1 = (s + 1) % ring
          idx.push(a0 + s, b0 + s, b0 + s1, a0 + s, b0 + s1, a0 + s1)
        }
      }
      if (i > 0) { lpos.push(spine[i - 1].x, spine[i - 1].y, spine[i - 1].z, spine[i].x, spine[i].y, spine[i].z); ldep.push(depths[i - 1], depths[i]) }
      // canopy accumulates along the outer half of the tree, not just at tips
      if (depths[i] > 0.55 && i % 2 === 0) leafSites.push({ position: spine[i].clone(), depth: depths[i], tangent: tangent.clone(), normal: normal.clone(), radius: radii[i] })
    }
  }
  for (const tip of tips) leafSites.push({ position: tip.position, depth: tip.depth, tangent: new Vector3(0, 1, 0), normal: new Vector3(1, 0, 0), radius: 0.01 })
  return { position: new Float32Array(pos), roff: new Float32Array(off), depth: new Float32Array(dep), index: new Uint32Array(idx), linePosition: new Float32Array(lpos), lineDepth: new Float32Array(ldep), tips, leafSites }
}
