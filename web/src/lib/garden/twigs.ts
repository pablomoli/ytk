// Stage 2: space colonization (Runions et al. 2007) below the measured
// clusters. Nothing here reads the dendrogram beyond the attractors handed in.
import { Vector3 } from "three";
import { makeNode, type ColonizeOptions, type SkelNode } from "./types";

type Hit = { node: SkelNode; dist: number };

// Uniform hash grid over the growing node set; cell size is the attraction
// distance, so a query touches a 3x3x3 neighbourhood instead of every node.
class NodeGrid {
  private readonly cells = new Map<string, SkelNode[]>();
  private readonly inv: number;

  constructor(cellSize: number) {
    this.inv = 1 / cellSize;
  }

  insert(node: SkelNode): void {
    const key = this.keyOf(node.position.x, node.position.y, node.position.z);
    const bucket = this.cells.get(key);
    if (bucket) bucket.push(node);
    else this.cells.set(key, [node]);
  }

  nearest(point: Vector3, radius: number): Hit | null {
    const span = Math.max(0, Math.ceil(radius * this.inv));
    const cx = Math.floor(point.x * this.inv);
    const cy = Math.floor(point.y * this.inv);
    const cz = Math.floor(point.z * this.inv);
    const limit = radius * radius;
    let best: SkelNode | null = null;
    let bestSq = Infinity;
    for (let ix = cx - span; ix <= cx + span; ix++) {
      for (let iy = cy - span; iy <= cy + span; iy++) {
        for (let iz = cz - span; iz <= cz + span; iz++) {
          const bucket = this.cells.get(this.key(ix, iy, iz));
          if (!bucket) continue;
          for (const node of bucket) {
            const d = node.position.distanceToSquared(point);
            if (d <= limit && d < bestSq) {
              bestSq = d;
              best = node;
            }
          }
        }
      }
    }
    return best ? { node: best, dist: Math.sqrt(bestSq) } : null;
  }

  private keyOf(x: number, y: number, z: number): string {
    return this.key(Math.floor(x * this.inv), Math.floor(y * this.inv), Math.floor(z * this.inv));
  }

  private key(ix: number, iy: number, iz: number): string {
    return `${ix},${iy},${iz}`;
  }
}

// Cap on the run counter so a seed's Infinity does not poison the arithmetic.
const MAX_RUN = 1e6;
// One heading per angular cluster of the node's attractors. Splitting inside
// the iteration is what lets a fork land on a limb's first node: a node can
// otherwise only take its second child an iteration after its first.
const headings = (dirs: Vector3[], mayFork: boolean, splitCos: number): Vector3[] => {
  const mean = new Vector3();
  for (const d of dirs) mean.add(d);
  if (mean.lengthSq() < 1e-12) return [];
  mean.normalize();
  if (!mayFork || dirs.length < 2) return [mean];

  let far = dirs[0] as Vector3;
  let worst = Infinity;
  for (const d of dirs) {
    const dot = d.dot(mean);
    if (dot < worst) {
      worst = dot;
      far = d;
    }
  }
  if (worst >= splitCos) return [mean];

  const a = new Vector3();
  const b = new Vector3();
  for (const d of dirs) (d.dot(mean) >= d.dot(far) ? a : b).add(d);
  if (a.lengthSq() < 1e-12 || b.lengthSq() < 1e-12) return [mean];
  return [a.normalize(), b.normalize()];
};

const randomUnit = (rand: () => number, out: Vector3): Vector3 => {
  const z = rand() * 2 - 1;
  const a = rand() * Math.PI * 2;
  const r = Math.sqrt(Math.max(0, 1 - z * z));
  return out.set(Math.cos(a) * r, Math.sin(a) * r, z);
};

/**
 * Grow twigs from `tips` into the attractor cloud. Mutates the nodes in `tips`
 * by appending children; returns how many nodes were added.
 */
