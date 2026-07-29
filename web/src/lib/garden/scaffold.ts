// Stage 1: the measured skeleton, from the dendrogram. Pure math, no scene
// and no WebGL.
import { Vector3 } from "three";
import type { BucketTopology, TopoNode } from "./datatree";
import { insideEnvelope } from "./envelope";
import { makeNode, type Envelope, type SkelNode } from "./types";

export type ScaffoldParams = {
  stepScale: number;
  stiffness: number; // 0-1, resistance to direction change
  noise: number;
  upBias: number; // base gravitropism, before the order gradient
  orderDecay: number; // 0-1, per-order falloff of upward pull
  sag: number; // 0-1, strength of the gravity droop
  sagFloor: number; // min world y a sagging limb may reach
  lengthGradient: number; // 0-1, how much limb length falls with height
};

export type Lobe = {
  clusterId: number;
  mass: number;
  tip: SkelNode; // the limb's end
  // nodes along the limb's outer span that stage 2 grows from; seeding only
  // from the tip bunches every twig into one ball at the limb's end
  seeds: SkelNode[];
  azimuth: number; // sector centre, radians
  halfAngle: number; // sector half-width
};

export type ScaffoldResult = { root: SkelNode; lobes: Lobe[] };

const GOLDEN = 2.399963;
// Canopy stays above ground; retained from the previous generator.
const GROUND_EPS = 0.03;
// The ellipsoid's horizontal semi-axis is zero at its base, so a limb forking
// lower than this leaves the envelope on its first step.
const FORK_BAND_START = 0.25;
// A tip on the crown axis has no meaningful azimuth, so its sector stops
// bounding where stage 2 scatters attractors.
const MIN_RADIAL_SHARE = 0.4;
// Outer fraction of a limb that carries twigs, and how many seeds are taken
// from it. The inner span stays bare, as on a real branch.
const SEED_SPAN = 0.6;
const MAX_SEEDS = 6;
// Pseudo-lobes for a one-node dendrogram. Thresholds are note counts, so a
// two-note bucket does not get the branch count of a twenty-note one.
const SYNTH_STEP_A = 8;
const SYNTH_STEP_B = 24;
// Share of the radius still left at a fork that the strongest sibling takes.
// Below 1 so a limb stops short of the envelope wall rather than skidding it.
const LIMB_FILL = 0.85;

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);

const randomUnit = (rand: () => number): Vector3 => {
  const z = rand() * 2 - 1;
  const a = rand() * Math.PI * 2;
  const r = Math.sqrt(Math.max(0, 1 - z * z));
  return new Vector3(r * Math.cos(a), z, r * Math.sin(a));
};

type LimbSpec = {
  order: number;
  azimuth: number;
  // world horizontal distance from the crown axis the limb grows toward; 0
  // means the trunk, which has no lateral target
  targetRadius: number;
  steps: number;
  // planned world length; the sag load and ramp are both measured against it
  length: number;
};

// Fraction of a limb over which sag reaches full strength. Past the midpoint
// the order gradient lifts the inner half faster than droop overtakes it.
const SAG_RAMP = 0.25;
// Band above sagFloor, as a fraction of crown half-height, over which the net
// downward pull eases out. Clamping position instead reads as clipping.
const FLOOR_BAND = 0.3;

const smoothstep = (t: number): number => t * t * (3 - 2 * t);

// Evenly spaced nodes over the limb's outer span, tip always included.
const limbSeeds = (chain: SkelNode[]): SkelNode[] => {
  if (chain.length === 0) return [];
  const tail = chain.slice(Math.max(0, Math.floor(chain.length * (1 - SEED_SPAN))));
  if (tail.length <= MAX_SEEDS) return tail;
  return Array.from(
    { length: MAX_SEEDS },
    (_, i) => tail[Math.round((i * (tail.length - 1)) / (MAX_SEEDS - 1))] as SkelNode,
  );
};

