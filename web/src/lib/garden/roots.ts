// The root system: the same five stages as the crown, run in a space where +y
// points down. One reflection at the end inverts every tropism at once.
import { Vector3 } from "three";
import type { BucketTopology, TopoNode } from "./datatree";
import { applyMurrayGirth } from "./girth";
import { countNodes, growTwigs, type GrowthParams } from "./pipeline";
import { growScaffold } from "./scaffold";
import { rng } from "./tree";
import type { Envelope, SkelNode } from "./types";

// Plate radius as a multiple of the crown's, and plate depth as a multiple of
// the crown's half-height: a root plate runs wider than the crown and far
// shallower. Both scale off the crown, so a big tree gets a big plate.
export const ROOT_SPREAD = 1.2;
export const ROOT_DEPTH = 0.4;
// Share of the depth that is bare collar before the plate opens out.
const ROOT_COLLAR = 0.06;
// Shallowest a lateral may level off, as a share of the plate depth. The
// mirrored sag term eases limbs up to this instead of letting them dive.
const ROOT_SHALLOW = 0.1;
// Mirrored, the order gradient is a taproot pulling straight down and laterals
// running flat; a tighter decay than the crown's gets them flat one order sooner.
const ROOT_ORDER_DECAY = 0.7;
// Internode as a share of the crown's: the plate is shallow, so a crown-sized
// step spends the whole taproot in three nodes.
const ROOT_STEP = 0.55;
// Mirrored tilt on fine roots. Small and downward-in-world, so fibrous ends
// hang under the plate rather than surfacing through the ground disc.
const ROOT_TWIG_TILT = 0.12;
// Roots branch coarser than crowns and most of the result is under the ground
// disc, so the scaffold takes the larger share and fine roots the remainder.
const ROOT_SCAFFOLD_SHARE = 0.55;
// Dendrogram levels the root scaffold reads. Deeper costs hidden nodes and
// changes nothing above the ground disc.
const ROOT_LEVELS = 3;
// A lateral wanders far more than a limb: at the crown's noise the plate came
// out as four dead-straight spokes.
const ROOT_NOISE = 2.2;
const ROOT_STIFFNESS = 0.85;
// Murray probe pass: radii are homogeneous of degree one in the tip radius, so
// a unit-tip pass measures the shape factor and the second pass lands exactly.
const PROBE_TIP = 1;

// Mirrored-space envelope: an oblate ellipsoid standing above the origin that
// the caller reflects back under it.
export function rootEnvelope(crown: Envelope, origin: Vector3): Envelope {
  const depth = Math.max(1e-4, crown.halfHeight * ROOT_DEPTH);
  const halfHeight = Math.max(1e-4, (depth * (1 - ROOT_COLLAR)) / 2);
  return {
    center: new Vector3(origin.x, origin.y + depth * ROOT_COLLAR + halfHeight, origin.z),
    radius: Math.max(1e-4, crown.radius * ROOT_SPREAD),
    halfHeight,
  };
}

// Breadth-first so a dendrogram that lists a child before its parent still
// truncates by level rather than by array order.
function coarsen(topo: BucketTopology, levels: number): BucketTopology {
  const byParent = new Map<number, TopoNode[]>();
  let top: TopoNode | undefined;
  for (const n of topo.nodes) {
    if (n.parent === -1) {
      top = n;
      continue;
    }
    const kids = byParent.get(n.parent);
    if (kids) kids.push(n);
    else byParent.set(n.parent, [n]);
  }
  if (!top) return topo;
  const nodes: TopoNode[] = [top];
  let frontier: TopoNode[] = [top];
  for (let d = 0; d < levels; d += 1) {
    const next: TopoNode[] = [];
    for (const parent of frontier) {
      for (const kid of byParent.get(parent.id) ?? []) {
        nodes.push(kid);
        next.push(kid);
      }
    }
    frontier = next;
  }
  return { ...topo, nodes };
}

function reflect(root: SkelNode, aboutY: number): void {
  const stack: SkelNode[] = [root];
  while (stack.length > 0) {
    const node = stack.pop() as SkelNode;
    node.position.y = 2 * aboutY - node.position.y;
    node.dir.y = -node.dir.y;
    for (const child of node.children) stack.push(child);
  }
}

export function growRootSystem(
  topo: BucketTopology,
  crown: Envelope,
  params: GrowthParams,
  trunkRadius: number,
  seed: number,
  origin: Vector3,
  maxNodes: number,
): { root: SkelNode; env: Envelope } {
  const mirror = rootEnvelope(crown, origin);
  const depth = mirror.center.y + mirror.halfHeight - origin.y;
  const rand = rng(seed);
  const budget = Math.max(2, Math.floor(maxNodes));
  const rootParams: GrowthParams = {
    ...params,
    orderDecay: params.orderDecay * ROOT_ORDER_DECAY,
    noise: params.noise * ROOT_NOISE,
    stiffness: params.stiffness * ROOT_STIFFNESS,
    stepScale: params.stepScale * ROOT_STEP,
    twigStep: params.twigStep * ROOT_STEP,
    // Mirrored, the sag floor is the shallowest a lateral may run, so the plate
    // stays under the ground disc instead of breaking through it.
    sagFloor: origin.y + ROOT_SHALLOW * depth,
  };

  const { root, lobes } = growScaffold(
    coarsen(topo, ROOT_LEVELS),
    mirror,
    rootParams,
    rand,
    origin,
    Math.max(24, Math.floor(budget * ROOT_SCAFFOLD_SHARE)),
  );
  growTwigs(mirror, lobes, rootParams, rand, budget - countNodes(root), ROOT_TWIG_TILT);
  reflect(root, origin.y);

  // Pipe-model continuity through the collar: the shape factor comes from the
  // fine roots bottom-up, the scale from the trunk the collar has to meet.
  const exponent = Math.max(1.2, params.pipeExponent);
  applyMurrayGirth(root, PROBE_TIP, exponent);
  const shape = root.radius > 0 ? root.radius : 1;
  applyMurrayGirth(root, Math.max(1e-6, trunkRadius) / shape, exponent);

  return {
    root,
    env: {
      center: new Vector3(mirror.center.x, 2 * origin.y - mirror.center.y, mirror.center.z),
      radius: mirror.radius,
      halfHeight: mirror.halfHeight,
    },
  };
}
