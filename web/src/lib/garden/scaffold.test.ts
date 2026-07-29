import { describe, expect, test } from "vite-plus/test";
import { Vector3 } from "three";
import { rng } from "./tree";
import { envelopeFor, insideEnvelope, sampleLobe } from "./envelope";
import { growScaffold, type Lobe, type ScaffoldParams } from "./scaffold";
import type { BucketTopology, TopoNode } from "./datatree";
import type { Envelope, SkelNode } from "./types";

const ORIGIN = new Vector3(0, 0, 0);

const env: Envelope = envelopeFor(ORIGIN, 100, 100, {
  maxHeight: 10,
  spreadMin: 0.35,
  spreadMax: 1.1,
  trunkFraction: 0.35,
});
const crownBase = env.center.y - env.halfHeight;

const params: ScaffoldParams = {
  stepScale: 0.25,
  stiffness: 0.55,
  noise: 0.12,
  upBias: 0.9,
  orderDecay: 0.35,
  sag: 0.7,
  sagFloor: crownBase + 0.4,
  lengthGradient: 0.6,
};

const node = (
  id: number,
  parent: number,
  mass: number,
  persistence = 0.5,
): TopoNode => ({ id, parent, mass, persistence });

const topology = (nodes: TopoNode[]): BucketTopology => ({
  bucket: "test",
  n_notes: nodes[0]?.mass ?? 0,
  nodes,
});

// root plus `count` leaf children of equal mass and persistence
const star = (count: number, mass = 100, persistence = 0.5): BucketTopology =>
  topology([
    node(0, -1, mass, persistence),
    ...Array.from({ length: count }, (_, i) => node(i + 1, 0, mass / count, persistence)),
  ]);

// three dendrogram levels: 2 first-order children, each with 2 of its own
const deep = (): BucketTopology =>
  topology([
    node(0, -1, 400, 0.9),
    node(1, 0, 220, 0.7),
    node(2, 0, 180, 0.7),
    node(3, 1, 120, 0.5),
    node(4, 1, 100, 0.5),
    node(5, 2, 100, 0.5),
    node(6, 2, 80, 0.5),
  ]);

const walk = (root: SkelNode): SkelNode[] => {
  const out: SkelNode[] = [];
  const stack = [root];
  while (stack.length > 0) {
    const cur = stack.pop() as SkelNode;
    out.push(cur);
    for (const c of cur.children) stack.push(c);
  }
  return out;
};

type Limb = { order: number; from: SkelNode; tip: SkelNode; nodes: SkelNode[]; length: number };

// A limb is a maximal run of nodes sharing one order; `from` is the node it
// forked off, so rise and length are measured against the fork, not the tip.
const limbs = (root: SkelNode): Limb[] => {
  const out: Limb[] = [];
  const collect = (start: SkelNode, from: SkelNode) => {
    const nodes = [start];
    let cur = start;
    for (;;) {
      const next = cur.children.find((c) => c.order === cur.order);
      if (!next) break;
      nodes.push(next);
      cur = next;
    }
    out.push({ order: start.order, from, tip: cur, nodes, length: cur.pathLength - from.pathLength });
    for (const n of nodes) {
      for (const c of n.children) if (c.order !== n.order) collect(c, n);
    }
  };
  collect(root, root);
  return out;
};

const contained = (n: SkelNode): boolean =>
  insideEnvelope(env, n.position) || (n.order === 0 && n.position.y < crownBase);

const grow = (topo: BucketTopology, over: Partial<ScaffoldParams> = {}, seed = 7, max = 4000) =>
  growScaffold(topo, env, { ...params, ...over }, rng(seed), ORIGIN, max);

