export const growthVertex = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`;

// Gray-Scott reaction-diffusion. State: r = chemical A (substrate),
// g = chemical B (pattern), b = activity (recent perturbation),
// a = growth domain. The reaction only lives inside the domain; each note's
// droplet expands the domain locally, so the silhouette itself is the record
// of growth. Old pattern is never re-seeded — growth stays incremental.
export const growthUpdateFragment = `
precision highp float;
varying vec2 vUv;
uniform sampler2D uState;
uniform vec2 uTexel;
uniform vec2 uFrom;
uniform vec2 uTo;
uniform float uRadius;
uniform float uProgress;
uniform float uSeed;
uniform float uActive;
uniform float uCopy;
uniform float uFeed;
uniform float uKill;
uniform float uDiffA;
uniform float uDiffB;
uniform float uStipple; // per-texel feed/kill irregularity

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x),
             mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0)), f.x), f.y);
}

void main() {
  vec4 state = texture2D(uState, vUv);
  if (uCopy > 0.5) {
    gl_FragColor = state;
    return;
  }

  vec4 n  = texture2D(uState, vUv + vec2(0.0,  uTexel.y));
  vec4 s  = texture2D(uState, vUv - vec2(0.0,  uTexel.y));
  vec4 e  = texture2D(uState, vUv + vec2(uTexel.x, 0.0));
  vec4 w  = texture2D(uState, vUv - vec2(uTexel.x, 0.0));
  vec4 ne = texture2D(uState, vUv + uTexel);
  vec4 sw = texture2D(uState, vUv - uTexel);
  vec4 nw = texture2D(uState, vUv + vec2(-uTexel.x, uTexel.y));
  vec4 se = texture2D(uState, vUv + vec2(uTexel.x, -uTexel.y));

  vec2 lap = (n.rg + s.rg + e.rg + w.rg) * 0.2
           + (ne.rg + sw.rg + nw.rg + se.rg) * 0.05
           - state.rg;

  float A = state.r;
  float B = state.g;

  float domain = state.a;
  // Smoothed domain edge so the silhouette stays organic, not stamped.
  float domainSoft = (n.a + s.a + e.a + w.a) * 0.25;
  float dm = smoothstep(0.12, 0.55, max(domain, domainSoft));

  // STIPPLE roughens the parameter field so patterns grow irregular.
  float wobble = (noise(vUv * 9.0 + uSeed * 0.01) - 0.5) * uStipple;
  // Outside the domain the reaction starves: no feed, elevated kill.
  float feed = uFeed * (1.0 + wobble * 0.35) * dm;
  float kill = (uKill + (1.0 - dm) * 0.025) * (1.0 + wobble * 0.2);

  float reaction = A * B * B;
  A += uDiffA * lap.x - reaction + feed * (1.0 - A);
  B += uDiffB * lap.y + reaction - (kill + feed) * B;

  float activity = state.b * 0.985;

  if (uActive > 0.5) {
    float eased = 0.5 - 0.5 * cos(clamp(uProgress, 0.0, 1.0) * 3.14159265);
    vec2 tip = mix(uFrom, uTo, eased);
    float d = length((vUv - tip) / uRadius);
    float droplet = exp(-d * d * 3.0);
    float grain = noise(vUv * 40.0 + vec2(uSeed * 0.017, uSeed * 0.013));
    B = max(B, droplet * (0.5 + 0.5 * grain) * 0.9);
    A = min(A, 1.0 - droplet * 0.5);
    activity = max(activity, droplet);
    // The domain expands wider than the droplet, with a ragged noise edge.
    float dd = length((vUv - tip) / (uRadius * 2.4));
    float ragged = 0.75 + 0.5 * noise(vUv * 17.0 + uSeed * 0.07);
    domain = max(domain, exp(-dd * dd * 2.0) * ragged);
  }

  gl_FragColor = clamp(vec4(A, B, activity, domain), 0.0, 1.0);
}`;

// Dithered palette-quantized display. The pattern field is shaded into the
// five content-derived palette roles through an ordered-dither threshold —
// quantization is the aesthetic, applied per screen pixel, so the image is
// crisp at any canvas size regardless of simulation resolution.
export const growthRenderFragment = `
precision highp float;
varying vec2 vUv;
uniform sampler2D uState;
uniform vec2 uTexel;
uniform float uTime;
uniform float uAspect;
uniform float uPulse;
uniform vec3 uPalette0; // deep field
uniform vec3 uPalette1; // low tissue
uniform vec3 uPalette2; // high tissue
uniform vec3 uPalette3; // vessel highlight
uniform vec3 uPalette4; // membrane / brightest
uniform vec3 uOpsA; // DEEPEN, BUD, LACE
uniform vec3 uOpsB; // STIPPLE, BLEED, MEMBRANE
uniform float uGlowMax;
uniform float uAbstraction; // 0 = full dither, 1 = smooth shaded
uniform float uDitherScale; // dither cell size in device pixels

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

