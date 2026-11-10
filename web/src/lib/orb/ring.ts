import {
  GLSL3,
  Group,
  InstancedBufferAttribute,
  InstancedBufferGeometry,
  Matrix4,
  Mesh,
  NoColorSpace,
  PerspectiveCamera,
  PlaneGeometry,
  RawShaderMaterial,
  Texture,
  TextureLoader,
} from "three";

/* The pending ring: every item still in the queue is one grain in a flat ring
   around the sphere, newest at the inner edge, a gap at each month. Read-only:
   grains can be hovered, nothing here ingests or drops. */

export type RingItem = {
  u: string; // url
  s: string; // source
  a: string; // author
  t: string; // title or text, clipped by the bake
  d: string; // day saved, "" when unknown
  q: number; // 1 = carries an open question
  k: number; // cover's slot in the atlas, -1 = no cached cover
};
export type RingData = { cols: number; cell: number; size: number; items: RingItem[] };

export const RING_IN = 1.22;
export const RING_OUT = 1.8;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));
// a month boundary leaves a gap as wide as this many items; it has to clear one grain's width
const GAP = 600;
// months with fewer items than this merge into the next band instead of getting a gap of their own
const MIN_BAND = 40;
const GRAIN = 0.02;
const NO_COVER = 0.55; // size of a grain without a cover, against one with
const HOVER = 2.4;
const OMEGA = (Math.PI * 2) / 480; // inner edge: one turn in eight minutes
const THICK_INSIDE = 0.07, THICK_GLOBE = 0.006;
const FAR_INSIDE = 0.5; // behind the tiles the belt is backdrop, not content

const hash = (x: number) => { const v = Math.sin(x * 12.9898) * 43758.5453; return v - Math.floor(v); };

// pure so it's unit-testable: r, theta per item, in input order (newest first).
// Equal area per item, so a busy month is a wide band. Grains snap to concentric
// lanes: evenly scattered they read as sunflower spirals, in lanes as a ring.
export function ringLayout(days: string[]): Float32Array {
  const n = days.length;
  const slot = new Float32Array(n);
  let gaps = 0, band = 0, prev = "";
  for (let k = 0; k < n; k++) {
    const key = days[k].slice(0, 7);
    if (k > 0 && key !== prev && band >= MIN_BAND) { gaps++; band = 0; }
    prev = key;
    band++;
    slot[k] = k + gaps * GAP;
  }
  const total = Math.max(1, n + gaps * GAP);
  const a = RING_IN * RING_IN, b = RING_OUT * RING_OUT - a;
  const pitch = Math.sqrt((Math.PI * b) / total); // side of one item's share of the ring's area
  const lane = new Int32Array(n);
  const count: number[] = [];
  for (let k = 0; k < n; k++) {
    const r = Math.sqrt(a + ((slot[k] + 0.5) / total) * b);
    lane[k] = Math.floor((r - RING_IN) / pitch);
    count[lane[k]] = (count[lane[k]] ?? 0) + 1;
  }
  const seen: number[] = [];
  const out = new Float32Array(n * 2);
  for (let k = 0; k < n; k++) {
    const l = lane[k];
    const j = (seen[l] = (seen[l] ?? -1) + 1);
    // a little disorder inside the lane, never enough to cross into the next
    out[k * 2] = RING_IN + (l + 0.5 + (hash(k + 0.5) - 0.5) * 0.45) * pitch;
    out[k * 2 + 1] = l * GOLDEN + ((j + (hash(k + 7.3) - 0.5) * 0.5) / count[l]) * Math.PI * 2;
  }
  return out;
}

