import { describe, expect, test } from "vite-plus/test";
import { Vector3 } from "three";
import { hashString } from "../growth/dna";
import type { BucketTopology, TopoNode } from "./datatree";
import { envelopeFor, insideEnvelope } from "./envelope";
import { growGardenTree, scaffoldBudget, type GrowthParams } from "./pipeline";
import { growScaffold } from "./scaffold";
import { rng } from "./tree";
import type { EnvelopeShape, SkelNode } from "./types";

const ORIGIN = new Vector3(0, 0, 0);

const shape: EnvelopeShape = {
  maxHeight: 10,
  spreadMin: 0.35,
  spreadMax: 1.1,
  trunkFraction: 0.35,
};

// twigStep is kept clear of stepScale * (0.7..1.3) so a node's distance from
// its parent alone says which stage placed it.
const STEP = 0.4;
const TWIG = 0.11;

const params: GrowthParams = {
  stepScale: STEP,
  stiffness: 0.55,
  noise: 0.12,
  upBias: 0.9,
  orderDecay: 0.35,
  sag: 0.7,
  sagFloor: 1.4,
  lengthGradient: 0.6,
  pipeExponent: 2.5,
  tipRadius: 0.012,
  twigStep: TWIG,
  attractorsPerNote: 6,
};

const node = (id: number, parent: number, mass: number, persistence = 0.5): TopoNode => ({
  id,
  parent,
  mass,
  persistence,
});

const topology = (name: string, nNotes: number, nodes: TopoNode[]): BucketTopology => ({
  bucket: name,
  n_notes: nNotes,
  nodes,
});

// three dendrogram levels: 2 first-order children, each with 2 of its own
const deep = (name = "deep", notes = 400): BucketTopology =>
  topology(name, notes, [
    node(0, -1, notes, 0.9),
    node(1, 0, notes * 0.55, 0.7),
    node(2, 0, notes * 0.45, 0.7),
    node(3, 1, notes * 0.3, 0.5),
    node(4, 1, notes * 0.25, 0.5),
    node(5, 2, notes * 0.25, 0.5),
    node(6, 2, notes * 0.2, 0.5),
  ]);

