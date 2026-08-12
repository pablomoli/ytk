// Pure geometry for the galaxy scene. No three.js imports: plain number
// tuples keep this unit-testable without a WebGL context.
export type V3 = [number, number, number];

const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));

const len3 = (v: V3) => Math.hypot(v[0], v[1], v[2]);

const normalize = (v: V3): V3 => {
  const l = len3(v);
  return l > 0 ? [v[0] / l, v[1] / l, v[2] / l] : v;
};

const dot3 = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

const cross3 = (a: V3, b: V3): V3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];

export const worldRadius = (radiusDeg: number) => Math.sin((radiusDeg * Math.PI) / 180);

// seconds-per-rotation = clamp(medianAgeDays, 20, 600): a 24-day world turns
// in 24s, a 380-day world is near-still. Falls back to the population median
// before clamping when this planet has no median age of its own.
export const spinRadPerSec = (medianAgeDays: number | null, populationMedian: number) => {
  const days = medianAgeDays ?? populationMedian;
  const secondsPerRot = clamp(days, 20, 600);
  return (2 * Math.PI) / secondsPerRot;
};

// Must match ytk/coast.py's grid(): xyz = (cos(lat)cos(lon), cos(lat)sin(lon), sin(lat)).
// flipY interplay with the three.js texture upload is resolved where the
// texture is bound (Task 10), not here.
// This is the BAKE contract, and what the shader samples under uYUp=0 (orb's
// coast sphere); galaxy planets take uYUp=1, a y-up swizzle off this frame.
export const equirectUv = (n: V3): [number, number] => {
  const u = Math.atan2(n[1], n[0]) / (2 * Math.PI) + 0.5;
  const v = 0.5 + Math.asin(clamp(n[2], -1, 1)) / Math.PI;
  return [u, v];
};

// Default tilt is 30deg from the radial (center) direction toward the
// component of `partner` tangent to that radial.
export const ringNormal = (center: V3, partner: V3, tiltRad: number = Math.PI / 6): V3 => {
  const radial = normalize(center);
  const d = dot3(partner, radial);
  const tangentRaw: V3 = [partner[0] - d * radial[0], partner[1] - d * radial[1], partner[2] - d * radial[2]];
  // partner parallel/antiparallel to radial: tangent is undefined, so pick a
  // deterministic axis not aligned with radial (same pattern as
  // ytk/spheremap.py lattice()'s degenerate-centroid fallback).
  const tangent =
    len3(tangentRaw) > 1e-9 ? normalize(tangentRaw) : normalize(cross3(radial, Math.abs(radial[2]) > 0.9 ? [1, 0, 0] : [0, 0, 1]));
  const c = Math.cos(tiltRad);
  const s = Math.sin(tiltRad);
  return [radial[0] * c + tangent[0] * s, radial[1] * c + tangent[1] * s, radial[2] * c + tangent[2] * s];
};

// Visit camera position: pushed outward along the planet's radial by 3.2x its
// angular (world) radius beyond the sphere surface.
export const standoff = (center: V3, radiusDeg: number): V3 => {
  const k = 1 + 3.2 * worldRadius(radiusDeg);
  return [center[0] * k, center[1] * k, center[2] * k];
};

// Rotation about the gray axis in RGB, row-major 3x3 (arm 0, #179). The
// (1-cos)/3 and sqrt(1/3)*sin terms are the closed form of conjugating a
// rotation into the plane normal to (1,1,1): the gray axis is fixed, so a
// sample's distance from gray survives and only its direction turns.
export const hueRotationMatrix = (deg: number): number[] => {
  const a = (deg * Math.PI) / 180;
  const c = Math.cos(a);
  const s = Math.sin(a);
  const d = (1 - c) / 3;
  const k = Math.sqrt(1 / 3) * s;
  return [c + d, d - k, d + k, d + k, c + d, d - k, d - k, d + k, c + d];
};

// Unit-vector slerp for travel arcs. Falls back to lerp+normalize when a and
// b are near-parallel, where the slerp basis is degenerate.
export const slerp = (a: V3, b: V3, t: number): V3 => {
  const cosTheta = clamp(dot3(normalize(a), normalize(b)), -1, 1);
  if (cosTheta > 0.9995) {
    const lerped: V3 = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
    return normalize(lerped);
  }
  const theta = Math.acos(cosTheta);
  const sinTheta = Math.sin(theta);
  const wa = Math.sin((1 - t) * theta) / sinTheta;
  const wb = Math.sin(t * theta) / sinTheta;
  return [a[0] * wa + b[0] * wb, a[1] * wa + b[1] * wb, a[2] * wa + b[2] * wb];
};
