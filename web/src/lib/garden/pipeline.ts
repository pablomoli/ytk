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
// Half-width of the attractor latitude band, in normalised ellipsoid y. Wider
// and an apex lobe's cloud drifts out of its own tip's attraction radius.
const BAND_HALF = 0.3;
const MIN_TWIG_NODES = 24;
const MIN_ATTRACTORS = 12;
// di as a fraction of crown radius, and its floor in steps. Too small and a
// lobe silently grows nothing; colonize reports that as zero, not as an error.
const ATTRACT_FRACTION = 0.5;
const ATTRACT_STEPS = 8;
const KILL_STEPS = 2;
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

// Node budget per lobe, by note mass, floored so no lobe ends bare and scaled
// back down if the floors together overrun what is left.
function twigBudgets(lobes: Lobe[], available: number): number[] {
  if (lobes.length === 0) return [];
  let total = 0;
  for (const lobe of lobes) total += Math.max(0, lobe.mass);
  const raw = lobes.map((lobe) => {
    const share = total > 0 ? Math.max(0, lobe.mass) / total : 1 / lobes.length;
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
  const budgets = twigBudgets(lobes, Math.max(0, budget - countNodes(root)));
  for (let i = 0; i < lobes.length; i += 1) {
    const lobe = lobes[i] as Lobe;
    const nodeBudget = budgets[i] as number;
    // The band follows the tip's own height in the crown; a lobe whose
    // attractors span the whole ellipsoid grows nothing at all.
    const center = (lobe.tip.position.y - env.center.y) / env.halfHeight;
    const count = Math.min(
      Math.max(MIN_ATTRACTORS, nodeBudget * 2),
      Math.max(MIN_ATTRACTORS, Math.round(params.attractorsPerNote * Math.max(0, lobe.mass))),
    );
    const attractors = Array.from({ length: count }, () =>
      sampleLobe(env, lobe.azimuth, lobe.halfAngle, rand, { center, half: BAND_HALF }),
    );
    colonize([lobe.tip], {
      attractors,
      step,
      killDistance: KILL_STEPS * step,
      attractDistance,
      maxNodes: nodeBudget,
      rand,
      jitter: JITTER_STEPS * step,
    });
  }

  // Last, over the finished skeleton: the trunk's radius is the sum of what it
  // ends up carrying, so a twig grown after this pass would never reach it.
  applyMurrayGirth(root, Math.max(1e-5, params.tipRadius), Math.max(1.2, params.pipeExponent));
  return { root, env };
}
