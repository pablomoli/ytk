import { PerspectiveCamera, Vector3 } from "three";
import { worldRadius, type V3 } from "./math";

const _origin = new Vector3();
const _dir = new Vector3();
const _oc = new Vector3();

// Analytic ray-sphere: |O + t*D - C|^2 = r^2, D unit-length so a = 1.
// Nearest positive t wins; a hit with t <= 0 is behind the camera.
export function pickPlanet(
  ndcX: number,
  ndcY: number,
  camera: PerspectiveCamera,
  planets: { pos: V3; radius_deg: number }[],
): number | null {
  _origin.copy(camera.position);
  _dir.set(ndcX, ndcY, 0.5).unproject(camera).sub(_origin).normalize();
  let best: number | null = null;
  let bestT = Infinity;
  for (let i = 0; i < planets.length; i++) {
    const { pos, radius_deg } = planets[i];
    _oc.set(pos[0], pos[1], pos[2]).sub(_origin);
    const b = _oc.dot(_dir);
    const r = worldRadius(radius_deg);
    const c = _oc.dot(_oc) - r * r;
    const disc = b * b - c;
    if (disc < 0) continue;
    const sqrtDisc = Math.sqrt(disc);
    const t0 = b - sqrtDisc;
    const t1 = b + sqrtDisc;
    const t = t0 > 0 ? t0 : t1;
    if (t <= 0 || t >= bestT) continue;
    best = i;
    bestT = t;
  }
  return best;
}
