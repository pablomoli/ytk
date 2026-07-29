// Garden procedural/data-tree geometry. Structural channels here are measured
// or generation controls; decorative material channels live in shaders.ts.
// Faithful port of Marius Ballot's procedural data-tree pipeline
// (sources/youtube/procedural-3d-data-trees-in-three-js-a-shader-geometry-breakdown.md):
// BFS node tree -> chain decomposition -> centripetal Catmull-Rom -> hand-built
// TNB frames -> weight-sized vertex rings -> hand-stitched quad index buffer,
// with a backpropagated 0-1 depth attribute driving growth in the shaders.
import { CatmullRomCurve3, Vector3 } from "three";

export type GardenParams = {
  seed: number;
  trees: number;
  initialChildren: number; // 1-4, sphere-distributed around the root
  branchChance: number; // probability a node forks into two children
  stepScale: number; // world distance per BFS step
  noise: number; // noise vector amplitude added to each step
  reach: number; // distance-from-root threshold that stops growth
  upBias: number; // 0-1 pull of every step toward +y
  girth: number; // trunk radius at the root
  girthDecay: number; // weight multiplier per generation
  ringSegments: number; // vertices per tube ring
  stiffness: number; // 0-1: how much a branch resists changing direction
  wind: number; // 0-1: branch + leaf sway amplitude
  growSeconds: number;
  leafDensity: number; // points per leaf site (foliage look)
  leafSpread: number; // world radius of a leaf cluster
  leafSize: number; // point size multiplier for leaves
  paletteTravel: number; // decorative root-to-tip palette travel
  paletteMotion: number; // decorative animated palette phase
  paletteStrength: number; // decorative palette contribution
  wireGlow: number; // decorative x-ray core/halo energy
  wirePulse: number; // decorative x-ray traveling pulse
  wireBody: number; // decorative x-ray tube body opacity
};

// Named parameter presets persisted by the garden controls.
export const PRESETS: Record<string, GardenParams> = {
  "bonsai-80163": {
    seed: 80163,
    trees: 1,
    initialChildren: 3,
    branchChance: 0.15,
    stepScale: 0.3,
    noise: 0.6,
    reach: 2.4,
    upBias: 0.75,
    girth: 0.09,
    girthDecay: 0.94,
    ringSegments: 12,
    stiffness: 0.6,
    wind: 0.65,
    growSeconds: 4,
    leafDensity: 24,
    leafSpread: 0.78,
    leafSize: 2.2,
    paletteTravel: 0.75,
    paletteMotion: 0.04,
    paletteStrength: 0.72,
    wireGlow: 0.8,
    wirePulse: 0.28,
    wireBody: 0.12,
  },
};

export const DEFAULT_PARAMS: GardenParams = {
  seed: 7,
  trees: 1,
  initialChildren: 1,
  branchChance: 0.5,
  stepScale: 0.32,
  noise: 0.16,
  reach: 4,
  upBias: 0.55,
  girth: 0.12,
  girthDecay: 0.92,
  ringSegments: 7,
  stiffness: 0.6,
  wind: 0.35,
  growSeconds: 5,
  leafDensity: 60,
  leafSpread: 0.4,
  leafSize: 2.2,
  paletteTravel: 0.75,
  paletteMotion: 0.04,
  paletteStrength: 0.72,
  wireGlow: 0.8,
  wirePulse: 0.28,
  wireBody: 0.12,
};

export type TreeNode = {
  position: Vector3;
  weight: number;
  pathLength: number;
  dir: Vector3;
  children: TreeNode[];
};

// Root plates are wide and shallow: generate at near-canopy reach, then
// compress vertically so the span mirrors the crown while staying shallow.
export function flattenTree(root: TreeNode, yScale: number): TreeNode {
  const walk = (n: TreeNode) => {
    n.position.y *= yScale;
    n.children.forEach(walk);
  };
  walk(root);
  return root;
}

// mulberry32 - seeded so "regenerate" is reproducible from the seed knob
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const randomUnit = (rand: () => number): Vector3 => {
  const z = rand() * 2 - 1;
  const a = rand() * Math.PI * 2;
  const r = Math.sqrt(1 - z * z);
  return new Vector3(r * Math.cos(a), z, r * Math.sin(a));
};

