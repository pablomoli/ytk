import * as THREE from "three";

export type BackdropHandle = { dispose: () => void };

/* Galaxy shader adapted from ReactBits (reactbits.dev/backgrounds/galaxy),
   MIT + Commons Clause, (c) David Haz. The ogl wrapper is replaced with the
   house three mount: full DPR, visibility pause, reduced-motion still frame. */

const VERT = /* glsl */ `
precision highp float;
attribute vec3 position;
attribute vec2 uv;
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

const FRAG = /* glsl */ `
precision highp float;

uniform float uTime;
uniform vec3 uResolution;
uniform vec2 uFocal;
uniform vec2 uRotation;
uniform float uStarSpeed;
uniform float uDensity;
uniform float uHueShift;
uniform float uSpeed;
uniform vec2 uMouse;
uniform float uGlowIntensity;
uniform float uSaturation;
uniform bool uMouseRepulsion;
uniform float uTwinkleIntensity;
uniform float uRotationSpeed;
uniform float uRepulsionStrength;
uniform float uMouseActiveFactor;
uniform float uAutoCenterRepulsion;
uniform bool uTransparent;

varying vec2 vUv;

#define NUM_LAYER 4.0
#define STAR_COLOR_CUTOFF 0.2
#define MAT45 mat2(0.7071, -0.7071, 0.7071, 0.7071)
#define PERIOD 3.0

float Hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float tri(float x) {
  return abs(fract(x) * 2.0 - 1.0);
}

float tris(float x) {
  float t = fract(x);
  return 1.0 - smoothstep(0.0, 1.0, abs(2.0 * t - 1.0));
}

float trisn(float x) {
  float t = fract(x);
  return 2.0 * (1.0 - smoothstep(0.0, 1.0, abs(2.0 * t - 1.0))) - 1.0;
}

