import { PerspectiveCamera, Vector3 } from "three";

/* Tiles are shader-positioned quads, invisible to three's Raycaster; picking
   is ray-vs-plane per tile in JS — trivially cheap at the content-set scale. */

const UP = new Vector3(0, 1, 0);
const ALT = new Vector3(1, 0, 0);

// pickTile runs per pointermove; writes into caller-supplied vectors instead
// of allocating so the per-tile loop doesn't churn the GC at content-set scale.
function computeBasis(center: Vector3, outN: Vector3, outE1: Vector3, outE2: Vector3): void {
  outN.copy(center).negate().normalize(); // tiles face the origin
  const ref = Math.abs(outN.y) > 0.9 ? ALT : UP;
  outE1.crossVectors(ref, outN).normalize();
  outE2.crossVectors(outN, outE1);
}

const _origin = new Vector3();
const _dir = new Vector3();
const _c = new Vector3();
const _n = new Vector3();
const _e1 = new Vector3();
const _e2 = new Vector3();
const _hit = new Vector3();

export function pickTile(
  ndcX: number,
  ndcY: number,
  camera: PerspectiveCamera,
  centers: Float32Array,
  half: number,
): number | null {
  _origin.copy(camera.position);
  _dir.set(ndcX, ndcY, 0.5).unproject(camera).sub(_origin).normalize();
  let best: number | null = null;
  let bestT = Infinity;
  for (let i = 0; i * 3 < centers.length; i++) {
    _c.set(centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]);
    computeBasis(_c, _n, _e1, _e2);
    const denom = _dir.dot(_n);
    if (Math.abs(denom) < 1e-9) continue;
    const t = _hit.copy(_c).sub(_origin).dot(_n) / denom;
    if (t <= 0 || t >= bestT) continue;
    _hit.copy(_origin).addScaledVector(_dir, t).sub(_c);
    if (Math.abs(_hit.dot(_e1)) <= half && Math.abs(_hit.dot(_e2)) <= half) {
      best = i;
      bestT = t;
    }
  }
  return best;
}

export function tileScreenRect(
  camera: PerspectiveCamera,
  center: Vector3,
  half: number,
  vw: number,
  vh: number,
): DOMRect {
  const n = new Vector3();
  const e1 = new Vector3();
  const e2 = new Vector3();
  computeBasis(center, n, e1, e2);
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [a, b] of [[-1, -1], [1, -1], [1, 1], [-1, 1]] as const) {
    const corner = center.clone().addScaledVector(e1, a * half).addScaledVector(e2, b * half);
    corner.project(camera);
    const x = ((corner.x + 1) / 2) * vw;
    const y = ((1 - corner.y) / 2) * vh;
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  return new DOMRect(minX, minY, maxX - minX, maxY - minY);
}
