import { LAVA_GLSL } from "../galaxy/scene";

// the uniform objects every lava-riding shader holds in common: one clock, one state, one pull
export const LAVA_SHARED = ["uLavaTime", "uLavaCut", "uLavaA", "uLavaB", "uLavaShapeA", "uLavaShapeB", "uLavaPull"] as const;

// How a thing resting on the sphere is carried by the lava under it. Shared by the atlas tiles, the
// sharp quads drawn over the nearest ones and the pending grains, so all three move as one surface.
export const LAVA_RIDE = /* glsl */ `
uniform float uLavaPull; // 0..1: how far things have given in to the lava
${LAVA_GLSL}
// v turned by the shortest rotation that takes unit a to unit b
vec3 lavaTurn(vec3 v, vec3 a, vec3 b) {
  vec3 ax = cross(a, b);
  float s2 = dot(ax, ax);
  if (s2 < 1e-10) return v;
  return v * dot(a, b) + cross(ax, v) + ax * dot(ax, v) * (1.0 - dot(a, b)) / s2;
}
// where a thing resting at unit dir is carried to; ride = (lift as a share of the radius, size factor)
vec3 lavaCarry(vec3 dir, float amount, out vec2 ride) {
  // the pull sweeps from one pole to the other, and each thing overshoots as it gives in
  float k = clamp(uLavaPull * 1.5 - 0.25 * (dir.z + 1.0), 0.0, 1.0) - 1.0;
  k = (1.0 + 2.70158 * k * k * k + 1.70158 * k * k) * amount;
  vec3 ref = abs(dir.y) > 0.9 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0);
  vec3 t1 = normalize(cross(ref, dir)), t2 = cross(dir, t1);
  // uphill is inland: things crowd onto the land and leave the sea, at most 0.3 rad from rest
  float h0 = lavaNow(dir);
  vec2 climb = 0.16 * vec2(lavaNow(normalize(dir + 0.07 * t1)) - h0, lavaNow(normalize(dir + 0.07 * t2)) - h0) / 0.07;
  climb *= min(1.0, 0.3 / max(1e-4, length(climb)));
  // and a slow wander of their own, so nothing sits still even far from a coast
  vec3 q = dir * 1.6;
  float t = uLavaTime * 1.3;
  vec3 w = vec3(vnoise(q + vec3(t, 3.0, 0.0)), vnoise(q + vec3(17.0, t, 5.0)), vnoise(q + vec3(0.0, 29.0, t))) - 0.5;
  vec3 to = normalize(dir + k * (t1 * climb.x + t2 * climb.y + 0.45 * (w - dir * dot(w, dir))));
  float h = clamp(lavaNow(to), 0.2, 1.0);
  float land = smoothstep(0.44, 0.62, h);            // 0 at sea, 1 inland
  float crest = exp(-pow((h - 0.5) / 0.045, 2.0));   // 1 on the shoreline: a thing hops as a coast crosses it
  // land lifts off the sphere, sea stays put (lower would sink under the terrain) and shrinks
  ride = vec2(k * (0.05 * land + 0.035 * crest), mix(1.0, 0.6 + 0.52 * land + 0.22 * crest, k));
  return to;
}`;