// Complexity budget: BFS growth is exponential in branchChance and
// reach/step, so a hard node cap keeps every knob combination interactive
// and the scene shares the budget across trees via maxNodes.
const MAX_NODES = 2200;

export function generateTree(
  params: GardenParams,
  rand: () => number,
  origin: Vector3,
  maxNodes: number = MAX_NODES,
): TreeNode {
  const root: TreeNode = {
    position: origin.clone(),
    weight: 1,
    pathLength: 0,
    dir: new Vector3(0, 1, 0),
    children: [],
  };
  const up = new Vector3(0, 1, 0);
  const queue: TreeNode[] = [];
  let nodes = 1;
  // Initial 1-4 children sphere-distributed around the root, biased upward so
  // the sapling leaves the ground (Ballot's sphere distribution, our bias).
  for (let i = 0; i < params.initialChildren; i++) {
    const direction = randomUnit(rand)
      .multiplyScalar(1 - Math.abs(params.upBias))
      .add(up.clone().multiplyScalar(params.upBias + Math.sign(params.upBias) * rand() * 0.4))
      .normalize();
    const firstPos = origin
      .clone()
      .add(direction.clone().multiplyScalar(params.stepScale * (0.7 + rand() * 0.6)));
    const firstSide = params.upBias >= 0 ? 1 : -1;
    if (firstPos.y * firstSide < 0.03) firstPos.y = firstSide * (0.03 + Math.abs(firstPos.y) * 0.3);
    const child: TreeNode = {
      position: firstPos,
      weight: params.girthDecay,
      pathLength: params.stepScale,
      dir: direction,
      children: [],
    };
    root.children.push(child);
    queue.push(child);
  }
  // BFS: each node extends along its root-to-node direction, scaled by a
  // random scalar, plus a noise vector; growth stops past the reach threshold.
  while (queue.length) {
    const node = queue.shift()!;
    const outward = node.position.clone().sub(origin).normalize();
    const count = rand() < params.branchChance ? 2 : 1;
    for (let i = 0; i < count; i++) {
      // fork siblings get a strong lateral kick so branches visibly diverge
      // instead of hugging the shared root-outward direction
      const lateral = i === 0 ? params.noise : params.noise + params.stepScale * 0.8;
      const pull = outward
        .clone()
        .add(randomUnit(rand).multiplyScalar(lateral / params.stepScale))
        .add(up.clone().multiplyScalar(params.upBias * 0.3))
        .normalize();
      // stiffness: wood resists direction change - blend the pull with the
      // direction the limb was already growing in
      const direction = node.dir
        .clone()
        .multiplyScalar(params.stiffness)
        .add(pull.multiplyScalar(1 - params.stiffness))
        .normalize();
      const step = direction.clone().multiplyScalar(params.stepScale * (0.6 + rand() * 0.8));
      const position = node.position.clone().add(step);
      // hemisphere rule: canopy stays above the ground plane, roots below -
      // noise that pushes growth across the surface folds back to its side
      const side = params.upBias >= 0 ? 1 : -1;
      if (position.y * side < 0.03) {
        position.y = side * (0.03 + Math.abs(position.y) * 0.3);
        direction.y = Math.abs(direction.y) * side * 0.5;
        direction.normalize();
      }
      if (position.distanceTo(origin) > params.reach) continue;
      if (nodes >= maxNodes) return root;
      // da Vinci rule at forks: children split the parent's cross-section
      // area, so girth thins where the tree branches, not merely with age
      const girth = params.girthDecay * (count === 2 ? 0.72 : 1);
      const child: TreeNode = {
        position,
        weight: node.weight * girth,
        pathLength: node.pathLength + step.length(),
        dir: direction,
        children: [],
      };
      node.children.push(child);
      queue.push(child);
      nodes++;
    }
  }
  return root;
}

// Chains: maximal single-child runs between branch points, each starting at
// its parent branch node so tubes stay connected. Ballot's "segments".
type Chain = { points: Vector3[]; weights: number[]; depths: number[]; tip: boolean };

