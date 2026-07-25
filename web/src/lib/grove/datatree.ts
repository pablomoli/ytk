// PROTOTYPE (grove workshop) - data-native topology generator (E2).
// Consumes /api/grove bucket snapshots (average-linkage cluster hierarchy,
// scripts/grove_lab/dendro.py) and grows a TreeNode tree whose STRUCTURE is
// the data: limb length = cluster persistence, girth = note mass via the
// da Vinci area rule (child weight = parent * sqrt(mass ratio)), one tree
// per bucket. The hand-tuned BFS generator remains as the aesthetic mode;
// knobs (stiffness, noise, upBias, girth...) shape character in both.
import { Vector3 } from "three";
import type { GroveParams, TreeNode } from "./tree";

export type TopoNode = {
  id: number;
  parent: number;
  mass: number;
  persistence: number;
  exemplars?: string[];
};
export type BucketTopology = {
  bucket: string;
  palette?: string;
  n_notes: number;
  params?: { kind: string };
  stability?: { kind: string; ari: number | null } | null;
  nodes: TopoNode[];
};
export type GrovePayload = {
  version: number;
  buckets: BucketTopology[];
  // explicit camera azimuth (radians) around the vertical axis; E7 records
  // it per stimulus so view angle is a controlled variable, not a nuisance
  azimuth?: number;
};

const randomUnit = (rand: () => number): Vector3 => {
  const z = rand() * 2 - 1;
  const a = rand() * Math.PI * 2;
  const r = Math.sqrt(1 - z * z);
  return new Vector3(r * Math.cos(a), z, r * Math.sin(a));
};

const GOLDEN = 2.399963;

export function generateDataTree(
  params: GroveParams,
  rand: () => number,
  origin: Vector3,
  topo: BucketTopology,
  maxNodes: number,
): TreeNode {
  const up = new Vector3(0, 1, 0);
  const byParent = new Map<number, TopoNode[]>();
  for (const n of topo.nodes) {
    if (n.parent !== -1) {
      const kids = byParent.get(n.parent) ?? [];
      kids.push(n);
      byParent.set(n.parent, kids);
    }
  }
  const rootTopo = topo.nodes.find((n) => n.parent === -1) ?? topo.nodes[0];
  const maxPersistence = Math.max(1e-6, ...topo.nodes.map((n) => n.persistence));
  let budget = maxNodes;

  const root: TreeNode = {
    position: origin.clone(),
    weight: 1,
    pathLength: 0,
    dir: up.clone(),
    children: [],
  };

  // Grow one limb as a chain of steps; returns its last TreeNode so the
  // topology children can fork from it. Same feel as the BFS generator:
  // stiffness resists turning, noise wanders, the hemisphere rule folds
  // growth back above ground.
  const growLimb = (from: TreeNode, dir: Vector3, weight: number, steps: number): TreeNode => {
    let node = from;
    let direction = dir.clone();
    let w = weight;
    for (let i = 0; i < steps && budget > 0; i++) {
      const pull = direction
        .clone()
        .add(randomUnit(rand).multiplyScalar(params.noise * 0.8))
        .add(up.clone().multiplyScalar(params.upBias * 0.25))
        .normalize();
      direction = direction
        .clone()
        .multiplyScalar(params.stiffness)
        .add(pull.multiplyScalar(1 - params.stiffness))
        .normalize();
      const step = direction.clone().multiplyScalar(params.stepScale * (0.7 + rand() * 0.6));
      const position = node.position.clone().add(step);
      if (position.y < 0.03) {
        position.y = 0.03 + Math.abs(position.y) * 0.3;
        direction.y = Math.abs(direction.y) * 0.5;
        direction.normalize();
      }
      // reach caps limb extent (scaled per bucket), taper thins each step -
      // same wood rules as the BFS generator, so both modes share a look
      if (position.distanceTo(origin) > params.reach) break;
      w *= params.girthDecay;
      const child: TreeNode = {
        position,
        weight: w,
        pathLength: node.pathLength + step.length(),
        dir: direction.clone(),
        children: [],
      };
      node.children.push(child);
      node = child;
      budget--;
    }
    return node;
  };

  const stepsFor = (n: TopoNode) =>
    Math.max(3, Math.round(3 + 9 * (n.persistence / maxPersistence)));

  // trunk: the bucket root, straight up with the root node's persistence
  const trunkEnd = growLimb(root, up.clone(), 1, stepsFor(rootTopo));

  const walk = (topoNode: TopoNode, fromTree: TreeNode, baseDir: Vector3) => {
    const kids = (byParent.get(topoNode.id) ?? []).slice().sort((a, b) => b.mass - a.mass);
    kids.forEach((kid, i) => {
      if (budget <= 0) return;
      // da Vinci with data: children split the parent's cross-section by
      // their share of the note mass
      const share = Math.sqrt(Math.max(0.02, kid.mass / Math.max(1, topoNode.mass)));
      const kidWeight = fromTree.weight * Math.min(0.92, Math.max(0.3, share));
      // fork around the limb: golden-angle azimuth, heavier limbs steeper
      const azimuth = i * GOLDEN + rand() * 0.5;
      const polar = 0.5 + 0.5 * (1 - share); // light limbs splay wider
      const ref = Math.abs(baseDir.y) < 0.9 ? up : new Vector3(1, 0, 0);
      const side = new Vector3().crossVectors(baseDir, ref).normalize();
      const out = new Vector3().crossVectors(side, baseDir).normalize();
      const lateral = side
        .clone()
        .multiplyScalar(Math.cos(azimuth))
        .add(out.clone().multiplyScalar(Math.sin(azimuth)));
      const dir = baseDir
        .clone()
        .multiplyScalar(1 - polar * 0.8)
        .add(lateral.multiplyScalar(polar))
        .add(up.clone().multiplyScalar(params.upBias * 0.3))
        .normalize();
      const end = growLimb(fromTree, dir, kidWeight, stepsFor(kid));
      walk(kid, end, end.dir);
    });
  };
  walk(rootTopo, trunkEnd, trunkEnd.dir);
  return root;
}

export async function fetchGrovePayload(): Promise<GrovePayload | null> {
  try {
    const r = await fetch("/api/grove");
    if (!r.ok) return null;
    return (await r.json()) as GrovePayload;
  } catch {
    return null;
  }
}
