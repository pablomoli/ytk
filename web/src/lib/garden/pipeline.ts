// Composes stages 0-3 into one tree: envelope, measured scaffold, colonized
// twigs, then girth. Pure math, no scene and no WebGL.
import type { Vector3 } from "three";
import type { BucketTopology } from "./datatree";
import { envelopeFor, sampleLobe } from "./envelope";
import { applyMurrayGirth } from "./girth";
import { growScaffold, type Lobe, type ScaffoldParams } from "./scaffold";
import { rng } from "./tree";
import { colonize } from "./twigs";
import type { Envelope, EnvelopeShape, SkelNode } from "./types";

export type GrowthParams = ScaffoldParams & {
  pipeExponent: number;
  tipRadius: number;
  twigStep: number; // D, one space-colonization step
  attractorsPerNote: number;
};

// Share of the node budget the measured scaffold may spend. The remainder is
// twigs, which carry the fine structure the shallow dendrogram cannot.
export const SCAFFOLD_SHARE = 0.3;
export const scaffoldBudget = (maxNodes: number): number =>
  Math.max(32, Math.floor(Math.max(2, Math.floor(maxNodes)) * SCAFFOLD_SHARE));
// Attractor latitude band, in normalised ellipsoid y: it follows the limb's own
// height span, padded so a level limb does not get a flat plate of foliage.
const BAND_PAD = 0.18;
const BAND_HALF_MIN = 0.36;
// Wider and an apex lobe's cloud drifts out of its own limb's attraction radius.
const BAND_HALF_MAX = 0.45;
// Radial half-width around the limb's own span, in normalised crown radius.
const RADIAL_PAD = 0.18;
// Sector half-width nests one division per dendrogram level, so a depth-2 lobe
// gets 0.07 rad and its cloud is a plane. Floored so a twig mass has volume.
const MIN_LOBE_HALF = 0.35;
const MIN_TWIG_NODES = 24;
const MIN_ATTRACTORS = 12;
// di as a fraction of crown radius, and its floor in steps. Too small and a
// lobe silently grows nothing; colonize reports that as zero, not as an error.
const ATTRACT_FRACTION = 0.5;
const ATTRACT_STEPS = 8;
const KILL_STEPS = 2;
// Twigs per attractor. Uncapped, a stalled lobe eats the whole node budget:
// the same 90 attractors measured 40 nodes on one seed and 600 on the next.
const NODES_PER_ATTRACTOR = 2;
const JITTER_STEPS = 0.12;

const countNodes = (root: SkelNode): number => {
  let n = 0;
  const stack: SkelNode[] = [root];
  while (stack.length > 0) {
    const node = stack.pop() as SkelNode;
    n += 1;
    for (const child of node.children) stack.push(child);
  }
  return n;
};

// Sub-linear in note mass, renormalised to the same total. A linear share gave
// epicmap's two heaviest lobes 76% of the twigs and left the apex a wisp.
const MASS_EXPONENT = 0.5;
function foliageMasses(lobes: Lobe[]): number[] {
  let total = 0;
  let weighted = 0;
  const w = lobes.map((lobe) => {
    const m = Math.max(0, lobe.mass);
    total += m;
    const v = Math.pow(m, MASS_EXPONENT);
    weighted += v;
    return v;
  });
  if (weighted <= 0) return w.map(() => 0);
  const k = total / weighted;
  return w.map((v) => v * k);
}

// Node budget per lobe, by foliage mass, floored so no lobe ends bare and
// scaled back down if the floors together overrun what is left.
function twigBudgets(masses: number[], available: number): number[] {
  if (masses.length === 0) return [];
  let total = 0;
  for (const m of masses) total += Math.max(0, m);
  const raw = masses.map((m) => {
    const share = total > 0 ? Math.max(0, m) / total : 1 / masses.length;
    return Math.max(MIN_TWIG_NODES, Math.round(available * share));
  });
  const sum = raw.reduce((a, b) => a + b, 0);
  const scale = sum > available ? available / sum : 1;
  return raw.map((v) => Math.max(1, Math.floor(v * scale)));
}

export function growGardenTree(
  topo: BucketTopology,
  maxNotes: number,
  shape: EnvelopeShape,
  params: GrowthParams,
  seed: number,
  origin: Vector3,
  maxNodes: number,
): { root: SkelNode; env: Envelope } {
  const env = envelopeFor(origin, topo.n_notes, maxNotes, shape);
  const rand = rng(seed);
  const budget = Math.max(2, Math.floor(maxNodes));
  const { root, lobes } = growScaffold(
    topo,
    env,
    params,
    rand,
    origin,
    scaffoldBudget(budget),
  );

  const step = Math.max(1e-4, params.twigStep);
  const attractDistance = Math.max(ATTRACT_FRACTION * env.radius, ATTRACT_STEPS * step);
  const masses = foliageMasses(lobes);
  const budgets = twigBudgets(masses, Math.max(0, budget - countNodes(root)));
  for (let i = 0; i < lobes.length; i += 1) {
    const lobe = lobes[i] as Lobe;
    const nodeBudget = budgets[i] as number;
    const seeds = lobe.seeds.length > 0 ? lobe.seeds : [lobe.tip];
    // The band follows the limb's own height span; a lobe whose attractors
    // span the whole ellipsoid grows nothing at all.
    let lo = Infinity;
    let hi = -Infinity;
    let rLo = Infinity;
    let rHi = -Infinity;
    for (const seed of seeds) {
      const y = (seed.position.y - env.center.y) / env.halfHeight;
      if (y < lo) lo = y;
      if (y > hi) hi = y;
      const r =
        Math.hypot(seed.position.x - env.center.x, seed.position.z - env.center.z) / env.radius;
      if (r < rLo) rLo = r;
      if (r > rHi) rHi = r;
    }
    const center = (lo + hi) / 2;
    const half = Math.min(BAND_HALF_MAX, Math.max(BAND_HALF_MIN, (hi - lo) / 2 + BAND_PAD));
    const radial = { min: rLo - RADIAL_PAD, max: rHi + RADIAL_PAD };
    const count = Math.min(
      Math.max(MIN_ATTRACTORS, nodeBudget * 2),
      Math.max(MIN_ATTRACTORS, Math.round(params.attractorsPerNote * (masses[i] as number))),
    );
    const attractors = Array.from({ length: count }, () =>
      sampleLobe(
        env,
        lobe.azimuth,
        Math.max(MIN_LOBE_HALF, lobe.halfAngle),
        rand,
        { center, half },
        radial,
      ),
    );
    colonize(seeds, {
      attractors,
      step,
      killDistance: KILL_STEPS * step,
      attractDistance,
      maxNodes: Math.min(nodeBudget, Math.ceil(count * NODES_PER_ATTRACTOR)),
      rand,
      jitter: JITTER_STEPS * step,
    });
  }

  // Last, over the finished skeleton: the trunk's radius is the sum of what it
  // ends up carrying, so a twig grown after this pass would never reach it.
  applyMurrayGirth(root, Math.max(1e-5, params.tipRadius), Math.max(1.2, params.pipeExponent));
  return { root, env };
}