function decompose(root: TreeNode): {
  chains: Chain[];
  tips: Array<{ position: Vector3; depth: number }>;
  knuckles: Array<{ position: Vector3; weight: number; depth: number }>;
} {
  let maxPath = 0;
  const walkMax = (n: TreeNode) => {
    maxPath = Math.max(maxPath, n.pathLength);
    n.children.forEach(walkMax);
  };
  walkMax(root);
  const depthOf = (n: TreeNode) => (maxPath > 0 ? n.pathLength / maxPath : 0);
  const chains: Chain[] = [];
  const tips: Array<{ position: Vector3; depth: number }> = [];
  const knuckles: Array<{ position: Vector3; weight: number; depth: number }> = [];
  const walk = (start: TreeNode) => {
    if (start.children.length > 1)
      knuckles.push({ position: start.position, weight: start.weight, depth: depthOf(start) });
    for (const first of start.children) {
      const points = [start.position];
      const weights = [start.weight];
      const depths = [depthOf(start)];
      let node = first;
      while (true) {
        points.push(node.position);
        weights.push(node.weight);
        depths.push(depthOf(node));
        if (node.children.length !== 1) break;
        node = node.children[0];
      }
      chains.push({ points, weights, depths, tip: node.children.length === 0 });
      if (node.children.length === 0) tips.push({ position: node.position, depth: depthOf(node) });
      else walk(node);
    }
  };
  walk(root);
  return { chains, tips, knuckles };
}

export type TreeGeometry = {
  // tube mesh: position = spine point, roff = ring offset from spine, depth 0-1
  position: Float32Array;
  roff: Float32Array;
  depth: Float32Array;
  index: Uint32Array;
  // wireframe look: line segment pairs along the smoothed spines
  linePosition: Float32Array;
  lineDepth: Float32Array;
  // leaf tips (buds / future notes)
  tips: Array<{ position: Vector3; depth: number }>;
  // canopy sites: outer-branch spine samples where foliage accumulates,
  // each carrying its branch frame so instanced geometry can orient to the limb
  leafSites: Array<{
    position: Vector3;
    depth: number;
    tangent: Vector3;
    normal: Vector3;
    radius: number;
  }>;
};