vec3 hsv2rgb(vec3 c) {
  vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
  vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
  return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

float Star(vec2 uv, float flare) {
  float d = length(uv);
  float m = (0.05 * uGlowIntensity) / d;
  float rays = smoothstep(0.0, 1.0, 1.0 - abs(uv.x * uv.y * 1000.0));
  m += rays * flare * uGlowIntensity;
  uv *= MAT45;
  rays = smoothstep(0.0, 1.0, 1.0 - abs(uv.x * uv.y * 1000.0));
  m += rays * 0.3 * flare * uGlowIntensity;
  m *= smoothstep(1.0, 0.2, d);
  return m;
}

vec3 StarLayer(vec2 uv) {
  vec3 col = vec3(0.0);

  vec2 gv = fract(uv) - 0.5;
  vec2 id = floor(uv);

  for (int y = -1; y <= 1; y++) {
    for (int x = -1; x <= 1; x++) {
      vec2 offset = vec2(float(x), float(y));
      vec2 si = id + vec2(float(x), float(y));
      float seed = Hash21(si);
      float size = fract(seed * 345.32);
      float glossLocal = tri(uStarSpeed / (PERIOD * seed + 1.0));
      float flareSize = smoothstep(0.9, 1.0, size) * glossLocal;

      float red = smoothstep(STAR_COLOR_CUTOFF, 1.0, Hash21(si + 1.0)) + STAR_COLOR_CUTOFF;
      float blu = smoothstep(STAR_COLOR_CUTOFF, 1.0, Hash21(si + 3.0)) + STAR_COLOR_CUTOFF;
      float grn = min(red, blu) * seed;
      vec3 base = vec3(red, grn, blu);

      float hue = atan(base.g - base.r, base.b - base.r) / (2.0 * 3.14159) + 0.5;
      hue = fract(hue + uHueShift / 360.0);
      float sat = length(base - vec3(dot(base, vec3(0.299, 0.587, 0.114)))) * uSaturation;
      float val = max(max(base.r, base.g), base.b);
      base = hsv2rgb(vec3(hue, sat, val));

      vec2 pad = vec2(tris(seed * 34.0 + uTime * uSpeed / 10.0), tris(seed * 38.0 + uTime * uSpeed / 30.0)) - 0.5;

      float star = Star(gv - offset - pad, flareSize);
      vec3 color = base;

      float twinkle = trisn(uTime * uSpeed + seed * 6.2831) * 0.5 + 1.0;
      twinkle = mix(1.0, twinkle, uTwinkleIntensity);
      star *= twinkle;

      col += star * size * color;
    }
  }

  return col;
}

void main() {
  vec2 focalPx = uFocal * uResolution.xy;
  vec2 uv = (vUv * uResolution.xy - focalPx) / uResolution.y;

  vec2 mouseNorm = uMouse - vec2(0.5);

  if (uAutoCenterRepulsion > 0.0) {
    vec2 centerUV = vec2(0.0, 0.0);
    float centerDist = length(uv - centerUV);
    vec2 repulsion = normalize(uv - centerUV) * (uAutoCenterRepulsion / (centerDist + 0.1));
    uv += repulsion * 0.05;
  } else if (uMouseRepulsion) {
    vec2 mousePosUV = (uMouse * uResolution.xy - focalPx) / uResolution.y;
    float mouseDist = length(uv - mousePosUV);
    vec2 repulsion = normalize(uv - mousePosUV) * (uRepulsionStrength / (mouseDist + 0.1));
    uv += repulsion * 0.05 * uMouseActiveFactor;
  } else {
    vec2 mouseOffset = mouseNorm * 0.1 * uMouseActiveFactor;
    uv += mouseOffset;
  }

  float autoRotAngle = uTime * uRotationSpeed;
  mat2 autoRot = mat2(cos(autoRotAngle), -sin(autoRotAngle), sin(autoRotAngle), cos(autoRotAngle));
  uv = autoRot * uv;

  uv = mat2(uRotation.x, -uRotation.y, uRotation.y, uRotation.x) * uv;

  vec3 col = vec3(0.0);

  for (float i = 0.0; i < 1.0; i += 1.0 / NUM_LAYER) {
    float depth = fract(i + uStarSpeed * uSpeed);
    float scale = mix(20.0 * uDensity, 0.5 * uDensity, depth);
    float fade = depth * smoothstep(1.0, 0.9, depth);
    col += StarLayer(uv * scale + i * 453.32) * fade;
  }

  if (uTransparent) {
    float alpha = length(col);
    alpha = smoothstep(0.0, 0.3, alpha);
    alpha = min(alpha, 1.0);
    gl_FragColor = vec4(col, alpha);
  } else {
    gl_FragColor = vec4(col, 1.0);
  }
}
`;

// tuned for the record page: sparse, slow, faintly warm — eyeballed, not sacred
const TUNING = {
  focal: [0.5, 0.5] as const,
  rotation: [1.0, 0.0] as const,
  starSpeed: 0.5,
  density: 0.9,
  hueShift: 15,
  speed: 0.7,
  glowIntensity: 0.25,
  saturation: 0.3,
  twinkleIntensity: 0.3,
  rotationSpeed: 0.03,
  repulsionStrength: 2,
};

/** ReactBits galaxy behind the record grid. Purely decorative: the grid
    never depends on it, and reduced-motion viewers get a single still frame. */
export function mountBackdrop(canvas: HTMLCanvasElement): BackdropHandle {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const scene = new THREE.Scene();
  // the vertex shader ignores the camera; this one exists to satisfy render()
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  const size = new THREE.Vector2();
  const uniforms = {
    uTime: { value: 0 },
    uResolution: { value: new THREE.Vector3(1, 1, 1) },
    uFocal: { value: new THREE.Vector2(...TUNING.focal) },
    uRotation: { value: new THREE.Vector2(...TUNING.rotation) },
    uStarSpeed: { value: TUNING.starSpeed },
    uDensity: { value: TUNING.density },
    uHueShift: { value: TUNING.hueShift },
    uSpeed: { value: TUNING.speed },
    uMouse: { value: new THREE.Vector2(0.5, 0.5) },
    uGlowIntensity: { value: TUNING.glowIntensity },
    uSaturation: { value: TUNING.saturation },
    uMouseRepulsion: { value: true },
    uTwinkleIntensity: { value: TUNING.twinkleIntensity },
    uRotationSpeed: { value: TUNING.rotationSpeed },
    uRepulsionStrength: { value: TUNING.repulsionStrength },
    uMouseActiveFactor: { value: 0 },
    uAutoCenterRepulsion: { value: 0 },
    uTransparent: { value: true },
  };
  const mat = new THREE.RawShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms,
    transparent: true,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), mat);
  mesh.frustumCulled = false;
  scene.add(mesh);

  const resize = () => {
    const w = canvas.clientWidth || 1;
    const h = canvas.clientHeight || 1;
    renderer.setSize(w, h, false);
    renderer.getDrawingBufferSize(size);
    uniforms.uResolution.value.set(size.x, size.y, size.x / size.y);
  };
  resize();
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);

  // the canvas sits behind content with pointer-events off, so the
  // repulsion listener lives on the window
  const targetMouse = { x: 0.5, y: 0.5 };
  let targetActive = 0;
  const onMouseMove = (e: MouseEvent) => {
    const rect = canvas.getBoundingClientRect();
    targetMouse.x = (e.clientX - rect.left) / rect.width;
    targetMouse.y = 1 - (e.clientY - rect.top) / rect.height;
    targetActive = 1;
  };
  window.addEventListener("mousemove", onMouseMove);

  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let raf = 0;
  let t = 0;
  const frame = () => {
    t += 1 / 60;
    uniforms.uTime.value = t;
    uniforms.uStarSpeed.value = (t * TUNING.starSpeed) / 10;
    const m = uniforms.uMouse.value;
    m.x += (targetMouse.x - m.x) * 0.05;
    m.y += (targetMouse.y - m.y) * 0.05;
    uniforms.uMouseActiveFactor.value += (targetActive - uniforms.uMouseActiveFactor.value) * 0.05;
    renderer.render(scene, camera);
    if (!still) raf = requestAnimationFrame(frame);
  };
  const onVisibility = () => {
    cancelAnimationFrame(raf);
    if (!document.hidden) raf = requestAnimationFrame(frame);
  };
  document.addEventListener("visibilitychange", onVisibility);
  raf = requestAnimationFrame(frame);

  return {
    dispose() {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("mousemove", onMouseMove);
      ro.disconnect();
      mesh.geometry.dispose();
      mat.dispose();
      renderer.dispose();
    },
  };
}
