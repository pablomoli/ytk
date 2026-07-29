// Stage 2: space colonization (Runions et al. 2007) below the measured
// clusters. Twigs are generated texture under the resolution of the data, so
// nothing here reads the dendrogram beyond the attractor cloud it was handed.
import { Vector3 } from "three";
import { makeNode, type ColonizeOptions, type SkelNode } from "./types";

type Hit = { node: SkelNode; dist: number };

// Uniform hash grid over the growing node set. Cell size is the attraction
// distance, so a nearest-node query touches a 3x3x3 neighbourhood instead of
// every node.
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
  const { step, killDistance, attractDistance, maxNodes, rand, jitter = 0 } = opts;
  if (tips.length === 0 || opts.attractors.length === 0) return 0;
  if (step <= 0 || attractDistance <= 0 || maxNodes <= 0) return 0;

  const attractors = opts.attractors.map((p) => p.clone());
  const alive = new Uint8Array(attractors.length).fill(1);
  let remaining = attractors.length;

  // Cell size is di, so a query touches 3x3x3 cells. Finer cells were measured
  // 4-20x slower: most attractors have no node in range for most iterations,
  // and a miss then pays hundreds of empty-cell lookups instead of 27.
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

  const pull = new Map<SkelNode, Vector3>();
  const toward = new Vector3();
  const wobble = new Vector3();
  let added = 0;

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
      if (acc) acc.add(toward);
      else pull.set(hit.node, toward.clone());
    }
    if (remaining === 0 || pull.size === 0) break;

    let grew = 0;
    const frontier = nodes.length;
    for (let n = 0; n < frontier && added < maxNodes; n++) {
      const parent = nodes[n] as SkelNode;
      const acc = pull.get(parent);
      if (!acc || acc.lengthSq() === 0) continue;
      const heading = acc.clone().normalize().multiplyScalar(step);
      if (jitter > 0) heading.addScaledVector(randomUnit(rand, wobble), jitter);
      const len = heading.length();
      if (len === 0) continue;
      heading.divideScalar(len);
      // types.ts fixes the meaning of order: 0 on the trunk, +1 on each lateral
      // child. The first child continues its parent's axis; a second or later
      // child is a fork and starts the next order.
      const order = parent.children.length > 0 ? parent.order + 1 : parent.order;
      const child = makeNode(
        parent.position.clone().addScaledVector(heading, step),
        heading,
        parent.pathLength + step,
        order,
      );
      parent.children.push(child);
      nodes.push(child);
      grid.insert(child);
      added++;
      grew++;
    }
    if (grew === 0) break;
  }

  return added;
}