export function buildTreeGeometry(params: GardenParams, root: TreeNode): TreeGeometry {
  const { chains, tips, knuckles } = decompose(root);
  const ring = params.ringSegments;
  const pos: number[] = [];
  const off: number[] = [];
  const dep: number[] = [];
  const idx: number[] = [];
  const lpos: number[] = [];
  const ldep: number[] = [];
  const leafSites: Array<{
    position: Vector3;
    depth: number;
    tangent: Vector3;
    normal: Vector3;
    radius: number;
  }> = [];
  for (const chain of chains) {
    if (chain.points.length < 2) continue;
    const curve = new CatmullRomCurve3(chain.points, false, "centripetal");
    // polyline length estimate: curve.getLength() subdivides 200x per chain
    // and was the generation hotspot; control-point distances are plenty
    // accurate for picking a sample count
    let length = 0;
    for (let i = 1; i < chain.points.length; i++)
      length += chain.points[i].distanceTo(chain.points[i - 1]);
    const samples = Math.min(72, Math.max(4, Math.round(length / (params.stepScale * 0.22))));
    const spine: Vector3[] = [];
    const radii: number[] = [];
    const depths: number[] = [];
    const polyline = (t: number) => {
      const f = t * (chain.points.length - 1);
      const j = Math.min(chain.points.length - 2, Math.floor(f));
      return chain.points[j].clone().lerp(chain.points[j + 1], f - j);
    };
    for (let i = 0; i <= samples; i++) {
      const t = i / samples;
      // stiff wood: pull the spline back toward straight runs between joints
      spine.push(curve.getPoint(t).lerp(polyline(t), params.stiffness * 0.45));
      const f = t * (chain.points.length - 1);
      const j = Math.min(chain.points.length - 2, Math.floor(f));
      const local = f - j;
      radii.push(
        (chain.weights[j] + (chain.weights[j + 1] - chain.weights[j]) * local) * params.girth,
      );
      depths.push(chain.depths[j] + (chain.depths[j + 1] - chain.depths[j]) * local);
    }
    // TNB frames by parallel transport: tangent from neighbors, first normal
    // from a cross with an arbitrary reference, then carried along the spine.
    let normal = new Vector3();
    const base = pos.length / 3;
    for (let i = 0; i <= samples; i++) {
      const tangent = spine[Math.min(samples, i + 1)]
        .clone()
        .sub(spine[Math.max(0, i - 1)])
        .normalize();
      if (i === 0) {
        const ref = Math.abs(tangent.y) < 0.9 ? new Vector3(0, 1, 0) : new Vector3(1, 0, 0);
        normal = new Vector3().crossVectors(tangent, ref).normalize();
      } else {
        normal.sub(tangent.clone().multiplyScalar(normal.dot(tangent))).normalize();
      }
      const binormal = new Vector3().crossVectors(tangent, normal);
      for (let s = 0; s < ring; s++) {
        const a = (s / ring) * Math.PI * 2;
        const o = normal
          .clone()
          .multiplyScalar(Math.cos(a))
          .add(binormal.clone().multiplyScalar(Math.sin(a)))
          .multiplyScalar(radii[i]);
        pos.push(spine[i].x, spine[i].y, spine[i].z);
        off.push(o.x, o.y, o.z);
        dep.push(depths[i]);
      }
      if (i > 0) {
        // stitch ring i-1 to ring i as quads = two triangles per segment pair
        const a0 = base + (i - 1) * ring;
        const b0 = base + i * ring;
        for (let s = 0; s < ring; s++) {
          const s1 = (s + 1) % ring;
          idx.push(a0 + s, b0 + s, b0 + s1, a0 + s, b0 + s1, a0 + s1);
        }
      }
      if (i > 0) {
        lpos.push(
          spine[i - 1].x,
          spine[i - 1].y,
          spine[i - 1].z,
          spine[i].x,
          spine[i].y,
          spine[i].z,
        );
        ldep.push(depths[i - 1], depths[i]);
      }
      // canopy accumulates along the outer half of the tree, not just at tips
      if (depths[i] > 0.55 && i % 2 === 0)
        leafSites.push({
          position: spine[i].clone(),
          depth: depths[i],
          tangent: tangent.clone(),
          normal: normal.clone(),
          radius: radii[i],
        });
      // close tip chains with an apex fan so branch ends are never open pipes
      if (chain.tip && i === samples) {
        const endTangent = spine[samples]
          .clone()
          .sub(spine[Math.max(0, samples - 1)])
          .normalize();
        const apex = spine[samples]
          .clone()
          .add(endTangent.clone().multiplyScalar(Math.max(0.015, radii[samples] * 1.6)));
        const apexIndex = pos.length / 3;
        pos.push(apex.x, apex.y, apex.z);
        const apexOff = endTangent.multiplyScalar(0.002);
        off.push(apexOff.x, apexOff.y, apexOff.z);
        dep.push(depths[samples]);
        const lastRing = base + samples * ring;
        for (let s = 0; s < ring; s++)
          idx.push(lastRing + s, apexIndex, lastRing + ((s + 1) % ring));
      }
    }
  }
  for (const tip of tips)
    leafSites.push({
      position: tip.position,
      depth: tip.depth,
      tangent: new Vector3(0, 1, 0),
      normal: new Vector3(1, 0, 0),
      radius: 0.01,
    });
  // knuckles: a small UV-sphere welded over every fork so parent and child
  // tubes meet inside solid geometry instead of showing open seams
  for (const k of knuckles) {
    const r = Math.max(0.012, k.weight * params.girth * 1.18);
    const lats = 4;
    const base = pos.length / 3;
    for (let li = 0; li <= lats; li++) {
      const phi = -Math.PI / 2 + (li / lats) * Math.PI;
      const cy = Math.sin(phi) * r;
      const cr = Math.cos(phi) * r;
      for (let s2 = 0; s2 < ring; s2++) {
        const a = (s2 / ring) * Math.PI * 2;
        pos.push(k.position.x, k.position.y, k.position.z);
        off.push(Math.cos(a) * cr, cy, Math.sin(a) * cr);
        dep.push(k.depth);
      }
      if (li > 0) {
        const a0 = base + (li - 1) * ring;
        const b0 = base + li * ring;
        for (let s2 = 0; s2 < ring; s2++) {
          const s3 = (s2 + 1) % ring;
          idx.push(a0 + s2, b0 + s2, b0 + s3, a0 + s2, b0 + s3, a0 + s3);
        }
      }
    }
  }
  return {
    position: new Float32Array(pos),
    roff: new Float32Array(off),
    depth: new Float32Array(dep),
    index: new Uint32Array(idx),
    linePosition: new Float32Array(lpos),
    lineDepth: new Float32Array(ldep),
    tips,
    leafSites,
  };
}
