/* Inertial-pan math for the map camera — a technique port of the
   MapLibre release-velocity approach (algorithm only, no dependency).
   Pure and unit-tested; mapRenderer wires it to pointer events. */
export type VelocitySample = { x: number; y: number; t: number };

export function pushSample(buffer: VelocitySample[], sample: VelocitySample, windowMs = 90): void {
  buffer.push(sample);
  while (buffer.length && sample.t - buffer[0].t > windowMs) buffer.shift();
}

export function releaseVelocity(buffer: VelocitySample[]): { vx: number; vy: number } {
  if (buffer.length < 2) return { vx: 0, vy: 0 };
  const first = buffer[0];
  const last = buffer[buffer.length - 1];
  const span = last.t - first.t;
  if (span <= 0) return { vx: 0, vy: 0 };
  return { vx: (last.x - first.x) / span, vy: (last.y - first.y) / span };
}

export function decay(value: number, dt: number, k = 4): number {
  return value * Math.exp(-k * dt);
}
