import { PerspectiveCamera, Vector3 } from "three";

/* Tiles are shader-positioned quads, invisible to three's Raycaster; picking
   is ray-vs-plane per tile in JS. 505 tiles is trivially cheap per frame. */

const UP = new Vector3(0, 1, 0);
const ALT = new Vector3(1, 0, 0);

function basis(center: Vector3): { n: Vector3; e1: Vector3; e2: Vector3 } {
  const n = center.clone().negate().normalize(); // tiles face the origin
  const ref = Math.abs(n.y) > 0.9 ? ALT : UP;
  const e1 = new Vector3().crossVectors(ref, n).normalize();
  const e2 = new Vector3().crossVectors(n, e1);
  return { n, e1, e2 };
}

export function pickTile(
  ndcX: number,
  ndcY: number,
  camera: PerspectiveCamera,
  centers: Float32Array,
  half: number,
): number | null {
  const origin = camera.position.clone();
  const dir = new Vector3(ndcX, ndcY, 0.5).unproject(camera).sub(origin).normalize();
  let best: number | null = null;
  let bestT = Infinity;
  const c = new Vector3();
  for (let i = 0; i * 3 < centers.length; i++) {
    c.set(centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]);
    const { n, e1, e2 } = basis(c);
    const denom = dir.dot(n);
    if (Math.abs(denom) < 1e-9) continue;
    const t = c.clone().sub(origin).dot(n) / denom;
    if (t <= 0 || t >= bestT) continue;
    const hit = origin.clone().addScaledVector(dir, t).sub(c);
    if (Math.abs(hit.dot(e1)) <= half && Math.abs(hit.dot(e2)) <= half) {
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
  const { e1, e2 } = basis(center);
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