const VERT = /* glsl */ `
precision highp float;
in vec3 position;
in vec2 uv;
in vec4 iGrain; // r, theta at rest, height in the belt (-1..1), atlas slot (-1 = no cover)
in float iIdx;
in float iFlag; // 1 = open question
uniform mat4 modelViewMatrix, projectionMatrix;
uniform float uTime, uOmega, uInner;
uniform float uGrain, uSize, uNoCover, uHover, uHoverScale;
uniform float uBill;  // 0 = grains lie in the ring plane, 1 = they face the camera
uniform float uThick; // half thickness of the belt
uniform float uCols, uCell;
out vec2 vUv;
out float vHas, vHov, vFlag, vNear, vSeed;
void main() {
  float r = iGrain.x;
  // inner grains lap outer ones, as in a real ring
  float a = iGrain.y + uTime * uOmega * pow(uInner / r, 1.5);
  vec3 radial = vec3(cos(a), 0.0, sin(a));
  vec3 tang = vec3(-radial.z, 0.0, radial.x);
  vec3 c = radial * r + vec3(0.0, iGrain.z * uThick, 0.0);
  float has = step(0.0, iGrain.w);
  float hov = abs(iIdx - uHover) < 0.5 ? 1.0 : 0.0;
  vec4 cv = modelViewMatrix * vec4(c, 1.0);
  float dist = length(cv.xyz);
  // a grain about to pass through the camera shrinks away instead of filling the view
  float s = uGrain * uSize * mix(uNoCover, 1.0, has) * mix(1.0, uHoverScale, hov) * smoothstep(0.06, 0.3, dist);
  vec4 lying = modelViewMatrix * vec4(c + (tang * position.x + radial * position.y) * s, 1.0);
  vec4 bill = cv + vec4(position.xy * s, 0.0, 0.0);
  gl_Position = projectionMatrix * mix(lying, bill, max(uBill, hov));
  float k = max(iGrain.w, 0.0);
  // inset: at the small mip levels a cell's edge carries its neighbor's color
  vec2 cell = vec2(mod(k, uCols), floor(k / uCols));
  vec2 q = 0.05 + uv * 0.9;
  vUv = vec2((cell.x + q.x) * uCell, 1.0 - (cell.y + 1.0 - q.y) * uCell);
  vHas = has;
  vHov = hov;
  vFlag = iFlag;
  vNear = 1.0 - smoothstep(0.5, 2.0, dist);
  vSeed = fract(iIdx * 0.618034);
}`;

const FRAG = /* glsl */ `
precision highp float;
uniform sampler2D uAtlas;
uniform float uLevel;
uniform float uFar; // brightness away from the pointer: the ring steps back when seen from inside
in vec2 vUv;
in float vHas, vHov, vFlag, vNear, vSeed;
out vec4 outColor;
void main() {
  if (uLevel < 0.01) discard;
  vec3 cover = texture(uAtlas, vUv).rgb;
  float l = dot(cover, vec3(0.299, 0.587, 0.114));
  // far grains are pale ice that keeps the cover's light and dark; the picture returns up close
  vec3 pale = vec3(0.80, 0.78, 0.72) * (0.22 + 0.78 * l) * 0.72;
  float near = max(vNear, vHov);
  vec3 c = mix(pale, cover, near);
  vec3 speck = vec3(0.27, 0.26, 0.245) * (0.55 + 0.6 * vSeed);
  c = mix(speck, c, vHas);
  vec3 brass = vec3(0.886, 0.690, 0.290) * (0.3 + 0.7 * dot(c, vec3(0.333)) * 1.6);
  c = mix(c, brass, 0.45 * vFlag * (1.0 - near));
  outColor = vec4(c * mix(uFar, 1.0, vHov), uLevel);
}`;

export type RingHandle = {
  group: Group;
  // level: 0..1 opacity. size: the tiles' size factor, so grains shrink with them. paused: hold the rotation.
  update(dt: number, opts: { level: number; size: number; inside: boolean; paused: boolean; still: boolean }): void;
  // grain under the pointer and its view depth, nearest first; null when none
  pick(ndcX: number, ndcY: number, camera: PerspectiveCamera): { k: number; depth: number } | null;
  setHover(k: number | null): void;
  setBill(globe: number): void;
  dispose(): void;
};