describe("growScaffold", () => {
  test("every node lies inside the envelope, or on the trunk below the crown", () => {
    for (const seed of [1, 2, 3, 4, 5]) {
      const { root } = grow(deep(), {}, seed);
      const nodes = walk(root);
      expect(nodes.length).toBeGreaterThan(20);
      for (const n of nodes) expect(contained(n)).toBe(true);
    }
  });

  test("the upward pull falls off with branch order", () => {
    // sag is the other vertical axis; isolate the order gradient by zeroing it.
    const { root } = grow(deep(), { sag: 0 });
    const byOrder = new Map<number, number[]>();
    for (const n of walk(root)) {
      if (n === root) continue;
      const bucket = byOrder.get(n.order) ?? [];
      bucket.push(Math.abs(n.dir.y));
      byOrder.set(n.order, bucket);
    }
    const orders = [...byOrder.keys()].sort((a, b) => a - b);
    expect(orders).toEqual([0, 1, 2]);
    const means = orders.map((o) => {
      const v = byOrder.get(o) as number[];
      return v.reduce((a, b) => a + b, 0) / v.length;
    });
    for (let i = 1; i < means.length; i += 1) {
      expect(means[i] as number).toBeLessThan(means[i - 1] as number);
    }
  });

  test("long low limbs droop while high limbs angle up", () => {
    const { root } = grow(star(4), { sag: 0.9, lengthGradient: 0.7 });
    const laterals = limbs(root)
      .filter((l) => l.order === 1)
      .sort((a, b) => a.from.position.y - b.from.position.y);
    expect(laterals.length).toBe(4);
    const rise = (l: Limb) => l.tip.position.y - l.from.position.y;
    expect(rise(laterals[0] as Limb)).toBeLessThan(0);
    expect(rise(laterals[laterals.length - 1] as Limb)).toBeGreaterThan(0);
  });

  test("a drooping limb eases into sagFloor instead of running flat along it", () => {
    const floor = crownBase + 1;
    for (const seed of [7, 21, 33, 44, 58, 61]) {
      const { root } = grow(
        star(1),
        { stepScale: 0.12, sag: 1, upBias: 0.3, lengthGradient: 0.1, sagFloor: floor },
        seed,
      );
      const limb = limbs(root).filter((l) => l.order === 1)[0] as Limb;
      const chain = [limb.from, ...limb.nodes];
      const dy = chain.slice(1).map((n, i) => n.position.y - (chain[i] as SkelNode).position.y);
      expect(dy.length).toBeGreaterThanOrEqual(12);
      const steepest = Math.min(...dy);
      expect(steepest).toBeLessThan(-0.03);

      const tail = dy.slice(Math.floor(dy.length * 0.67));
      const tailMean = tail.reduce((a, b) => a + b, 0) / tail.length;
      // Softening, not truncation: the approach is much shallower than the
      // steepest descent yet still descending. A position clamp would run the
      // limb dead flat along the floor, giving exactly zero here.
      expect(tailMean).toBeLessThan(0);
      expect(tailMean).toBeGreaterThan(steepest * 0.6);
      // no flat run against an invisible wall
      for (let i = 2; i < dy.length; i += 1) {
        const flat = [dy[i - 2], dy[i - 1], dy[i]].every((v) => Math.abs(v as number) < 1e-9);
        expect(flat).toBe(false);
      }
      // the hard clamp never had to fire: the limb asymptotes clear of the floor
      expect(Math.min(...chain.map((n) => n.position.y)) - floor).toBeGreaterThan(0.05);
    }
  });

  test("sag never drives a limb below sagFloor", () => {
    for (const seed of [11, 12, 13]) {
      const { root } = grow(deep(), { sag: 1, upBias: 0.2 }, seed);
      for (const n of walk(root)) {
        if (n.order === 0) continue;
        expect(n.position.y).toBeGreaterThanOrEqual(params.sagFloor - 1e-9);
      }
    }
  });

  test("limbs low in the crown outrun limbs near the apex at equal persistence", () => {
    const { root } = grow(star(4), { sag: 0.15 });
    const laterals = limbs(root)
      .filter((l) => l.order === 1)
      .sort((a, b) => a.from.position.y - b.from.position.y);
    expect(laterals.length).toBe(4);
    const lowest = laterals[0] as Limb;
    const highest = laterals[laterals.length - 1] as Limb;
    expect(lowest.length).toBeGreaterThan(highest.length);
  });

  test("limb length still ranks by cluster persistence", () => {
    const topo = topology([
      node(0, -1, 200, 0.9),
      node(1, 0, 100, 0.95),
      node(2, 0, 100, 0.05),
    ]);
    const { root } = grow(topo, { lengthGradient: 0, sag: 0.1 });
    const laterals = limbs(root).filter((l) => l.order === 1);
    expect(laterals.length).toBe(2);
    const byPersistence = laterals.sort((a, b) => a.from.position.y - b.from.position.y);
    // kids sort by mass then id, so id 1 (persistence 0.95) takes the low site
    expect((byPersistence[0] as Limb).length).toBeGreaterThan((byPersistence[1] as Limb).length);
  });

  test("every lobe tip sits within reach of its own sector", () => {
    const { root, lobes } = grow(deep());
    expect(lobes.length).toBe(4);
    const tips = new Set(walk(root));
    const draw = rng(99);
    for (const lobe of lobes) {
      expect(tips.has(lobe.tip)).toBe(true);
      expect(insideEnvelope(env, lobe.tip.position)).toBe(true);
      const dists: number[] = [];
      for (let i = 0; i < 300; i += 1) {
        const p = sampleLobe(env, lobe.azimuth, lobe.halfAngle, draw);
        dists.push(p.distanceTo(lobe.tip.position));
      }
      dists.sort((a, b) => a - b);
      // Stage 2 adds nothing at all if no attractor lands within di of a tip.
      // The nearest sector sample must therefore sit well inside the crown
      // scale, and a real share of the sector must be in range of a plausible
      // di, or twigs fail silently.
      expect(dists[0] as number).toBeLessThan(0.35 * env.radius);
      const inRange = dists.filter((d) => d <= 0.6 * env.radius).length;
      expect(inRange / dists.length).toBeGreaterThan(0.1);
    }
  });

  test("lobe sectors nest inside their parent's sector", () => {
    const { lobes } = grow(deep());
    for (const lobe of lobes) {
      expect(lobe.halfAngle).toBeGreaterThan(0);
      expect(lobe.halfAngle).toBeLessThanOrEqual(Math.PI);
    }
    const ids = lobes.map((l: Lobe) => l.clusterId).sort((a, b) => a - b);
    expect(ids).toEqual([3, 4, 5, 6]);
  });

  test("the same seed and topology yield an identical skeleton", () => {
    const fingerprint = (root: SkelNode) =>
      walk(root).map((n) => [
        n.position.x,
        n.position.y,
        n.position.z,
        n.dir.x,
        n.dir.y,
        n.dir.z,
        n.pathLength,
        n.order,
        n.radius,
        n.children.length,
      ]);
    const a = grow(deep(), {}, 4242);
    const b = grow(deep(), {}, 4242);
    expect(fingerprint(b.root)).toEqual(fingerprint(a.root));
    expect(b.lobes.map((l) => [l.clusterId, l.mass, l.azimuth, l.halfAngle])).toEqual(
      a.lobes.map((l) => [l.clusterId, l.mass, l.azimuth, l.halfAngle]),
    );
    const c = grow(deep(), {}, 4243);
    expect(fingerprint(c.root)).not.toEqual(fingerprint(a.root));
  });

  test("radius is left for stage 3 and pathLength accumulates", () => {
    const { root } = grow(deep());
    for (const n of walk(root)) {
      expect(n.radius).toBe(0);
      for (const c of n.children) expect(c.pathLength).toBeGreaterThan(n.pathLength);
    }
  });

  test.each([1, 2, 7, 40, 200])("respects a node budget of %i", (max) => {
    const { root } = grow(deep(), {}, 3, max);
    expect(walk(root).length).toBeLessThanOrEqual(Math.max(1, max));
  });

  test("degenerate topologies terminate and return something valid", () => {
    const single = grow(topology([node(0, -1, 1, 0)]));
    expect(walk(single.root).length).toBeGreaterThan(1);
    expect(single.lobes.length).toBe(1);
    expect(single.lobes[0]?.clusterId).toBe(0);

    const empty = grow(topology([]));
    expect(walk(empty.root).length).toBe(1);
    expect(empty.lobes.length).toBe(0);

    // a parent pointer cycle must not spin forever
    const cyclic = grow(topology([node(0, -1, 10, 0.5), node(1, 0, 5, 0.5), node(0, 1, 10, 0.5)]));
    expect(walk(cyclic.root).length).toBeGreaterThan(1);

    const zeroMass = grow(star(3, 0, 0));
    expect(walk(zeroMass.root).length).toBeGreaterThan(1);
    for (const n of walk(zeroMass.root)) expect(Number.isFinite(n.position.y)).toBe(true);
  });
});
