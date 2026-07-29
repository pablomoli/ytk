import { Vector3 } from "three";
import { describe, expect, test } from "vite-plus/test";
import { envelopeFor, insideEnvelope, sampleEnvelope, sampleLobe } from "./envelope";
import { rng } from "./tree";
import type { EnvelopeShape } from "./types";

const SHAPE: EnvelopeShape = {
  maxHeight: 12,
  spreadMin: 0.35,
  spreadMax: 1.1,
  trunkFraction: 0.3,
};

const ORIGIN = new Vector3(0, 0, 0);
const MAX_NOTES = 240;
const spreadOf = (n: number): number => {
  const env = envelopeFor(ORIGIN, n, MAX_NOTES, SHAPE);
  return env.radius / env.halfHeight;
};
const apexOf = (n: number): number => {
  const env = envelopeFor(ORIGIN, n, MAX_NOTES, SHAPE);
  return env.center.y + env.halfHeight;
};

// signed smallest angle between two azimuths, so a sector straddling +/-PI is
// judged by rotation and not by raw atan2 values
const angleDelta = (a: number, b: number): number => Math.atan2(Math.sin(a - b), Math.cos(a - b));

describe("envelopeFor", () => {
  test("a large bucket is taller and proportionally broader than a small one", () => {
    const small = envelopeFor(ORIGIN, 4, MAX_NOTES, SHAPE);
    const large = envelopeFor(ORIGIN, MAX_NOTES, MAX_NOTES, SHAPE);
    expect(apexOf(MAX_NOTES)).toBeGreaterThan(apexOf(4));
    expect(large.radius).toBeGreaterThan(small.radius);
    expect(large.radius / large.halfHeight).toBeGreaterThan(small.radius / small.halfHeight);
  });

  test("height scales sub-linearly with note count", () => {
    const one = apexOf(1);
    const quarter = apexOf(MAX_NOTES / 4);
    const full = apexOf(MAX_NOTES);
    // quadrupling the bucket must add less than four times the height gain
    expect(full - one).toBeLessThan(4 * (quarter - one));
  });

  test("spread is monotone in note count and stays within the ramp", () => {
    let previous = -Infinity;
    for (let n = 0; n <= MAX_NOTES; n += 1) {
      const spread = spreadOf(n);
      expect(spread).toBeGreaterThanOrEqual(previous - 1e-12);
      expect(spread).toBeGreaterThanOrEqual(SHAPE.spreadMin - 1e-12);
      expect(spread).toBeLessThanOrEqual(SHAPE.spreadMax + 1e-12);
      previous = spread;
    }
    expect(spreadOf(0)).toBeCloseTo(SHAPE.spreadMin, 10);
    expect(spreadOf(MAX_NOTES)).toBeCloseTo(SHAPE.spreadMax, 10);
    // counts above the largest bucket clamp rather than overshoot the ramp
    expect(spreadOf(MAX_NOTES * 3)).toBeCloseTo(SHAPE.spreadMax, 10);
  });

  test("empty and single-note buckets stay positive and finite", () => {
    for (const n of [0, 1]) {
      const env = envelopeFor(ORIGIN, n, MAX_NOTES, SHAPE);
      expect(env.radius).toBeGreaterThan(0);
      expect(env.halfHeight).toBeGreaterThan(0);
      expect(Number.isFinite(env.radius)).toBe(true);
      expect(Number.isFinite(env.halfHeight)).toBe(true);
      expect(Number.isFinite(env.center.y)).toBe(true);
      expect(env.center.y).toBeGreaterThan(0);
    }
  });

  test("the crown sits above a bare trunk anchored at the origin", () => {
    const origin = new Vector3(3, 0, -2);
    const env = envelopeFor(origin, 100, MAX_NOTES, SHAPE);
    expect(env.center.x).toBe(3);
    expect(env.center.z).toBe(-2);
    const total = env.center.y + env.halfHeight;
    expect(env.center.y - env.halfHeight).toBeCloseTo(total * SHAPE.trunkFraction, 8);
  });
});

describe("sampleEnvelope", () => {
  test("every sample lands inside the envelope", () => {
    const env = envelopeFor(ORIGIN, 90, MAX_NOTES, SHAPE);
    const rand = rng(1337);
    for (let i = 0; i < 400; i += 1) {
      expect(insideEnvelope(env, sampleEnvelope(env, rand))).toBe(true);
    }
  });

  test("samples fill the envelope rather than hugging the centre", () => {
    const env = envelopeFor(ORIGIN, 90, MAX_NOTES, SHAPE);
    const rand = rng(7);
    let far = 0;
    for (let i = 0; i < 400; i += 1) {
      const p = sampleEnvelope(env, rand);
      const x = (p.x - env.center.x) / env.radius;
      const y = (p.y - env.center.y) / env.halfHeight;
      const z = (p.z - env.center.z) / env.radius;
      if (Math.sqrt(x * x + y * y + z * z) > 0.5) far += 1;
    }
    expect(far).toBeGreaterThan(200);
  });

  test("a degenerate one-note envelope still samples inside itself", () => {
    const env = envelopeFor(ORIGIN, 1, MAX_NOTES, SHAPE);
    const rand = rng(5);
    for (let i = 0; i < 100; i += 1) {
      expect(insideEnvelope(env, sampleEnvelope(env, rand))).toBe(true);
    }
  });
});

