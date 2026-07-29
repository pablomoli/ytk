// Shared types for the garden generator pipeline. Stages 0-3 are pure: no
// scene, no WebGL, no DOM. Vector3 is used only as a math type.
import type { Vector3 } from "three";

export type SkelNode = {
  position: Vector3;
  // unit heading the limb was travelling when this node was placed
  dir: Vector3;
  // distance from the root along the skeleton, not straight-line
  pathLength: number;
  // 0 on the trunk, +1 on each lateral child; the axis the tropism gradient
  // reads so outer branches stop being re-aimed vertical
  order: number;
  // world radius, filled by applyMurrayGirth; 0 until then
  radius: number;
  children: SkelNode[];
};

export const makeNode = (
  position: Vector3,
  dir: Vector3,
  pathLength = 0,
  order = 0,
): SkelNode => ({ position, dir, pathLength, order, radius: 0, children: [] });

// Crown envelope: an oblate ellipsoid seated above a bare trunk. Horizontal
// semi-axis is `radius` on both x and z, vertical semi-axis is `halfHeight`.
export type Envelope = {
  center: Vector3;
  radius: number;
  halfHeight: number;
};

export type EnvelopeShape = {
  // world height of the largest bucket's crown apex
  maxHeight: number;
  // horizontal-to-vertical ratio at the smallest and largest bucket; the ramp
  // between them keeps a seedling from being a scaled-down mature tree
  spreadMin: number;
  spreadMax: number;
  // fraction of total height that is bare trunk below the crown
  trunkFraction: number;
};

export type ColonizeOptions = {
  attractors: Vector3[];
  // D: one growth step
  step: number;
  // dk: an attractor within this distance of any node is consumed
  killDistance: number;
  // di: a node only sees attractors within this distance
  attractDistance: number;
  maxNodes: number;
  rand: () => number;
  // optional lateral wobble per step, in world units
  jitter?: number;
  // optional upward tilt added to each step, as a fraction of `step`
  upBias?: number;
  // steps a limb of the given branch order must run before it may fork
  bareRun?: (order: number) => number;
  // cosine spread past which a node's attractors are two branches, by order;
  // higher splits more readily, so fine twigs fork on a narrower divergence
  splitCos?: (order: number) => number;
  // internode length by branch order, defaulting to `step` at every order
  stepFor?: (order: number) => number;
};