export function colonize(tips: SkelNode[], opts: ColonizeOptions): number {
  const {
    step,
    killDistance,
    attractDistance,
    maxNodes,
    rand,
    jitter = 0,
    upBias = 0,
    bareRun = () => 0,
    splitCos = () => 0.2,
    stepFor = () => step,
  } = opts;
  if (tips.length === 0 || opts.attractors.length === 0) return 0;
  if (step <= 0 || attractDistance <= 0 || maxNodes <= 0) return 0;

  const attractors = opts.attractors.map((p) => p.clone());
  const alive = new Uint8Array(attractors.length).fill(1);
  let remaining = attractors.length;

  // Finer cells measured 4-20x slower: most attractors miss, and a miss on a
  // fine grid pays hundreds of empty-cell lookups instead of 27.
  const grid = new NodeGrid(attractDistance);
  const nodes: SkelNode[] = [];
  for (const tip of tips) {
    nodes.push(tip);
    grid.insert(tip);
  }

  // A query radius covering both roles lets one grid lookup per attractor
  // decide kill-or-associate; killDistance is normally well under di.
  const queryRadius = Math.max(attractDistance, killDistance);
  // Every productive iteration adds at least one node, so this only fires on a
  // degenerate cloud that can never fall inside killDistance.
  const maxIterations = maxNodes + 8;

  const pull = new Map<SkelNode, Vector3[]>();
  const toward = new Vector3();
  const wobble = new Vector3();
  let added = 0;
  // Steps a node sits from the start of its own limb. Seeds are handed in
  // mid-limb, so they carry no run of their own and may fork at once.
  const run = new Map<SkelNode, number>();
  for (const tip of tips) run.set(tip, Infinity);

  for (let iter = 0; iter < maxIterations && remaining > 0 && added < maxNodes; iter++) {
    pull.clear();
    for (let i = 0; i < attractors.length; i++) {
      if (!alive[i]) continue;
      const point = attractors[i] as Vector3;
      const hit = grid.nearest(point, queryRadius);
      if (!hit) continue;
      if (hit.dist <= killDistance) {
        alive[i] = 0;
        remaining--;
        continue;
      }
      if (hit.dist > attractDistance) continue;
      toward.subVectors(point, hit.node.position).divideScalar(hit.dist);
      const acc = pull.get(hit.node);
      if (acc) acc.push(toward.clone());
      else pull.set(hit.node, [toward.clone()]);
    }
    if (remaining === 0 || pull.size === 0) break;

    let grew = 0;
    const frontier = nodes.length;
    for (let n = 0; n < frontier && added < maxNodes; n++) {
      const parent = nodes[n] as SkelNode;
      const dirs = pull.get(parent);
      if (!dirs || dirs.length === 0) continue;
      const parentRun = run.get(parent) ?? 0;
      const mayFork = parentRun >= bareRun(parent.order);
      for (const heading of headings(dirs, mayFork, splitCos(parent.order))) {
        if (added >= maxNodes) break;
        // First child continues the parent's axis; a later child is a fork and
        // starts the next order.
        const lateral = parent.children.length > 0;
        if (lateral && !mayFork) break;
        const order = lateral ? parent.order + 1 : parent.order;
        // A child that jumps a full step ahead becomes nearest to the very
        // attractors that would have forked its parent's base.
        const reach = stepFor(order);
        heading.multiplyScalar(reach);
        // Only the departing child: the residue of an isotropic cloud is
        // isotropic, so an untilted fork leaves at a right angle on the median.
        if (lateral && upBias !== 0) heading.y += upBias * reach;
        if (jitter > 0) heading.addScaledVector(randomUnit(rand, wobble), jitter);
        const len = heading.length();
        if (len === 0) continue;
        heading.divideScalar(len);
        const child = makeNode(
          parent.position.clone().addScaledVector(heading, reach),
          heading,
          parent.pathLength + reach,
          order,
        );
        parent.children.push(child);
        nodes.push(child);
        run.set(child, lateral ? 0 : Math.min(parentRun, MAX_RUN) + 1);
        grid.insert(child);
        added++;
        grew++;
      }
    }
    if (grew === 0) break;
  }

  return added;
}
