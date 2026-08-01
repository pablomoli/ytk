/* Pointer-drag camera state: target angles chase the pointer while down,
   coast on inertia after release, and settle on a critically damped spring —
   the lenis-style easing the reference names, without the dependency. */

export const SENS = 0.0022; // rad per px
export const PITCH_MAX = (75 * Math.PI) / 180;
const TAP_PX = 6;
const STIFFNESS = 60; // spring toward target; ~0.3s to settle
const FRICTION = 10; // exponential decay of thrown velocity; sim-checked, see task-7-report.md

export type OrbControls = {
  down(x: number, y: number): void;
  move(x: number, y: number): void;
  up(): { tap: boolean };
  wheel(dy: number): void;
  step(dt: number): { yaw: number; pitch: number };
  setTarget(yaw: number, pitch: number): void;
  readonly dragging: boolean;
};

export function createControls(): OrbControls {
  let yaw = 0, pitch = 0; // rendered angles
  let tyaw = 0, tpitch = 0; // spring targets
  let vyaw = 0, vpitch = 0; // throw velocity (rad/s), post-release only
  let dragging = false;
  let lastX = 0, lastY = 0, travel = 0;
  let lastDX = 0, lastDY = 0;
  let dtSinceMove = 0; // real elapsed time since the last move(), for velocity-on-release

  const clamp = () => { tpitch = Math.max(-PITCH_MAX, Math.min(PITCH_MAX, tpitch)); };

  return {
    get dragging() { return dragging; },
    down(x, y) {
      dragging = true;
      vyaw = vpitch = 0;
      lastX = x; lastY = y; travel = 0; lastDX = 0; lastDY = 0; dtSinceMove = 0;
    },
    move(x, y) {
      if (!dragging) return;
      lastDX = x - lastX; lastDY = y - lastY;
      travel += Math.hypot(lastDX, lastDY);
      lastX = x; lastY = y;
      // grab-the-wall on both axes, but the camera applies the two angles
      // differently (rotateY(-yaw) vs rotateX(pitch)), so the negation that
      // makes "drag right -> content right" true does NOT also make
      // "drag down -> content down" true: yaw is negated at input to cancel
      // the camera's own negation; pitch is not, since the camera has none.
      tyaw -= lastDX * SENS;
      tpitch += lastDY * SENS;
      clamp();
      dtSinceMove = 0; // velocity-on-release measures from here, not an assumed frame rate
    },
    up() {
      if (!dragging) return { tap: false };
      dragging = false;
      const tap = travel <= TAP_PX;
      // throw: last move's delta over actual elapsed time; no elapsed step() means
      // no time basis for a rate, so no velocity (avoids a div-by-zero spurious throw)
      if (!tap && dtSinceMove > 0) {
        vyaw = -(lastDX * SENS) / dtSinceMove;
        vpitch = (lastDY * SENS) / dtSinceMove; // same per-axis convention as move()
      }
      return { tap };
    },
    wheel(dy) { tyaw -= dy * SENS * 0.5; },
    setTarget(y, p) { tyaw = y; tpitch = p; vyaw = vpitch = 0; clamp(); },
    step(dt) {
      if (dragging) dtSinceMove += dt;
      if (!dragging) {
        const decay = Math.exp(-FRICTION * dt);
        tyaw += vyaw * dt; tpitch += vpitch * dt;
        vyaw *= decay; vpitch *= decay;
        clamp();
      }
      // critically damped approach of rendered angles toward targets
      const k = 1 - Math.exp(-STIFFNESS * dt);
      yaw += (tyaw - yaw) * k;
      pitch += (tpitch - pitch) * k;
      return { yaw, pitch };
    },
  };
}