export function createRing(data: RingData, atlasUrl: string, anisotropy: number): RingHandle {
  const n = data.items.length;
  const layout = ringLayout(data.items.map((it) => it.d));
  const grain = new Float32Array(n * 4);
  const flag = new Float32Array(n);
  const rate = new Float32Array(n); // each grain's share of the inner edge's angular speed
  data.items.forEach((it, k) => {
    const r = layout[k * 2];
    // height from a hash, so the belt's thickness needs no stored field
    const h = (Math.sin(k * 12.9898) * 43758.5453) % 1;
    grain.set([r, layout[k * 2 + 1], Math.max(-1, Math.min(1, h)), it.k], k * 4);
    flag[k] = it.q ? 1 : 0;
    rate[k] = Math.pow(RING_IN / r, 1.5);
  });
  const plane = new PlaneGeometry(1, 1);
  const geo = new InstancedBufferGeometry();
  geo.index = plane.index;
  geo.setAttribute("position", plane.getAttribute("position"));
  geo.setAttribute("uv", plane.getAttribute("uv"));
  geo.setAttribute("iGrain", new InstancedBufferAttribute(grain, 4));
  geo.setAttribute("iIdx", new InstancedBufferAttribute(Float32Array.from({ length: n }, (_, i) => i), 1));
  geo.setAttribute("iFlag", new InstancedBufferAttribute(flag, 1));
  geo.instanceCount = n;
  const material = new RawShaderMaterial({
    glslVersion: GLSL3,
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    uniforms: {
      uAtlas: { value: null as Texture | null },
      uTime: { value: 0 }, uOmega: { value: OMEGA }, uInner: { value: RING_IN },
      uGrain: { value: GRAIN }, uSize: { value: 1 }, uNoCover: { value: NO_COVER },
      uHover: { value: -1 }, uHoverScale: { value: HOVER },
      uBill: { value: 1 }, uThick: { value: THICK_INSIDE },
      uCols: { value: data.cols }, uCell: { value: data.cell / data.size },
      uLevel: { value: 0 }, uFar: { value: 1 },
    },
  });
  const mesh = new Mesh(geo, material);
  mesh.frustumCulled = false; // instances are placed in the shader; the base quad's bound says nothing
  mesh.renderOrder = -0.5; // after the theme tint, before labels and the selection glow
  mesh.visible = false;
  const group = new Group();
  // tilted like Saturn seen from Earth: a narrow ellipse at rest, a full face when the camera climbs
  group.rotation.set(0.26, 0, 0.1);
  group.add(mesh);
  let disposed = false;
  let tex: Texture | null = null;
  new TextureLoader().load(atlasUrl, (t) => {
    if (disposed) { t.dispose(); return; }
    // raw shader, no output encode: bytes pass through, like the tile atlas
    t.colorSpace = NoColorSpace;
    t.anisotropy = anisotropy;
    t.needsUpdate = true;
    tex = t;
    material.uniforms.uAtlas.value = t;
    mesh.visible = true;
  });

  let hover = -1;
  let billGlobe = 1;
  const u = material.uniforms;
  const _mvp = new Matrix4();
  return {
    group,
    update(dt, { level, size, inside, paused, still }) {
      if (!paused && !still) u.uTime.value += dt;
      u.uSize.value = size;
      u.uLevel.value = level;
      // from inside the camera sits in the ring plane: flat grains would be edge-on, so they stand and spread into a belt
      const k = still ? 1 : 1 - Math.exp(-dt * 5);
      u.uBill.value += ((inside ? 1 : billGlobe) - u.uBill.value) * k;
      u.uThick.value += ((inside ? THICK_INSIDE : THICK_GLOBE) - u.uThick.value) * k;
      u.uFar.value += ((inside ? FAR_INSIDE : 1) - u.uFar.value) * k;
    },
    pick(ndcX, ndcY, camera) {
      if (!mesh.visible || (u.uLevel.value as number) < 0.5) return null;
      group.updateMatrixWorld();
      _mvp.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).multiply(group.matrixWorld);
      const e = _mvp.elements;
      const time = u.uTime.value as number, thick = u.uThick.value as number;
      const px = camera.projectionMatrix.elements[0], py = camera.projectionMatrix.elements[5];
      const side = GRAIN * (u.uSize.value as number);
      let best = -1, bestW = Infinity;
      for (let k = 0; k < n; k++) {
        const r = grain[k * 4];
        const a = grain[k * 4 + 1] + time * OMEGA * rate[k];
        const x = r * Math.cos(a), y = grain[k * 4 + 2] * thick, z = r * Math.sin(a);
        const w = e[3] * x + e[7] * y + e[11] * z + e[15];
        if (w < 0.3 || w >= bestW) continue; // nearer than this the shader has shrunk the grain away
        // small grains get a hit area a little larger than they are drawn
        const h = (side * (grain[k * 4 + 3] >= 0 ? 1 : NO_COVER) * (k === hover ? HOVER : 1.5)) / 2;
        const nx = (e[0] * x + e[4] * y + e[8] * z + e[12]) / w;
        if (Math.abs(nx - ndcX) > (h * px) / w) continue;
        const ny = (e[1] * x + e[5] * y + e[9] * z + e[13]) / w;
        if (Math.abs(ny - ndcY) > (h * py) / w) continue;
        best = k;
        bestW = w;
      }
      return best < 0 ? null : { k: best, depth: bestW };
    },
    setHover(k) {
      hover = k ?? -1;
      u.uHover.value = hover;
    },
    setBill(globe) { billGlobe = globe; },
    dispose() {
      disposed = true;
      tex?.dispose();
      plane.dispose();
      geo.dispose();
      material.dispose();
    },
  };
}
