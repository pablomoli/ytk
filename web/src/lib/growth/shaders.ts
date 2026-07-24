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

// Petri-dish display. The whole region is composed in shader: dark lab bench,
// circular glass dish (rim ring, specular hint, agar tint, drop shadow), and
// the reaction-diffusion culture inside. Dithering is exactly one device
// pixel of blue-noise-weighted threshold on the shaded ramp — grain on
// gradients, never checkerboard on flats.
export const growthRenderFragment = `
precision highp float;
varying vec2 vUv;
uniform sampler2D uState;
uniform vec2 uTexel;
uniform float uTime;
uniform float uAspect;
uniform float uPulse;
uniform vec3 uPalette0; // deep field / agar shadow
uniform vec3 uPalette1; // low tissue
uniform vec3 uPalette2; // high tissue
uniform vec3 uPalette3; // vessel highlight
uniform vec3 uPalette4; // membrane / brightest
uniform vec3 uOpsA; // DEEPEN, BUD, LACE
uniform vec3 uOpsB; // STIPPLE, BLEED, MEMBRANE
uniform float uGlowMax;
uniform float uAbstraction; // 0 = dithered, 1 = smooth
uniform float uMini;        // 1 = small variant dish (thicker relative rim)

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

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
  // Aspect-corrected coordinates centered on the region; the dish is a true
  // circle whatever the region shape, and the whole region is composed.
  vec2 p = (vUv - 0.5) * vec2(uAspect, 1.0);
  // The main dish sits left-of-center and clear of the variant strip at
  // bottom-right; minis stay centered in their own square regions.
  vec2 dishC = mix(vec2((0.40 - 0.5) * uAspect, -0.02), vec2(0.0), uMini);
  p -= dishC;
  float d = length(p);
  float dishR = mix(0.38, 0.46, uMini);
  float rimW = mix(0.008, 0.02, uMini);

  // Lab bench: flat near-black plus the dish drop shadow. Flat on purpose —
  // any positional texture would seam at the mini-dish region borders.
  vec3 bench = uPalette0 * 0.30;
  float shadow = smoothstep(dishR + 0.03, dishR + 0.004, length(p + vec2(0.008, -0.012)));
  bench *= 1.0 - shadow * 0.45;

  if (d > dishR + rimW * 2.5) {
    gl_FragColor = vec4(bench, 1.0);
    return;
  }

  // Culture field: map the dish interior to the square simulation.
  vec2 suv = p / dishR * 0.5 * 0.96 + 0.5;
  vec4 state = texture2D(uState, suv);
  float B = state.g;
  float activity = state.b;
  float domain = smoothstep(0.1, 0.5, state.a);

  float bx = texture2D(uState, suv + vec2(uTexel.x, 0.0)).g
           - texture2D(uState, suv - vec2(uTexel.x, 0.0)).g;
  float by = texture2D(uState, suv + vec2(0.0, uTexel.y)).g
           - texture2D(uState, suv - vec2(0.0, uTexel.y)).g;
  float gradient = length(vec2(bx, by));

  // Agar: a barely-lifted ground inside the glass, brightest mid-dish.
  float agarShade = smoothstep(dishR, dishR * 0.15, d);
  vec3 agar = mix(uPalette0 * 0.5, mix(uPalette0, uPalette1, 0.22), 0.35 + 0.3 * agarShade);

  // Culture shading: crisp band on the pattern chemical, membrane on its
  // gradient, warm tinted pulse where a note just landed (never white-out).
  float field = smoothstep(0.08, 0.26, B);
  float core = smoothstep(0.26, 0.50, B);
  float membrane = smoothstep(0.025, 0.12, gradient) * (0.3 + 0.7 * uOpsB.z);
  float v = clamp(field * (0.52 + 0.38 * core) + membrane * 0.30, 0.0, 1.0);

  // One-device-pixel blue-noise-weighted dither on the shaded ramp.
  float noiseT = hash21(gl_FragCoord.xy) * 0.55 + bayer8(gl_FragCoord.xy) * 0.45;
  float shades = 7.0;
  float quantized = floor(v * shades + noiseT) / shades;
  float shade = mix(quantized, v, clamp(uAbstraction, 0.0, 1.0));
  // Lift the tissue floor so the faintest culture still separates from agar.
  vec3 culture = paletteRamp(0.12 + shade * 0.88);

  vec3 inner = mix(agar, culture, smoothstep(0.02, 0.10, B));
  inner += uPalette3 * activity * min(uGlowMax, 0.22) * (1.0 + uPulse * 0.8);
  inner = mix(inner, inner * 0.86, smoothstep(dishR * 0.78, dishR, d)); // glass inner shadow

  // Glass rim: thin ring with a directional specular hint.
  float ring = smoothstep(rimW, rimW * 0.25, abs(d - dishR));
  float spec = pow(max(0.0, dot(normalize(p + vec2(0.0001)), normalize(vec2(-0.6, 0.75)))), 3.0);
  vec3 rimCol = mix(uPalette1, uPalette4, 0.25 + spec * 0.55);

  vec3 color = mix(bench, inner, smoothstep(dishR + rimW, dishR - rimW * 0.5, d));
  color = mix(color, rimCol, ring * (0.5 + spec * 0.4));

  gl_FragColor = vec4(color, 1.0);
}`;
