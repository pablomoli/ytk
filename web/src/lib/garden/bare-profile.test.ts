import { describe, expect, test } from "vite-plus/test";
import { Vector3 } from "three";
import type { BucketTopology, TopoNode } from "./datatree";
import { growGardenTree, type GrowthParams } from "./pipeline";
import type { EnvelopeShape, SkelNode } from "./types";

const ORIGIN = new Vector3(0, 0, 0);

const shape: EnvelopeShape = {
  maxHeight: 10,
  spreadMin: 0.35,
  spreadMax: 1.1,
  trunkFraction: 0.35,
};

const params: GrowthParams = {
  stepScale: 0.32,
  stiffness: 0.6,
  noise: 0.16,
  upBias: 0.55,
  orderDecay: 0.35,
  sag: 0.7,
  sagFloor: 1.4,
  lengthGradient: 0.6,
  pipeExponent: 2.5,
  tipRadius: 0.006,
  twigStep: 0.06,
  attractorsPerNote: 6,
};

const node = (id: number, parent: number, mass: number, persistence = 0.5): TopoNode => ({
  id,
  parent,
  mass,
  persistence,
});

// Three dendrogram levels with leaves at both, as the real buckets have: a
// hierarchy whose leaves all sit at one depth gives no order-2 limbs to measure.
const multilevel = (notes = 2000): BucketTopology => {
  const nodes: TopoNode[] = [node(0, -1, notes, 0.9)];
  for (let i = 0; i < 5; i += 1) nodes.push(node(1 + i, 0, notes * 0.08, 0.55 + 0.03 * i));
  for (let i = 0; i < 3; i += 1) {
    const id = 6 + i;
    nodes.push(node(id, 0, notes * 0.2, 0.75 - 0.05 * i));
    nodes.push(node(20 + 2 * i, id, notes * 0.11, 0.5));
    nodes.push(node(21 + 2 * i, id, notes * 0.09, 0.45));
  }
  return { bucket: "multilevel", n_notes: notes, nodes };
};

const median = (values: number[]): number => {
  const s = [...values].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? (s[mid] as number) : (((s[mid - 1] as number) + (s[mid] as number)) / 2);
};

// Limb starts only: a node whose parent shares its order is mid-limb, and
// walking from there would report the remainder of that limb as a limb.
const limbStarts = (root: SkelNode): SkelNode[] => {
  const out: SkelNode[] = [];
  const stack: { node: SkelNode; parentOrder: number }[] = [{ node: root, parentOrder: -1 }];
  while (stack.length > 0) {
    const { node: n, parentOrder } = stack.pop() as { node: SkelNode; parentOrder: number };
    if (n.order > parentOrder) out.push(n);
    for (const c of n.children) stack.push({ node: c, parentOrder: n.order });
  }
  return out;
};

/**
 * Median fraction of a limb that runs bare before its first branch, by branch
 * order. A limb is a maximal run of one order and ends on a childless node, so
 * its first higher-order child always sits at or before that end.
 */
function bareProfile(root: SkelNode): Map<number, number> {
  const byOrder = new Map<number, number[]>();
  for (const start of limbStarts(root)) {
    const order = start.order;
    let cur: SkelNode | undefined = start;
    let first: number | null = null;
    let end = start.pathLength;
    while (cur) {
      if (first === null && cur.children.some((c) => c.order > order)) first = cur.pathLength;
      end = cur.pathLength;
      cur = cur.children.find((c) => c.order === order);
    }
    const span = end - start.pathLength;
    if (span <= 1e-9 || first === null) continue;
    const bucket = byOrder.get(order) ?? [];
    bucket.push((first - start.pathLength) / span);
    byOrder.set(order, bucket);
  }
  const out = new Map<number, number>();
  for (const [order, values] of byOrder) {
    // A handful of limbs at the resolution limit is noise, not a profile.
    if (order >= 1 && values.length >= 5) out.set(order, median(values));
  }
  return out;
}

describe("bare-length profile", () => {
  test.each([3, 11, 29])("does not grow with branch order, seed %i", (seed) => {
    const { root } = growGardenTree(multilevel(), 2000, shape, params, seed, ORIGIN, 14000);
    const byOrder = bareProfile(root);
    const orders = [...byOrder.keys()].sort((a, b) => a - b);
    // the tree has to be deep enough for the assertion to mean anything
    expect(orders.length).toBeGreaterThanOrEqual(4);

    const values = orders.map((o) => byOrder.get(o) as number);
    // Tolerance, not equality: a limb only a few nodes long quantises its bare
    // fraction coarsely, so adjacent orders can invert by a step's worth. The
    // last generation is excluded here for the same reason and covered below.
    const TOL = 0.06;
    for (let i = 1; i < values.length - 1; i += 1) {
      expect(values[i] as number).toBeLessThanOrEqual((values[i - 1] as number) + TOL);
    }
    // and the outer half branches sooner than the inner half, which is the
    // whole point: the original profile rose from 0.16 at order 1 to 0.42.
    const cut = Math.floor(values.length / 2);
    const mean = (v: number[]) => v.reduce((a, b) => a + b, 0) / Math.max(1, v.length);
    expect(mean(values.slice(cut))).toBeLessThan(mean(values.slice(0, cut)));
  });
});