const flat = (name: string, notes: number, kids: number): BucketTopology =>
  topology(name, notes, [
    node(0, -1, notes, 0.8),
    ...Array.from({ length: kids }, (_, i) => node(i + 1, 0, notes / kids, 0.5)),
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

const twigChildren = (n: SkelNode): SkelNode[] =>
  n.children.filter((c) => Math.abs(c.position.distanceTo(n.position) - TWIG) < 1e-9);

// Everything colonize hung off this node, found by step length rather than by
// order: a scaffold fork and a twig fork are both order + 1.
const twigsBelow = (n: SkelNode): SkelNode[] => {
  const out: SkelNode[] = [];
  const stack = twigChildren(n);
  while (stack.length > 0) {
    const cur = stack.pop() as SkelNode;
    out.push(cur);
    stack.push(...twigChildren(cur));
  }
  return out;
};

const fingerprint = (root: SkelNode) =>
  walk(root).map((n) => [
    n.position.x,
    n.position.y,
    n.position.z,
    n.pathLength,
    n.order,
    n.radius,
    n.children.length,
  ]);

const grow = (
  topo: BucketTopology,
  over: Partial<GrowthParams> = {},
  seed = 7,
  maxNodes = 3000,
  maxNotes = 400,
) => growGardenTree(topo, maxNotes, shape, { ...params, ...over }, seed, ORIGIN, maxNodes);

describe("growGardenTree", () => {
  test("every lobe grows at least one twig", () => {
    for (const [topo, maxNotes] of [
      [deep(), 400],
      [flat("wide", 300, 6), 400],
      [flat("small", 9, 3), 400],
    ] as Array<[BucketTopology, number]>) {
      for (const seed of [1, 7, 23, 91]) {
        const budget = 3000;
        const { root, env } = growGardenTree(
          topo,
          maxNotes,
          shape,
          params,
          seed,
          ORIGIN,
          budget,
        );
        // Replay the scaffold on the same stream prefix to recover the lobes;
        // the pipeline draws them from rng(seed) before any twig is grown.
        const { lobes } = growScaffold(
          topo,
          envelopeFor(ORIGIN, topo.n_notes, maxNotes, shape),
          params,
          rng(seed),
          ORIGIN,
          scaffoldBudget(budget),
        );
        expect(lobes.length).toBeGreaterThan(0);
        const grown = new Map(walk(root).map((n) => [n.position.toArray().join(","), n]));
        const norm = (p: Vector3) => (p.y - env.center.y) / env.halfHeight;
        for (const lobe of lobes) {
          const seeds = lobe.seeds.map((s) => grown.get(s.position.toArray().join(",")));
          expect(seeds.length).toBeGreaterThan(0);
          for (const seed of seeds) {
            expect(seed).toBeDefined();
            expect(insideEnvelope(env, (seed as SkelNode).position)).toBe(true);
          }
          const twigs = seeds.flatMap((s) => twigsBelow(s as SkelNode));
          expect(twigs.length).toBeGreaterThan(0);
          // twigs run along the limb rather than bunching at its end: more than
          // one seed carries growth once the limb is longer than a single step
          const carrying = seeds.filter((s) => twigChildren(s as SkelNode).length > 0);
          expect(carrying.length).toBeGreaterThan(0);
          // and the cloud fills the limb's own height band: an unbanded cloud
          // spans the whole crown, so an apex lobe's twigs fall toward centre.
          const ys = seeds.map((s) => norm((s as SkelNode).position));
          const center = (Math.min(...ys) + Math.max(...ys)) / 2;
          const mean = twigs.reduce((a, t) => a + norm(t.position), 0) / twigs.length;
          expect(Math.abs(mean - center)).toBeLessThan(0.3);
        }
      }
    }
  });

  test("twigs distribute along a limb instead of bunching at its tip", () => {
    const budget = 3000;
    const seed = 7;
    const { root } = grow(deep(), {}, seed, budget);
    const { lobes } = growScaffold(
      deep(),
      envelopeFor(ORIGIN, 400, 400, shape),
      params,
      rng(seed),
      ORIGIN,
      scaffoldBudget(budget),
    );
    const grown = new Map(walk(root).map((n) => [n.position.toArray().join(","), n]));
    let carrying = 0;
    let total = 0;
    let atTip = 0;
    for (const lobe of lobes) {
      const seeds = lobe.seeds.map((s) => grown.get(s.position.toArray().join(",")) as SkelNode);
      carrying += seeds.filter((s) => twigChildren(s).length > 0).length;
      total += seeds.reduce((a, s) => a + twigsBelow(s).length, 0);
      atTip += twigsBelow(seeds[seeds.length - 1] as SkelNode).length;
    }
    // more growth points than limbs, and the limb ends do not hold the bulk
    expect(carrying).toBeGreaterThan(lobes.length);
    expect(atTip).toBeLessThan(total * 0.8);
  });

  test("a single-node dendrogram still branches", () => {
    const { root } = grow(topology("solo", 23, [node(0, -1, 23, 0.4)]));
    const orders = new Set(walk(root).map((n) => n.order));
    expect(orders.has(1)).toBe(true);
    // the trunk forks: a bare stalk with a puff has exactly one child chain
    const forks = walk(root).filter((n) => n.order === 0 && n.children.length > 1);
    expect(forks.length).toBeGreaterThan(1);
  });

  test("twigs stay inside the crown envelope", () => {
    const { root, env } = grow(deep());
    const twigs = walk(root).filter((n) => twigChildren(n).length > 0);
    expect(twigs.length).toBeGreaterThan(4);
    for (const parent of twigs) {
      for (const twig of twigChildren(parent)) {
        // colonize steps toward an attractor inside the ellipsoid, so a twig
        // may overshoot by at most one step past the surface.
        const scaled = new Vector3(
          (twig.position.x - env.center.x) / (env.radius + TWIG),
          (twig.position.y - env.center.y) / (env.halfHeight + TWIG),
          (twig.position.z - env.center.z) / (env.radius + TWIG),
        );
        expect(scaled.length()).toBeLessThanOrEqual(1 + 1e-9);
      }
    }
  });

  test("Murray's law holds at every fork and tips carry the tip radius", () => {
    const { root } = grow(deep());
    const n = params.pipeExponent;
    let forks = 0;
    for (const node_ of walk(root)) {
      if (node_.children.length === 0) {
        expect(node_.radius).toBeCloseTo(params.tipRadius, 12);
        continue;
      }
      if (node_.children.length === 1) {
        expect(node_.radius).toBe((node_.children[0] as SkelNode).radius);
        continue;
      }
      forks += 1;
      const sum = node_.children.reduce((a, c) => a + Math.pow(c.radius, n), 0);
      expect(Math.pow(node_.radius, n)).toBeCloseTo(sum, 9);
    }
    expect(forks).toBeGreaterThan(5);
  });

  test("the trunk thickens with the twigs it carries, not with the scaffold alone", () => {
    // Both ends stay under the node budget: past ~3 per note the cloud is
    // denser than the kill distance can consume and tip count stops rising.
    const sparse = grow(deep(), { attractorsPerNote: 0.1 });
    const dense = grow(deep(), { attractorsPerNote: 3 });
    expect(walk(dense.root).length).toBeGreaterThan(walk(sparse.root).length);
    expect(dense.root.radius).toBeGreaterThan(sparse.root.radius);
  });

  test("a bigger bucket gets a thicker trunk at equal tip radius", () => {
    const radii = [12, 60, 400].map((notes) => {
      const { root, env } = grow(deep("b", notes), {}, 7, 3000, 400);
      return { r: root.radius, h: env.center.y + env.halfHeight };
    });
    for (let i = 1; i < radii.length; i += 1) {
      expect((radii[i] as { h: number }).h).toBeGreaterThan((radii[i - 1] as { h: number }).h);
      expect((radii[i] as { r: number }).r).toBeGreaterThan((radii[i - 1] as { r: number }).r);
    }
  });

  test("the same seed and topology yield an identical skeleton", () => {
    const a = grow(deep(), {}, 4242);
    const b = grow(deep(), {}, 4242);
    expect(fingerprint(b.root)).toEqual(fingerprint(a.root));
    const c = grow(deep(), {}, 4243);
    expect(fingerprint(c.root)).not.toEqual(fingerprint(a.root));
  });

  test("one bucket's note count does not disturb the other buckets", () => {
    // Per-bucket seeding, as the scene derives it. maxNotes is held fixed by
    // editing a bucket that is not the largest: the envelope ramp is measured
    // against the biggest bucket, so moving that one legitimately moves all.
    const gardenSeed = 11;
    const plant = (buckets: BucketTopology[]) =>
      buckets.map((b) =>
        fingerprint(
          growGardenTree(
            b,
            900,
            shape,
            params,
            (hashString(b.bucket) ^ gardenSeed) >>> 0,
            ORIGIN,
            2400,
          ).root,
        ),
      );
    const before = plant([deep("alpha", 900), deep("beta", 120), flat("gamma", 40, 4)]);
    const after = plant([deep("alpha", 900), deep("beta", 121), flat("gamma", 40, 4)]);
    expect(after[0]).toEqual(before[0]);
    expect(after[2]).toEqual(before[2]);
    expect(after[1]).not.toEqual(before[1]);
  });

  test("respects the node budget", () => {
    for (const budget of [200, 800, 3000]) {
      const { root } = grow(deep(), {}, 5, budget);
      expect(walk(root).length).toBeLessThanOrEqual(budget);
      expect(walk(root).length).toBeGreaterThan(budget * 0.3);
    }
  });

  test("degenerate topologies terminate and still produce a girthed tree", () => {
    const single = grow(topology("one", 1, [node(0, -1, 1, 0)]));
    expect(walk(single.root).length).toBeGreaterThan(1);
    expect(single.root.radius).toBeGreaterThan(0);

    const empty = grow(topology("none", 0, []));
    expect(walk(empty.root).length).toBe(1);
    expect(empty.root.radius).toBeCloseTo(params.tipRadius, 12);

    const zeroMass = grow(topology("zero", 0, [node(0, -1, 0, 0), node(1, 0, 0, 0)]));
    for (const n of walk(zeroMass.root)) expect(Number.isFinite(n.radius)).toBe(true);
  });
});