describe("sampleLobe", () => {
  const env = envelopeFor(ORIGIN, 120, MAX_NOTES, SHAPE);

  test("samples stay inside the envelope and inside the sector", () => {
    const azimuth = 0.8;
    const halfAngle = 0.4;
    const rand = rng(99);
    for (let i = 0; i < 400; i += 1) {
      const p = sampleLobe(env, azimuth, halfAngle, rand);
      expect(insideEnvelope(env, p)).toBe(true);
      const a = Math.atan2(p.z - env.center.z, p.x - env.center.x);
      expect(Math.abs(angleDelta(a, azimuth))).toBeLessThanOrEqual(halfAngle + 1e-9);
    }
  });

  test("a sector straddling +/-PI wraps correctly", () => {
    const azimuth = Math.PI - 0.05;
    const halfAngle = 0.3;
    const rand = rng(2024);
    let below = 0;
    let above = 0;
    for (let i = 0; i < 400; i += 1) {
      const p = sampleLobe(env, azimuth, halfAngle, rand);
      expect(insideEnvelope(env, p)).toBe(true);
      const a = Math.atan2(p.z - env.center.z, p.x - env.center.x);
      expect(Math.abs(angleDelta(a, azimuth))).toBeLessThanOrEqual(halfAngle + 1e-9);
      if (a > 0) above += 1;
      else below += 1;
    }
    // the sector spans the branch cut, so both signs of atan2 must be hit
    expect(above).toBeGreaterThan(0);
    expect(below).toBeGreaterThan(0);
  });

  test("a full-circle lobe is not narrower than the sector allows", () => {
    const rand = rng(11);
    let maxDelta = 0;
    for (let i = 0; i < 300; i += 1) {
      const p = sampleLobe(env, 0, Math.PI, rand);
      const a = Math.atan2(p.z - env.center.z, p.x - env.center.x);
      maxDelta = Math.max(maxDelta, Math.abs(angleDelta(a, 0)));
    }
    expect(maxDelta).toBeGreaterThan(2.5);
  });
});

describe("determinism", () => {
  test("the same seed yields identical envelope samples", () => {
    const env = envelopeFor(ORIGIN, 77, MAX_NOTES, SHAPE);
    const a = rng(4242);
    const b = rng(4242);
    for (let i = 0; i < 200; i += 1) {
      expect(sampleEnvelope(env, a).toArray()).toEqual(sampleEnvelope(env, b).toArray());
    }
  });

  test("the same seed yields identical lobe samples, and a different seed does not", () => {
    const env = envelopeFor(ORIGIN, 77, MAX_NOTES, SHAPE);
    const a = rng(8);
    const b = rng(8);
    const c = rng(9);
    const first = sampleLobe(env, 1.2, 0.5, a);
    expect(first.toArray()).toEqual(sampleLobe(env, 1.2, 0.5, b).toArray());
    expect(first.toArray()).not.toEqual(sampleLobe(env, 1.2, 0.5, c).toArray());
  });
});

describe("sampleLobe height band", () => {
  const env = envelopeFor(new Vector3(0, 0, 0), 400, 400, SHAPE);

  test("band keeps samples near the requested latitude and inside the ellipsoid", () => {
    const rand = rng(4242);
    const band = { center: 0.7, half: 0.15 };
    for (let i = 0; i < 400; i += 1) {
      const p = sampleLobe(env, 0.8, 0.5, rand, band);
      expect(insideEnvelope(env, p)).toBe(true);
      const yNorm = (p.y - env.center.y) / env.halfHeight;
      expect(yNorm).toBeGreaterThanOrEqual(band.center - band.half - 1e-6);
      expect(yNorm).toBeLessThanOrEqual(Math.min(1, band.center + band.half) + 1e-6);
    }
  });

  test("an apex band never returns points from the crown floor", () => {
    const rand = rng(99);
    let lowest = Infinity;
    for (let i = 0; i < 400; i += 1) {
      const p = sampleLobe(env, -2.1, 0.4, rand, { center: 0.85, half: 0.12 });
      lowest = Math.min(lowest, p.y);
    }
    expect(lowest).toBeGreaterThan(env.center.y);
  });

  test("omitting the band leaves the original full-height behaviour", () => {
    const a = rng(7);
    const b = rng(7);
    for (let i = 0; i < 50; i += 1) {
      const p = sampleLobe(env, 1.1, 0.3, a);
      const q = sampleLobe(env, 1.1, 0.3, b);
      expect(p.x).toBe(q.x);
      expect(p.y).toBe(q.y);
    }
  });
});
