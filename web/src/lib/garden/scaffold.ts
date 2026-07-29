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
const FORK_BAND_START = 0.1;
// Weight of even spacing against cumulative mass when siting forks; pure mass
// drives the lowest fork half way up, pure even spacing stacks the heaviest.
const EVEN_WEIGHT = 0.6;
// Fraction of the crown half-height above centre the trunk climbs to. The top
// fork sits on the trunk's last node, so this also sets the crown's apex.
const TRUNK_TOP = 0.85;
// Limb length ranks on log persistence rescaled over the bucket's own range:
// the raw ratio is dominated by one outlier and squashes every other cluster.
const PERSIST_FLOOR = 0.25;
const PERSIST_EPS = 1e-6;
// A tip on the crown axis has no meaningful azimuth, so its sector stops
// bounding where stage 2 scatters attractors.
const MIN_RADIAL_SHARE = 0.4;
// Bare run before a limb carries anything, as a fraction of its own length.
// Falls with order: the further out, the sooner a real branch starts branching.
const BARE_BASE = 0.45;
const BARE_DECAY = 0.5;
const MAX_SEEDS = 6;
// Pseudo-lobes for a one-node dendrogram. Thresholds are note counts, so a
// two-note bucket does not get the branch count of a twenty-note one.
const SYNTH_STEP_A = 8;
const SYNTH_STEP_B = 24;
// Share of the radius still left at a fork that the strongest sibling takes.
// Below 1 so a limb stops short of the envelope wall rather than skidding it.
const LIMB_FILL = 0.85;

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);
const clampSlope = (v: number): number =>
  v < -CLIMB_MAX ? -CLIMB_MAX : v > CLIMB_MAX ? CLIMB_MAX : v;

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
  // point inside the envelope the limb climbs toward; null on the trunk
  target: Vector3 | null;
};

// Rise per unit outward run the limb aims for. 1 launches at 45 degrees from
// vertical; the envelope shell caps it wherever there is less headroom.
const CLIMB_RATIO = 1.5;
// Cap on the aim slope, so a limb forking just under the shell does not launch
// vertical and stall against it on its first step.
const CLIMB_MAX = 2;
// Exponent on the sag ramp that fades the climb out. The first step is at ramp
// zero either way, so this shapes the arc without touching the launch angle.
const CLIMB_FADE = 3;
// Share of the climb a limb at the crown base still gets; the apex gets all.
const CLIMB_LOW = 0.27;
// Fraction of a limb over which sag reaches full strength. Past the midpoint
// the order gradient lifts the inner half faster than droop overtakes it.
const SAG_RAMP = 0.25;
// Band above sagFloor, as a fraction of crown half-height, over which the net
// downward pull eases out. Clamping position instead reads as clipping.
const FLOOR_BAND = 0.3;

const smoothstep = (t: number): number => t * t * (3 - 2 * t);

export const bareFraction = (order: number): number =>
  BARE_BASE * Math.pow(BARE_DECAY, Math.max(0, order - 1));

