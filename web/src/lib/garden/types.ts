// Shared types for the garden generator pipeline. Stages 0-3 are pure: no
// scene, no WebGL, no DOM. Vector3 is used only as a math type.
//
// Girth is absent from generation on purpose. It is a single bottom-up pass
// after the skeleton exists (stage 3), so a limb's radius follows from what it
// carries rather than from how deep it sits.
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
  // horizontal-to-vertical ratio at the smallest and largest bucket. The ramp
  // between them is what separates a seedling from a scaled-down mature tree:
  // juvenile crowns are narrow and vertical, spread lags height.
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
};