// Xor's recursive Bayer construction: 2x2 base refined to 8x8.
float bayer2(vec2 a) {
  a = floor(a);
  return fract(a.x / 2.0 + a.y * a.y * 0.75);
}
float bayer8(vec2 a) {
  return bayer2(a / 4.0) * 0.0625 + bayer2(a / 2.0) * 0.25 + bayer2(a);
}

vec3 paletteRamp(float t) {
  t = clamp(t, 0.0, 1.0) * 4.0;
  vec3 c = mix(uPalette0, uPalette1, clamp(t, 0.0, 1.0));
  c = mix(c, uPalette2, clamp(t - 1.0, 0.0, 1.0));
  c = mix(c, uPalette3, clamp(t - 2.0, 0.0, 1.0));
  c = mix(c, uPalette4, clamp(t - 3.0, 0.0, 1.0));
  return c;
}

void main() {
  float fit = max(1.0, uAspect / 1.45);
  vec2 q = vec2((vUv.x - 0.5) * fit + 0.5, vUv.y);
  bool outside = q.x < 0.0 || q.x > 1.0 || q.y < 0.0 || q.y > 1.0;
  vec4 state = outside ? vec4(1.0, 0.0, 0.0, 1.0) : texture2D(uState, q);

  float B = state.g;
  float activity = state.b;

  float bx = (outside ? 0.0 : texture2D(uState, q + vec2(uTexel.x, 0.0)).g)
           - (outside ? 0.0 : texture2D(uState, q - vec2(uTexel.x, 0.0)).g);
  float by = (outside ? 0.0 : texture2D(uState, q + vec2(0.0, uTexel.y)).g)
           - (outside ? 0.0 : texture2D(uState, q - vec2(0.0, uTexel.y)).g);
  float gradient = length(vec2(bx, by));

  // Shape the raw chemical into a display field: pattern body plus a
  // membrane term riding the gradient, plus recent-event glow.
  float field = smoothstep(0.04, 0.42, B) * (0.72 + 0.28 * uOpsA.x);
  float membrane = smoothstep(0.02, 0.14, gradient) * (0.35 + 0.85 * uOpsB.z);
  float glow = min(uGlowMax, activity * uGlowMax * (1.2 + uPulse));
  float v = clamp(field + membrane * 0.35 + glow, 0.0, 1.0);

  // Faint substrate tint inside the domain only: the silhouette reads as a
  // specimen on a clean dark field, never haze.
  float domain = smoothstep(0.1, 0.5, state.a);
  float fieldFloor = 0.06 + 0.02 * sin(uTime * 0.4 + q.x * 3.0 + q.y * 5.0);
  v = max(v, fieldFloor * domain * (1.0 - smoothstep(0.0, 0.08, B)));

  // Ordered dither: quantize the display field into palette bands with a
  // Bayer threshold per dither cell.
  vec2 cell = floor(gl_FragCoord.xy / max(1.0, uDitherScale));
  float threshold = bayer8(cell) - 0.5;
  float shades = 5.0;
  float quantized = floor(v * shades + 0.5 + threshold) / shades;
  vec3 dithered = paletteRamp(quantized);
  vec3 smoothCol = paletteRamp(v);

  vec3 color = mix(dithered, smoothCol, clamp(uAbstraction, 0.0, 1.0));

  float vignette = smoothstep(0.95, 0.35, length((vUv - 0.5) * vec2(0.85, 1.0)));
  color *= 0.78 + 0.22 * vignette;

  gl_FragColor = vec4(color, 1.0);
}`;