export function growScaffold(
  topo: BucketTopology,
  env: Envelope,
  params: ScaffoldParams,
  rand: () => number,
  origin: Vector3,
  maxNodes: number,
): ScaffoldResult {
  const root = makeNode(origin.clone(), new Vector3(0, 1, 0), 0, 0);
  const lobes: Lobe[] = [];
  const rootTopo = topo.nodes.find((n) => n.parent === -1) ?? topo.nodes[0];
  if (!rootTopo) return { root, lobes };

  const stepScale = Math.max(1e-4, params.stepScale);
  const stiffness = clamp01(params.stiffness);
  const orderDecay = clamp01(params.orderDecay);
  const sag = clamp01(params.sag);
  const lengthGradient = clamp01(params.lengthGradient);
  const crownBase = env.center.y - env.halfHeight;
  const crownTop = env.center.y + env.halfHeight;
  const crownSpan = Math.max(1e-6, 2 * env.halfHeight);
  const forkBase = crownBase + FORK_BAND_START * crownSpan;
  const groundY = origin.y + GROUND_EPS;
  const floorBand = Math.max(4 * stepScale, FLOOR_BAND * env.halfHeight);

  const byParent = new Map<number, TopoNode[]>();
  for (const n of topo.nodes) {
    if (n.parent === -1) continue;
    const kids = byParent.get(n.parent);
    if (kids) kids.push(n);
    else byParent.set(n.parent, [n]);
  }
  let maxPersistence = 1e-6;
  for (const n of topo.nodes) maxPersistence = Math.max(maxPersistence, n.persistence);
  const rootMass = Math.max(1, rootTopo.mass);

  // A one-node dendrogram measures no structure to contradict, and without
  // pseudo-lobes it renders as a bare stalk carrying a single attractor cloud.
  if (topo.nodes.length === 1 && !byParent.has(rootTopo.id)) {
    const count = rootTopo.mass >= SYNTH_STEP_B ? 5 : rootTopo.mass >= SYNTH_STEP_A ? 4 : 3;
    byParent.set(
      rootTopo.id,
      Array.from({ length: count }, (_, i) => ({
        id: rootTopo.id + 1 + i,
        parent: rootTopo.id,
        mass: Math.max(0, rootTopo.mass) / count,
        persistence: rootTopo.persistence,
      })),
    );
  }

  let budget = Math.max(0, maxNodes - 1);

  // The bare trunk below the crown is outside the ellipsoid by construction, so
  // containment only binds once growth has entered the envelope.
  const allowed = (p: Vector3, order: number): boolean =>
    insideEnvelope(env, p) || (order === 0 && p.y < crownBase);

  const growLimb = (from: SkelNode, startDir: Vector3, spec: LimbSpec): SkelNode[] => {
    const chain: SkelNode[] = [];
    let node = from;
    let direction = startDir.clone();
    if (direction.lengthSq() < 1e-12) direction.set(0, 1, 0);
    direction.normalize();
    const startPath = from.pathLength;
    const outward = new Vector3(Math.cos(spec.azimuth), 0, Math.sin(spec.azimuth));
    const upPull = params.upBias * Math.pow(orderDecay, spec.order);

    for (let i = 0; i < spec.steps && budget > 0; i += 1) {
      const from3 = node.position;
      const radial = Math.hypot(from3.x - env.center.x, from3.z - env.center.z);
      if (spec.targetRadius > 0 && radial >= spec.targetRadius) break;

      const limbLength = node.pathLength - startPath;
      const height = clamp01((from3.y - crownBase) / crownSpan);
      // Absolute length, not a fraction of the limb: normalising per limb would
      // give every limb full-strength sag at its tip, apex twigs included.
      const ramp = clamp01(limbLength / Math.max(1e-6, SAG_RAMP * env.radius));
      // The trunk carries the crown; drooping it would fold the whole tree.
      const droop = spec.order === 0 ? 0 : sag * ramp * (1 - height);
      // One signed scalar carries both tropisms; adding two opposed unit
      // vectors would cancel to noise at the crossover.
      let vertical = upPull - droop;
      // Soft floor: the downward pull dies off as the limb nears sagFloor, so
      // it eases into a shallow curve on its own and never has to be cut.
      if (vertical < 0) vertical *= smoothstep(clamp01((from3.y - params.sagFloor) / floorBand));

      const desired = new Vector3(0, vertical, 0)
        .addScaledVector(outward, spec.targetRadius > 0 ? 1 : 0)
        .addScaledVector(randomUnit(rand), params.noise * 0.8);
      if (desired.lengthSq() < 1e-12) desired.copy(direction);
      desired.normalize();

      direction = direction
        .clone()
        .multiplyScalar(stiffness)
        .addScaledVector(desired, 1 - stiffness);
      if (direction.lengthSq() < 1e-12) direction.set(0, 1, 0);
      direction.normalize();

      const step = direction.clone().multiplyScalar(stepScale * (0.7 + rand() * 0.6));
      const position = from3.clone().add(step);

      if (position.y < groundY) {
        position.y = groundY + Math.abs(position.y - origin.y) * 0.3;
        direction.y = Math.abs(direction.y) * 0.5;
        if (direction.lengthSq() < 1e-12) direction.set(0, 1, 0);
        direction.normalize();
      }
      // Safety net only: the soft floor above keeps the pull off the limb, so
      // this fires only if noise alone carries a step through the floor.
      if (spec.order > 0 && position.y < params.sagFloor) position.y = params.sagFloor;
      if (!allowed(position, spec.order)) break;

      const child = makeNode(
        position,
        direction.clone(),
        node.pathLength + position.distanceTo(from3),
        spec.order,
      );
      node.children.push(child);
      chain.push(child);
      node = child;
      budget -= 1;
    }
    return chain;
  };

  const trunkSpec: LimbSpec = {
    order: 0,
    azimuth: 0,
    targetRadius: 0,
    steps: Math.max(2, Math.ceil((env.center.y + env.halfHeight * 0.6 - origin.y) / stepScale)),
    length: Math.max(stepScale, env.center.y + env.halfHeight * 0.6 - origin.y),
  };
  const trunk = growLimb(root, new Vector3(0, 1, 0), trunkSpec);

  const walk = (
    node: TopoNode,
    chain: SkelNode[],
    azimuth: number,
    halfAngle: number,
    order: number,
    seen: Set<number>,
  ): void => {
    const tip = chain[chain.length - 1] as SkelNode;
    const kids = (byParent.get(node.id) ?? [])
      .filter((k) => !seen.has(k.id))
      .sort((a, b) => b.mass - a.mass || a.id - b.id);
    if (kids.length === 0) {
      lobes.push({
        clusterId: node.id,
        mass: node.mass,
        tip,
        seeds: limbSeeds(chain),
        azimuth,
        halfAngle,
      });
      return;
    }

    // Fork sites spread along the parent limb, heaviest child lowest: the
    // crown then tapers instead of every limb leaving one knuckle.
    const candidates =
      order === 0
        ? chain.filter((n) => n.position.y >= forkBase)
        : chain.slice(Math.floor(chain.length * 0.35));
    const sites = candidates.length > 0 ? candidates : [tip];
    const childHalf = halfAngle / kids.length;

    const siteFor = (i: number): SkelNode =>
      sites[
        kids.length === 1 ? 0 : Math.round((i * (sites.length - 1)) / (kids.length - 1))
      ] as SkelNode;
    const bandFor = (n: SkelNode): number =>
      clamp01((n.position.y - forkBase) / Math.max(1e-6, crownTop - forkBase));
    // Rank first, scale second. The three factors are each below 1, so their
    // raw product left every limb a stub a quarter of the crown radius long.
    const scores = kids.map((kid, i) => {
      const heightFactor = 1 - lengthGradient * bandFor(siteFor(i));
      const share = Math.min(1, Math.max(MIN_RADIAL_SHARE, Math.sqrt(kid.mass / rootMass)));
      return heightFactor * share * (0.35 + kid.persistence / maxPersistence);
    });
    const bestScore = Math.max(1e-9, ...scores);

    for (let i = 0; i < kids.length; i += 1) {
      const kid = kids[i] as TopoNode;
      seen.add(kid.id);
      if (budget <= 0) {
        lobes.push({
          clusterId: kid.id,
          mass: kid.mass,
          tip,
          seeds: limbSeeds(chain),
          azimuth,
          halfAngle,
        });
        continue;
      }
      const childAzimuth =
        order === 0 ? i * GOLDEN : azimuth + childHalf * (2 * i + 1 - kids.length);
      const site = siteFor(i);
      const band = bandFor(site);
      // Measured from the fork, not from the crown axis: an absolute target
      // sits behind any second-order fork, which then breaks on its first step.
      const startRadial = Math.hypot(site.position.x - env.center.x, site.position.z - env.center.z);
      const headroom = Math.max(0, env.radius - startRadial);
      // One reach, not two: an independent step budget and radial target let
      // whichever bound first cut the limb short and starve the sag ramp.
      const reach = Math.max(
        env.radius * 0.15,
        headroom * LIMB_FILL * ((scores[i] as number) / bestScore),
      );
      const spec: LimbSpec = {
        order: order + 1,
        azimuth: childAzimuth,
        targetRadius: Math.min(env.radius, startRadial + reach),
        // Slack over the straight-line reach: a drooping or noisy limb walks a
        // longer path than it spans, and must not run out of steps first.
        steps: Math.max(2, Math.ceil((reach * 1.8) / stepScale)),
        length: reach,
      };
      // Launch angle follows the height band: a limb low in the crown leaves
      // the trunk near-horizontal so the droop has nothing to undo first.
      const startDir = new Vector3(
        Math.cos(childAzimuth),
        0.12 + 0.55 * band,
        Math.sin(childAzimuth),
      ).normalize();
      const grown = growLimb(site, startDir, spec);
      walk(kid, grown.length > 0 ? grown : [site], childAzimuth, childHalf, order + 1, seen);
    }
  };

  walk(rootTopo, trunk.length > 0 ? trunk : [root], 0, Math.PI, 0, new Set([rootTopo.id]));
  return { root, lobes };
}
