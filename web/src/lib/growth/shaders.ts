export const growthVertex = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`;

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

float segmentDistance(vec2 p, vec2 a, vec2 b) {
  vec2 pa = p - a;
  vec2 ba = b - a;
  float h = clamp(dot(pa, ba) / max(dot(ba, ba), 0.00001), 0.0, 1.0);
  return length(pa - ba * h);
}

void main() {
  vec4 state = texture2D(uState, vUv);
  if (uCopy > 0.5) {
    gl_FragColor = state;
    return;
  }

  vec4 north = texture2D(uState, vUv + vec2(0.0, uTexel.y));
  vec4 south = texture2D(uState, vUv - vec2(0.0, uTexel.y));
  vec4 east = texture2D(uState, vUv + vec2(uTexel.x, 0.0));
  vec4 west = texture2D(uState, vUv - vec2(uTexel.x, 0.0));
  vec4 average = (north + south + east + west) * 0.25;

  float body = state.r;
  float vessel = state.g;
  float activity = state.b * 0.986;
  float settled = min(1.0, state.a + 0.0015);

  if (uActive > 0.5) {
    float eased = 0.5 - 0.5 * cos(clamp(uProgress, 0.0, 1.0) * 3.14159265);
    vec2 tip = mix(uFrom, uTo, eased);
    float grain = noise(vUv * 23.0 + vec2(uSeed * 0.013, uSeed * 0.021));
    float fine = noise(vUv * 67.0 - vec2(uSeed * 0.017, uSeed * 0.009));
    float organicRadius = uRadius * mix(0.82, 1.18, grain) * mix(0.93, 1.07, fine);
    float capsule = segmentDistance(vUv, uFrom, tip);
    float lobe = length(vUv - tip);
    float pathWidth = mix(uRadius * 0.24, uRadius * 0.48, eased);
    float bodyInjection = max(
      smoothstep(pathWidth, pathWidth * 0.2, capsule),
      smoothstep(organicRadius, organicRadius * 0.14, lobe)
    );
    float veinInjection = max(
      smoothstep(uRadius * 0.11, uRadius * 0.018, capsule),
      smoothstep(uRadius * 0.17, uRadius * 0.025, lobe) * (0.35 + 0.65 * fine)
    );
    float local = smoothstep(uRadius * 2.6, uRadius * 0.25, min(capsule, lobe));

    body = max(body, bodyInjection * (0.78 + grain * 0.22));
    vessel = max(vessel, veinInjection);
    activity = max(activity, bodyInjection * (0.72 + 0.28 * eased));
    settled = min(settled, 1.0 - bodyInjection * 0.85);

    // Only the touched neighborhood relaxes. Distant tissue stays bit-stable.
    body += (average.r - body) * 0.035 * local;
    vessel += (average.g - vessel) * 0.012 * local;
  }

  gl_FragColor = clamp(vec4(body, vessel, activity, settled), 0.0, 1.0);
}`;

export const growthRenderFragment = `
precision highp float;
varying vec2 vUv;
uniform sampler2D uState;
uniform vec2 uTexel;
uniform float uTime;
uniform float uAspect;
uniform float uPulse;

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

vec2 hash22(vec2 p) {
  float n = sin(dot(p, vec2(41.0, 289.0)));
  return fract(vec2(262144.0, 32768.0) * n);
}

float voronoiEdge(vec2 p) {
  vec2 cell = floor(p);
  vec2 f = fract(p);
  float nearest = 8.0;
  float second = 8.0;
  for (int y = -1; y <= 1; y++) {
    for (int x = -1; x <= 1; x++) {
      vec2 offset = vec2(float(x), float(y));
      vec2 point = offset + hash22(cell + offset) - f;
      float distanceSquared = dot(point, point);
      if (distanceSquared < nearest) {
        second = nearest;
        nearest = distanceSquared;
      } else if (distanceSquared < second) {
        second = distanceSquared;
      }
    }
  }
  return sqrt(second) - sqrt(nearest);
}

void main() {
  // Keep the specimen broad but unstretched on landscape and portrait screens.
  float fit = max(1.0, uAspect / 1.45);
  vec2 q = vec2((vUv.x - 0.5) * fit + 0.5, vUv.y);
  bool outside = q.x < 0.0 || q.x > 1.0 || q.y < 0.0 || q.y > 1.0;
  vec4 state = outside ? vec4(0.0) : texture2D(uState, q);
  float body = state.r;
  float vessel = state.g;
  float activity = state.b;

  float left = outside ? 0.0 : texture2D(uState, q - vec2(uTexel.x, 0.0)).r;
  float right = outside ? 0.0 : texture2D(uState, q + vec2(uTexel.x, 0.0)).r;
  float down = outside ? 0.0 : texture2D(uState, q - vec2(0.0, uTexel.y)).r;
  float up = outside ? 0.0 : texture2D(uState, q + vec2(0.0, uTexel.y)).r;
  float gradient = length(vec2(right - left, up - down));

  float mask = smoothstep(0.25, 0.5, body);
  float inner = smoothstep(0.48, 0.76, body);
  float membrane = smoothstep(0.018, 0.095, gradient) * smoothstep(0.12, 0.55, body);
  float outerField = smoothstep(0.08, 0.34, body) * (1.0 - mask);

  vec2 warp = vec2(
    sin(q.y * 19.0 + q.x * 7.0),
    cos(q.x * 17.0 - q.y * 5.0)
  ) * 0.38;
  float cellsLarge = voronoiEdge(q * 29.0 + warp);
  float cellsFine = voronoiEdge(q * 61.0 - warp * 0.7);
  float cellWall = (1.0 - smoothstep(0.025, 0.09, cellsLarge)) * 0.72
                 + (1.0 - smoothstep(0.018, 0.055, cellsFine)) * 0.28;
  cellWall *= mask * (0.35 + 0.65 * body);

  float pixelGrain = hash21(floor(q / uTexel));
  float stipple = step(pixelGrain, outerField * 0.7 + activity * 0.08);
  float breath = 0.78 + 0.22 * sin(uTime * 0.72 + q.x * 5.0 + q.y * 3.0);
  float livingEdge = membrane * mix(0.78, 1.18, breath) + outerField * stipple * 0.65;

  vec3 black = vec3(0.008, 0.009, 0.011);
  vec3 tissue = vec3(0.80, 0.77, 0.66);
  vec3 tissueShadow = vec3(0.10, 0.13, 0.12);
  vec3 core = vec3(1.0, 0.19, 0.035);
  vec3 membraneColor = vec3(0.16, 0.88, 0.82);

  vec3 color = black;
  color += vec3(0.012, 0.02, 0.021) * (1.0 - length(vUv - 0.5));
  color = mix(color, mix(tissueShadow, tissue, inner * 0.84), mask * 0.86);
  color = mix(color, tissue * 0.68, cellWall * (0.38 + 0.35 * inner));
  color = mix(color, tissueShadow * 0.45, cellWall * 0.33 * (1.0 - vessel));
  color += core * pow(vessel, 1.45) * (1.05 + activity * 0.42 + uPulse * 0.16);
  color += membraneColor * livingEdge * (0.62 + activity * 0.65);
  color += mix(tissue, membraneColor, 0.42) * stipple * outerField * 0.28;

  float vignette = smoothstep(0.9, 0.28, length((vUv - 0.5) * vec2(0.8, 1.0)));
  color *= 0.62 + 0.38 * vignette;
  gl_FragColor = vec4(color, 1.0);
}`;