// Evenly spaced nodes over the limb's outer span, tip always included.
const limbSeeds = (chain: SkelNode[], order: number): SkelNode[] => {
  if (chain.length === 0) return [];
  // Measured over the gaps, not the nodes: on a three-node limb the node form
  // hands over a single seed, which is a tenth of the limb rather than 0.6.
  const tail = chain.slice(Math.max(0, Math.floor((chain.length - 1) * bareFraction(order))));
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
  let pLo = Infinity;
  let pHi = -Infinity;
  for (const n of topo.nodes) {
    const p = Math.max(PERSIST_EPS, n.persistence);
    if (p < pLo) pLo = p;
    if (p > pHi) pHi = p;
  }
  const logLo = Math.log(pLo);
  const logSpan = Math.log(pHi) - logLo;
  // A bucket whose clusters share one persistence carries no ranking to read,
  // so every limb takes the top of the range rather than a zero-span NaN.
  const persistenceRank = (p: number): number =>
    logSpan > 1e-9
      ? PERSIST_FLOOR +
        (1 - PERSIST_FLOOR) *
          clamp01((Math.log(Math.max(PERSIST_EPS, p)) - logLo) / logSpan)
      : 1;
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
      // Slope of the line from here to the aim point. `outward` is a unit
      // horizontal, so this scalar is literally the tangent of the climb angle.
      let climb = 0;
      if (spec.target) {
        const run = Math.hypot(spec.target.x - from3.x, spec.target.z - from3.z);
        // Fades on the same ramp that raises the droop: a persistent climb
        // outpulls sag for the whole limb and no limb ever comes back down.
        climb =
          clampSlope((spec.target.y - from3.y) / Math.max(1e-6, run)) *
          Math.pow(1 - ramp, CLIMB_FADE);
      }
      // One signed scalar carries all three tropisms; adding opposed unit
      // vectors would cancel to noise at the crossover.
      let vertical = upPull + climb - droop;
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
    steps: Math.max(
      2,
      Math.ceil((env.center.y + env.halfHeight * TRUNK_TOP - origin.y) / stepScale),
    ),
    length: Math.max(stepScale, env.center.y + env.halfHeight * TRUNK_TOP - origin.y),
    target: null,
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
        seeds: limbSeeds(chain, order),
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
        : chain.slice(Math.floor(chain.length * bareFraction(order)));
    const sites = candidates.length > 0 ? candidates : [tip];
    const childHalf = halfAngle / kids.length;

    // Children are sorted mass-descending, so even spacing alone stacks the
    // heaviest ones adjacent and the crown reads as blobs.
    let kidTotal = 0;
    for (const kid of kids) kidTotal += Math.max(0, kid.mass);
    let cumulative = 0;
    const fractions = kids.map((kid, i) => {
      const m = Math.max(0, kid.mass);
      const massFraction = kidTotal > 0 ? (cumulative + m / 2) / kidTotal : (i + 0.5) / kids.length;
      cumulative += m;
      const evenFraction = kids.length === 1 ? 0 : i / (kids.length - 1);
      return EVEN_WEIGHT * evenFraction + (1 - EVEN_WEIGHT) * massFraction;
    });
    const siteFor = (i: number): SkelNode =>
      sites[
        Math.round(clamp01(fractions[i] as number) * (sites.length - 1))
      ] as SkelNode;
    const bandFor = (n: SkelNode): number =>
      clamp01((n.position.y - forkBase) / Math.max(1e-6, crownTop - forkBase));
    // Rank first, scale second. The three factors are each below 1, so their
    // raw product left every limb a stub a quarter of the crown radius long.
    const scores = kids.map((kid, i) => {
      const heightFactor = 1 - lengthGradient * bandFor(siteFor(i));
      const share = Math.min(1, Math.max(MIN_RADIAL_SHARE, Math.sqrt(kid.mass / rootMass)));
      return heightFactor * share * persistenceRank(kid.persistence);
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
          seeds: limbSeeds(chain, order),
          azimuth,
          halfAngle,
        });
        continue;
      }
      const childAzimuth =
        order === 0 ? i * GOLDEN : azimuth + childHalf * (2 * i + 1 - kids.length);
      const site = siteFor(i);
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
      const targetRadius = Math.min(env.radius, startRadial + reach);
      // Aim at a point, not a direction: the shell height at the limb's own
      // target radius is what stops the climb, so no order settles flat.
      const shellY =
        env.center.y +
        env.halfHeight * Math.sqrt(Math.max(0, 1 - Math.pow(targetRadius / env.radius, 2)));
      // Climb follows the height band: an old low limb is plagiotropic, and a
      // steep launch there outpulls its own sag load for the whole limb.
      const rise = CLIMB_RATIO * reach * (CLIMB_LOW + (1 - CLIMB_LOW) * bandFor(site));
      const target = new Vector3(
        env.center.x + targetRadius * Math.cos(childAzimuth),
        Math.max(site.position.y, Math.min(shellY, site.position.y + rise)),
        env.center.z + targetRadius * Math.sin(childAzimuth),
      );
      const spec: LimbSpec = {
        order: order + 1,
        azimuth: childAzimuth,
        targetRadius,
        // Slack over the straight-line reach: a drooping or noisy limb walks a
        // longer path than it spans, and must not run out of steps first.
        steps: Math.max(2, Math.ceil((reach * 1.8) / stepScale)),
        length: reach,
        target,
      };
      const startDir = target.clone().sub(site.position);
      if (startDir.lengthSq() < 1e-12) startDir.set(Math.cos(childAzimuth), 0.5, Math.sin(childAzimuth));
      startDir.normalize();
      const grown = growLimb(site, startDir, spec);
      walk(kid, grown.length > 0 ? grown : [site], childAzimuth, childHalf, order + 1, seen);
    }
  };

  walk(rootTopo, trunk.length > 0 ? trunk : [root], 0, Math.PI, 0, new Set([rootTopo.id]));
  return { root, lobes };
}
