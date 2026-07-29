// Stage 0 of the garden pipeline: the crown envelope every later stage grows
// inside. Pure math, no scene and no WebGL.
import { Vector3 } from "three";
import type { Envelope, EnvelopeShape } from "./types";

// A zero-note bucket must still render as something, so height and radius are
// floored rather than allowed to collapse to a degenerate ellipsoid.
const MIN_HEIGHT_FRACTION = 0.18;
const MIN_DIMENSION = 1e-4;

// Rejection sampling is bounded so a caller can never hang on a pathological
// RNG; past this the last candidate is pulled inside the sphere instead.
const MAX_REJECTIONS = 32;
// Accepting strictly below 1 leaves headroom for the ellipsoid round-trip, so
// insideEnvelope cannot fail on a point this module just produced.
const ACCEPT_LIMIT = 0.999999;

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);

export function envelopeFor(
  origin: Vector3,
  nNotes: number,
  maxNotes: number,
  shape: EnvelopeShape,
): Envelope {
  const cap = Math.max(1, maxNotes);
  const n = Math.max(0, nNotes);
  // sqrt rather than log: it is already normalised to [0,1] against the
  // largest bucket, needs no offset at n = 0, and compresses the head of the
  // distribution without flattening the middle the way log does.
  const t = clamp01(Math.sqrt(Math.min(n, cap) / cap));

  const height = Math.max(
    MIN_DIMENSION,
    shape.maxHeight * (MIN_HEIGHT_FRACTION + (1 - MIN_HEIGHT_FRACTION) * t),
  );
  const trunkHeight = height * clamp01(shape.trunkFraction);
  const halfHeight = Math.max(MIN_DIMENSION, (height - trunkHeight) / 2);
  const spread = shape.spreadMin + (shape.spreadMax - shape.spreadMin) * t;
  const radius = Math.max(MIN_DIMENSION, spread * halfHeight);

  return {
    center: new Vector3(origin.x, origin.y + trunkHeight + halfHeight, origin.z),
    radius,
    halfHeight,
  };
}

export function insideEnvelope(env: Envelope, p: Vector3): boolean {
  const x = (p.x - env.center.x) / env.radius;
  const y = (p.y - env.center.y) / env.halfHeight;
  const z = (p.z - env.center.z) / env.radius;
  return x * x + y * y + z * z <= 1;
}

// Uniform inside the unit sphere by rejection; the fallback rescales the last
// candidate onto a shell just inside the surface.
function unitBallPoint(rand: () => number): Vector3 {
  let x = 0;
  let y = 0;
  let z = 0;
  for (let i = 0; i < MAX_REJECTIONS; i += 1) {
    x = rand() * 2 - 1;
    y = rand() * 2 - 1;
    z = rand() * 2 - 1;
    if (x * x + y * y + z * z <= ACCEPT_LIMIT) return new Vector3(x, y, z);
  }
  const len = Math.sqrt(x * x + y * y + z * z);
  if (len === 0) return new Vector3(0, 0, 0);
  const s = 0.99 / len;
  return new Vector3(x * s, y * s, z * s);
}

const toEnvelope = (env: Envelope, u: Vector3): Vector3 =>
  new Vector3(
    env.center.x + u.x * env.radius,
    env.center.y + u.y * env.halfHeight,
    env.center.z + u.z * env.radius,
  );

export function sampleEnvelope(env: Envelope, rand: () => number): Vector3 {
  return toEnvelope(env, unitBallPoint(rand));
}

export function sampleLobe(
  env: Envelope,
  azimuth: number,
  halfAngle: number,
  rand: () => number,
): Vector3 {
  const u = unitBallPoint(rand);
  const half = Math.min(Math.PI, Math.max(0, halfAngle));
  // The unit ball is azimuthally isotropic, so replacing the azimuth with a
  // uniform draw over the sector stays uniform and keeps the radius — and so
  // containment — untouched, whatever the sector does at +/-PI.
  const horizontal = Math.hypot(u.x, u.z);
  const a = azimuth + (rand() * 2 - 1) * half;
  return toEnvelope(env, new Vector3(horizontal * Math.cos(a), u.y, horizontal * Math.sin(a)));
}
