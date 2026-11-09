import {
  AdditiveBlending,
  BufferGeometry,
  ClampToEdgeWrapping,
  DataTexture,
  BufferAttribute,
  LineSegments,
  DoubleSide,
  GLSL3,
  InstancedBufferAttribute,
  InstancedBufferGeometry,
  LinearFilter,
  Matrix3,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  SRGBColorSpace,
  NoColorSpace,
  PerspectiveCamera,
  PlaneGeometry,
  RawShaderMaterial,
  RedFormat,
  RepeatWrapping,
  Scene,
  SphereGeometry,
  Texture,
  TextureLoader,
  Vector3,
  WebGLRenderer,
} from "three";
import { DUR, gsap, reducedMotion } from "../motion";
import type { LayoutName, OrbData } from "../../api/orb";
import { PLANET_COAST_AMP, PLANET_FRAG, PLANET_VERT, loadRamp } from "../galaxy/scene";
import { buildAtlas, COLS, slotUv } from "./atlas";
import { createControls } from "./controls";
import { pickTile, tileScreenRect } from "./pick";

export const TILE_HALF = 0.055; // ~4.5deg cell radius, sized for the content-set scale (~500 tiles)
// Apex40 previz verdict (user-reviewed, Apex Manim render): DOLLY = 1 -
// 0.055/(0.40 * tan 30deg) = 0.76. Final; do not derive from a different apex.
const DOLLY = 0.76;
const DIM_FOCUS = 0.25;
const DIM_FILTER = 0.15;

// mirrors DOLLY's stand-off distance-from-tile, kept outside the unit sphere:
// same ~40% viewport-height apex fraction, viewed from the outside instead of the origin.
const GLOBE_APEX = 1 + 0.238;
export const GLOBE_R_CLOSE = 1.30; // wheel zoom=0: globe orbit radius (camera 1.30, tiles at 1.0, near 0.01 — no clip)
export const GLOBE_R_FAR = 4.0; // wheel zoom=1: globe orbit radius
export const restGlobeR = (z: number) => GLOBE_R_CLOSE + z * (GLOBE_R_FAR - GLOBE_R_CLOSE);

// inside mode: wheel zoom drives a forward dolly instead of fov (fov is fixed
// at the camera's constructed 60). Bound: tiles at radius 1, TILE_HALF 0.055,
// near plane 0.01 -> at zoom=1 (offset=MAX_FWD) distance to the tile plane is
// 1 - 0.72 = 0.28, comfortably above the 0.2 invariant and the near plane.
export const MAX_FWD = 0.72;
// pure so it's unit-testable without a camera/canvas: offset for the inside
// dolly at a given wheel-zoom value.
export function wheelDollyOffset(zoom: number): number {
  return zoom * MAX_FWD;
}

// Firefox/Gecko reports WheelEvent.deltaMode 1 (DOM_DELTA_LINE, ~3/tick)
// where Chromium reports 0 (DOM_DELTA_PIXEL, ~100/tick); mode 2 is
// DOM_DELTA_PAGE. Normalizing here (not in controls.wheel) keeps the pixel
// accumulator in controls.ts engine-agnostic.
export function normalizeWheelDelta(deltaY: number, deltaMode: number, clientHeight: number): number {
  if (deltaMode === 1) return deltaY * 33;
  if (deltaMode === 2) return deltaY * clientHeight;
  return deltaY;
}

const VERT = /* glsl */ `
precision highp float;
in vec3 position;
in vec2 uv;
in vec3 iPos;   // tile center on the unit sphere
in vec4 iUv;    // atlas u, v, span u, span v
in float iAspect; // width/height; the quad keeps its area, so sqrt scales each axis
in float iScale;  // density scale: tiles shrink where a layout bunches them
in float iIdx;
in float iTheme; // per-instance theme id
uniform mat4 modelViewMatrix, projectionMatrix;
uniform float uHovered, uHoverScale;
uniform float uFacing; // 1 inside (tiles face the origin), -1 globe (tiles face outward)
uniform float uNeigh[8];
uniform float uNeighScale; // 1 at rest; the hovered tile's neighbors swell to it
uniform float uBirth, uCount; // mount pop-in: uBirth runs 0..1, tiles pop in index order
out vec2 vUv;
out float vIdx;
out float vTheme;
void main() {
  vec3 n = normalize(-iPos) * uFacing;
  vec3 ref = abs(n.y) > 0.9 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0);
  vec3 e1 = normalize(cross(ref, n));
  vec3 e2 = cross(n, e1);
  float s = (abs(iIdx - uHovered) < 0.5) ? uHoverScale : 1.0;
  for (int k = 0; k < 8; k++) if (abs(iIdx - uNeigh[k]) < 0.5) s *= uNeighScale;
  float born = smoothstep(0.0, 1.0, (uBirth * 1.35 - iIdx / uCount) / 0.35);
  s *= born * iScale;
  float sx = sqrt(iAspect);
  vec3 world = iPos + (e1 * position.x * sx + e2 * position.y / sx) * s;
  vUv = vec2(iUv.x + uv.x * iUv.z, iUv.y + uv.y * iUv.w);
  vIdx = iIdx;
  vTheme = iTheme; // constant across the quad; interpolation is a no-op
  gl_Position = projectionMatrix * modelViewMatrix * vec4(world, 1.0);
}`;

const FRAG = /* glsl */ `
precision highp float;
uniform sampler2D uAtlas;
uniform float uFocused, uDim;      // focus dimming: everyone but uFocused
uniform float uTheme, uThemeDim;   // theme filter dim factor
uniform float uHovered;
uniform float uNeigh[8];           // hovered tile's embedding neighbors (-1 = none)
uniform float uNeighDim;           // 1 = off; below 1 dims everyone outside hovered + neighbors
in vec2 vUv;
in float vIdx;
in float vTheme;
out vec4 outColor;
void main() {
  vec3 c = texture(uAtlas, vUv).rgb;
  float dim = 1.0;
  if (uFocused >= 0.0 && abs(vIdx - uFocused) >= 0.5) dim *= uDim;
  if (uTheme >= 0.0 && abs(vTheme - uTheme) >= 0.5) dim *= uThemeDim;
  if (uNeighDim < 1.0) {
    bool keep = abs(vIdx - uHovered) < 0.5;
    for (int k = 0; k < 8; k++) if (abs(vIdx - uNeigh[k]) < 0.5) keep = true;
    if (!keep) dim *= uNeighDim;
  }
  outColor = vec4(c * dim, 1.0);
}`;

export type OrbViewMode = "inside" | "globe";

// pure so it's unit-testable: the coast sphere shows only once the bake has
// loaded (404 or in-flight leaves it hidden), only while orbiting the globe,
// and only while the terrain toggle is on.
export function coastVisible(mode: OrbViewMode, loaded: boolean, terrain: boolean): boolean {
  return mode === "globe" && loaded && terrain;
}

export type OrbHandle = {
  setLayout(name: LayoutName): void;
  setThemeFilter(th: number | null): void;
  setView(mode: OrbViewMode): void;
  setTerrain(on: boolean): void;
  aimAt(dir: [number, number, number]): void;
  centerOf(i: number): [number, number, number];
  focus(i: number): void;
  blur(): void;
  dispose(): void;
};

export function mountOrb(
  canvas: HTMLCanvasElement,
  data: OrbData,
  cb: { onHover(i: number | null): void; onOpen(i: number, rect: DOMRect): void },
): OrbHandle {
  const cap = COLS * COLS; // atlas has exactly this many slots; beyond it uvRect wraps
  const n = Math.min(data.points.length, cap);
  if (n < data.points.length) {
    console.warn(`orb: dropping ${data.points.length - n} points beyond atlas capacity (${cap})`);
  }
  const points = data.points.slice(0, n);
  const renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const camera = new PerspectiveCamera(60, canvas.clientWidth / Math.max(1, canvas.clientHeight), 0.01, 10);
  const scene = new Scene();

  const centers = new Float32Array(n * 3);
  const scales = new Float32Array(n).fill(1);
  // where a layout bunches tiles, each shrinks to its nearest neighbor's distance so none overlap
  const densityScales = (pos: Float32Array, asp: Float32Array, out: Float32Array) => {
    for (let i = 0; i < n; i++) {
      let best = -1;
      const ax = pos[i * 3], ay = pos[i * 3 + 1], az = pos[i * 3 + 2];
      for (let j = 0; j < n; j++) {
        if (j === i) continue;
        const d = ax * pos[j * 3] + ay * pos[j * 3 + 1] + az * pos[j * 3 + 2];
        if (d > best) best = d;
      }
      const dist = Math.acos(Math.min(1, best)); // radians to the nearest tile center
      const sx = Math.sqrt(asp[i]);
      const long = TILE_HALF * Math.max(sx, 1 / sx) * 2 * 1.1;
      out[i] = Math.min(1, Math.max(0.4, dist / long));
    }
  };
  const layoutArray = (name: LayoutName): number[][] | null => {
    const arr = data.sphere[name] ?? data.sphere[data.sphere.chosen];
    if (!arr || arr.length < n) {
      console.warn(`orb: layout "${name}" missing or short (${arr?.length ?? 0} < ${n}); keeping current centers`);
      return null;
    }
    return arr;
  };
  {
    const arr = layoutArray(data.sphere.chosen)!;
    for (let i = 0; i < n; i++) centers.set(arr[i], i * 3);
  }
  const morph = { t: 1 };
  const morphFrom = new Float32Array(n * 3), morphTo = new Float32Array(n * 3);
  const scaleFrom = new Float32Array(n), scaleTo = new Float32Array(n);
  let morphing = false;

  const plane = new PlaneGeometry(TILE_HALF * 2, TILE_HALF * 2);
  const geo = new InstancedBufferGeometry();
  geo.index = plane.index;
  geo.setAttribute("position", plane.getAttribute("position"));
  geo.setAttribute("uv", plane.getAttribute("uv"));
  const iPos = new InstancedBufferAttribute(centers, 3);
  geo.setAttribute("iPos", iPos);
  const atlas = buildAtlas(points, data.themes.length, () => {});
  // tiles are seen at a slant from inside; without anisotropy every oblique tile smears
  atlas.texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const uvs = new Float32Array(n * 4);
  const aspects = new Float32Array(n);
  atlas.slots.forEach((sl, i) => {
    const r = slotUv(sl);
    uvs.set([r.u, r.v, r.su, r.sv], i * 4);
    aspects[i] = sl.w / sl.h;
  });
  geo.setAttribute("iUv", new InstancedBufferAttribute(uvs, 4));
  geo.setAttribute("iAspect", new InstancedBufferAttribute(aspects, 1));
  densityScales(centers, aspects, scales);
  const iScale = new InstancedBufferAttribute(scales, 1);
  geo.setAttribute("iScale", iScale);
  // tiles slide along the sphere from one layout to the next instead of jumping
  const writeLayout = (name: LayoutName) => {
    const arr = layoutArray(name);
    if (!arr) return;
    morphFrom.set(centers);
    scaleFrom.set(scales);
    for (let i = 0; i < n; i++) morphTo.set(arr[i], i * 3);
    densityScales(morphTo, aspects, scaleTo);
    if (reducedMotion()) {
      centers.set(morphTo); scales.set(scaleTo);
      iPos.needsUpdate = true; iScale.needsUpdate = true;
      return;
    }
    gsap.killTweensOf(morph);
    morph.t = 0; morphing = true;
    gsap.to(morph, { t: 1, duration: 0.9, ease: "power2.inOut", onComplete: () => { morphing = false; } });
  };
  const stepMorph = () => {
    const t = morph.t;
    for (let i = 0; i < n; i++) {
      const x = morphFrom[i * 3] + (morphTo[i * 3] - morphFrom[i * 3]) * t;
      const y = morphFrom[i * 3 + 1] + (morphTo[i * 3 + 1] - morphFrom[i * 3 + 1]) * t;
      const z = morphFrom[i * 3 + 2] + (morphTo[i * 3 + 2] - morphFrom[i * 3 + 2]) * t;
      const l = Math.hypot(x, y, z) || 1; // back onto the unit sphere; antipodal pairs are not in the data
      centers[i * 3] = x / l; centers[i * 3 + 1] = y / l; centers[i * 3 + 2] = z / l;
      scales[i] = scaleFrom[i] + (scaleTo[i] - scaleFrom[i]) * t;
    }
    iPos.needsUpdate = true; iScale.needsUpdate = true;
  };
  geo.setAttribute("iIdx", new InstancedBufferAttribute(Float32Array.from({ length: n }, (_, i) => i), 1));
  const themes = new Float32Array(n);
  points.forEach((p, i) => { themes[i] = p.th; });
  geo.setAttribute("iTheme", new InstancedBufferAttribute(themes, 1));
  geo.instanceCount = n;

  const material = new RawShaderMaterial({
    glslVersion: GLSL3,
    vertexShader: VERT,
    fragmentShader: FRAG,
    side: DoubleSide,
    uniforms: {
      uAtlas: { value: atlas.texture },
      uHovered: { value: -1 }, uHoverScale: { value: 1.06 },
      uFocused: { value: -1 }, uDim: { value: 1 },
      uTheme: { value: -1 }, uThemeDim: { value: DIM_FILTER },
      uFacing: { value: 1 },
      uNeigh: { value: new Float32Array(8).fill(-1) }, uNeighDim: { value: 1 }, uNeighScale: { value: 1 },
      uBirth: { value: 0 }, uCount: { value: n },
    },
  });
  const mesh = new Mesh(geo, material);
  // geo's bounding sphere is computed from the base plane's local vertices
  // only (three has no notion of the iPos instance attribute's extent), so
  // auto frustum-culling sees a near-zero-radius sphere at the origin instead
  // of the true unit-sphere spread of instances; disable it rather than hand-
  // roll a correct bound for a single always-small draw call.
  mesh.frustumCulled = false;
  scene.add(mesh);

  // superplanet coastline, under the tiles: hidden until globe mode AND the
  // bake has loaded (Task 12). Same shader as galaxy's planets, uSpin pinned.
  let disposed = false;
  let coastLoaded = false;
  let terrain = false; // spike: the coast sphere ships off; the /orb toggle turns it on
  const coastFallback = new DataTexture(new Uint8Array([128]), 1, 1, RedFormat);
  coastFallback.needsUpdate = true;
  const coastRamp = loadRamp();
  const coastGeo = new SphereGeometry(0.985, 64, 32);
  const coastMat = new RawShaderMaterial({
    glslVersion: GLSL3,
    vertexShader: PLANET_VERT,
    fragmentShader: PLANET_FRAG,
    uniforms: {
      uField: { value: coastFallback },
      uRamp: { value: null },
      uSpin: { value: 0 },
      uSeed: { value: 0 },
      uCoastAmp: { value: PLANET_COAST_AMP },
      // 0 = the bake's own z-lat frame: this sphere's geography must land under
      // tile directions from the same frame, so it cannot take the y-up swizzle
      uYUp: { value: 0 },
      // identity: the superplanet keeps the record's canonical magma, arm 0's
      // per-planet rotation is a galaxy-only identity signal
      uHueRot: { value: new Matrix3() },
    },
  });
  coastRamp.bind(coastMat.uniforms.uRamp);
  const coast = new Mesh(coastGeo, coastMat);
  coast.visible = false;
  scene.add(coast);
  let coastTex: Texture | null = null;
  new TextureLoader().load(
    "/galaxy-tex/superplanet.png",
    (tex) => {
      if (disposed) { tex.dispose(); return; }
      tex.flipY = false;
      tex.colorSpace = NoColorSpace; // distance field, not color
      tex.wrapS = RepeatWrapping; // uSpin scrolls u past the seam (unused here, spin pinned)
      tex.wrapT = ClampToEdgeWrapping;
      tex.minFilter = LinearFilter;
      tex.magFilter = LinearFilter;
      tex.generateMipmaps = false;
      tex.needsUpdate = true;
      coastTex = tex;
      coastMat.uniforms.uField.value = tex;
      coastLoaded = true;
      coast.visible = coastVisible(mode, coastLoaded, terrain);
    },
    undefined,
    () => {}, // 404 leaves the coast hidden; not fatal
  );

  // spike: neighbor arcs. One LineSegments, rebuilt on hover, faded with gsap.
  const K_MAX = 12, SEG = 48;
  const arcPos = new Float32Array(K_MAX * SEG * 2 * 3);
  const arcT = new Float32Array(K_MAX * SEG * 2); // 0 at the hovered tile, 1 at the neighbor
  const arcK = new Float32Array(K_MAX * SEG * 2); // which neighbor
  const arcL = new Float32Array(K_MAX * SEG * 2); // the arc's length in radians: pulses move in world units
  const arcGeo = new BufferGeometry();
  // BufferAttribute wraps the arrays; Float32BufferAttribute would copy them and swallow every later write
  const arcAttr = new BufferAttribute(arcPos, 3);
  const arcTAttr = new BufferAttribute(arcT, 1);
  const arcKAttr = new BufferAttribute(arcK, 1);
  const arcLAttr = new BufferAttribute(arcL, 1);
  arcGeo.setAttribute("position", arcAttr);
  arcGeo.setAttribute("aT", arcTAttr);
  arcGeo.setAttribute("aK", arcKAttr);
  arcGeo.setAttribute("aL", arcLAttr);
  arcGeo.setDrawRange(0, 0);
  const arcMat = new RawShaderMaterial({
    glslVersion: GLSL3,
    vertexShader: /* glsl */ `
precision highp float;
in vec3 position; in float aT; in float aK; in float aL;
uniform mat4 modelViewMatrix, projectionMatrix;
out float vT; out float vK; out float vL;
void main() { vT = aT; vK = aK; vL = aL; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: /* glsl */ `
precision highp float;
uniform float uProgress; // how far along each arc has grown, 0..1
uniform float uOpacity;
uniform float uTime;
uniform float uSpeed;   // radians per second along the shell, the same on every arc
uniform float uSpacing; // radians between pulses, so long arcs carry more of them
in float vT; in float vK; in float vL;
out vec4 outColor;
void main() {
  if (vT > uProgress) discard;
  // a continuous stream: pulses leave the hovered tile and travel outward at one speed,
  // each a slow swell (65% of the period rising) and a quicker fall
  float s = vT * vL;
  float ph = fract((s - uTime * uSpeed) / uSpacing);
  float swell = smoothstep(0.0, 0.65, ph) * (1.0 - smoothstep(0.65, 1.0, ph));
  float glow = 0.22 + 0.7 * swell;
  vec3 brass = vec3(0.886, 0.690, 0.290);
  outColor = vec4(mix(brass, vec3(1.0, 0.95, 0.8), swell * 0.6) * glow, glow * uOpacity);
}`,
    uniforms: {
      uProgress: { value: 0 }, uOpacity: { value: 0 }, uTime: { value: 0 },
      uSpeed: { value: 0.35 }, uSpacing: { value: 0.45 },
    },
    transparent: true, depthWrite: false, depthTest: true, blending: AdditiveBlending,
  });
  const arcs = new LineSegments(arcGeo, arcMat);
  arcs.frustumCulled = false;
  scene.add(arcs);
  const knn = data.sphere.knn ?? null;
  const _a = new Vector3(), _b = new Vector3(), _m = new Vector3();
  function buildArcs(i: number): number {
    const nb = knn?.[i] ?? [];
    // behind the shell: outside it when seen from the origin, inside it when orbiting; tiles occlude the arcs
    const out = mode === "globe" ? -1 : 1;
    const r = 1 + out * 0.04;
    _a.set(centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]);
    let w = 0, v = 0;
    for (let k = 0; k < Math.min(K_MAX, nb.length); k++) {
      const j = nb[k];
      _b.set(centers[j * 3], centers[j * 3 + 1], centers[j * 3 + 2]);
      const omega = Math.acos(Math.max(-1, Math.min(1, _a.dot(_b))));
      const so = Math.sin(omega) || 1e-6;
      for (let t = 0; t < SEG; t++) {
        for (const f of [t / SEG, (t + 1) / SEG]) {
          const wa = Math.sin((1 - f) * omega) / so, wb = Math.sin(f * omega) / so;
          _m.set(0, 0, 0).addScaledVector(_a, wa).addScaledVector(_b, wb).normalize();
          // lift the arc's middle a little so long arcs read as cords, not as paint on the shell
          const lift = 1 + out * 0.18 * Math.sin(f * Math.PI) * (omega / Math.PI);
          _m.multiplyScalar(r * lift);
          arcPos[w++] = _m.x; arcPos[w++] = _m.y; arcPos[w++] = _m.z;
          arcT[v] = f; arcK[v] = k; arcL[v] = omega; v++;
        }
      }
    }
    arcAttr.needsUpdate = true;
    arcTAttr.needsUpdate = true;
    arcKAttr.needsUpdate = true;
    arcLAttr.needsUpdate = true;
    arcGeo.setDrawRange(0, w / 3);
    return nb.length;
  }
  const neigh = material.uniforms.uNeigh.value as Float32Array;
  function showNeighbors(i: number | null) {
    const u = arcMat.uniforms;
    gsap.killTweensOf([u.uOpacity, u.uProgress, material.uniforms.uNeighDim, material.uniforms.uNeighScale]);
    if (i === null || !knn || knn[i].length === 0) {
      gsap.to(u.uOpacity, { value: 0, duration: DUR.morph });
      gsap.to(material.uniforms.uNeighDim, { value: 1, duration: DUR.morph });
      gsap.to(material.uniforms.uNeighScale, { value: 1, duration: DUR.morph, onComplete: () => neigh.fill(-1) });
      return;
    }
    const nb = knn[i];
    for (let k = 0; k < 8; k++) neigh[k] = k < nb.length ? nb[k] : -1;
    buildArcs(i);
    // arcs grow out from the tile, then the neighbors swell as the arcs arrive
    u.uProgress.value = 0;
    gsap.to(u.uOpacity, { value: 1, duration: DUR.base });
    gsap.to(u.uProgress, { value: 1, duration: DUR.reveal * 0.75, ease: "power2.out" });
    gsap.to(material.uniforms.uNeighDim, { value: 0.3, duration: DUR.morph });
    gsap.to(material.uniforms.uNeighScale, { value: 1.14, duration: DUR.morph, delay: DUR.reveal * 0.4 });
  }

  // near field: the NEAR tiles closest to the view center get a 512px texture of
  // their own, drawn as a quad a hair in front of the atlas tile. Everything
  // else stays on the 192px atlas. Textures are cached and the cache is capped.
  const NEAR = 28, NEAR_LONG = 512, NEAR_CACHE = 72;
  const nearCache = new Map<string, Texture | null>(); // null = loading
  const nearInUse = new Set<string>();
  const nearGeo = new PlaneGeometry(1, 1);
  const nearPool = Array.from({ length: NEAR }, () => {
    const m = new Mesh(nearGeo, new MeshBasicMaterial({ color: 0xffffff }));
    m.matrixAutoUpdate = false;
    m.visible = false;
    m.frustumCulled = false;
    scene.add(m);
    return m;
  });
  const loadNear = (i: number): Texture | null => {
    const path = points[i].thumb;
    if (!path) return null;
    if (nearCache.has(path)) return nearCache.get(path) ?? null;
    nearCache.set(path, null);
    const img = new Image();
    img.onload = () => {
      if (disposed) return;
      const k = NEAR_LONG / Math.max(img.naturalWidth, img.naturalHeight);
      const c = document.createElement("canvas");
      c.width = Math.max(1, Math.round(img.naturalWidth * k));
      c.height = Math.max(1, Math.round(img.naturalHeight * k));
      c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
      const tex = new Texture(c);
      tex.colorSpace = SRGBColorSpace; // decoded then re-encoded: lands on the same bytes as the raw atlas tiles
      tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
      tex.needsUpdate = true;
      nearCache.set(path, tex);
      if (nearCache.size > NEAR_CACHE) {
        for (const [k2, t2] of nearCache) {
          if (nearCache.size <= NEAR_CACHE) break;
          if (t2 && !nearInUse.has(k2)) { t2.dispose(); nearCache.delete(k2); }
        }
      }
    };
    img.src = `/vault-media/${path}`;
    return null;
  };
  const _nn = new Vector3(), _ne1 = new Vector3(), _ne2 = new Vector3(), _nc = new Vector3(), _nref = new Vector3();
  const _m4 = new Matrix4();
  const nearScore = new Float32Array(n);
  const nearIdx = Array.from({ length: n }, (_, i) => i);
  let nearTick = 0;
  const updateNear = () => {
    const f = facing();
    const u = material.uniforms;
    // rank every 4th frame; place every frame (cheap)
    if (nearTick++ % 4 === 0) {
      if (mode === "globe") _nc.copy(camera.position).normalize();
      else camera.getWorldDirection(_nc);
      for (let i = 0; i < n; i++) {
        nearScore[i] = points[i].thumb
          ? _nc.x * centers[i * 3] + _nc.y * centers[i * 3 + 1] + _nc.z * centers[i * 3 + 2]
          : -2;
      }
      nearIdx.sort((a, b) => nearScore[b] - nearScore[a]);
      nearInUse.clear();
      for (let k = 0; k < NEAR; k++) {
        const i = nearIdx[k];
        const tex = nearScore[i] > -2 ? loadNear(i) : null;
        const mesh = nearPool[k];
        mesh.userData.i = i;
        if (tex) {
          nearInUse.add(points[i].thumb!);
          const mat = mesh.material as MeshBasicMaterial;
          if (mat.map !== tex) { mat.map = tex; mat.needsUpdate = true; }
          mesh.visible = true;
        } else mesh.visible = false;
      }
    }
    const birth = u.uBirth.value as number;
    for (let k = 0; k < NEAR; k++) {
      const mesh = nearPool[k];
      if (!mesh.visible) continue;
      const i = mesh.userData.i as number;
      _nc.set(centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]);
      _nn.copy(_nc).negate().normalize().multiplyScalar(f);
      _nref.set(Math.abs(_nn.y) > 0.9 ? 1 : 0, Math.abs(_nn.y) > 0.9 ? 0 : 1, 0);
      _ne1.crossVectors(_nref, _nn).normalize();
      _ne2.crossVectors(_nn, _ne1);
      // mirror the vertex shader's scale chain exactly
      let sc = scales[i] * (i === hovered ? (u.uHoverScale.value as number) : 1);
      if (neigh.includes(i)) sc *= u.uNeighScale.value as number;
      const bornT = (birth * 1.35 - i / n) / 0.35;
      const born = bornT <= 0 ? 0 : bornT >= 1 ? 1 : bornT * bornT * (3 - 2 * bornT);
      sc *= born;
      const sx = Math.sqrt(aspects[i]);
      _ne1.multiplyScalar(TILE_HALF * 2 * sx * sc);
      _ne2.multiplyScalar(((TILE_HALF * 2) / sx) * sc);
      _m4.makeBasis(_ne1, _ne2, _nn);
      _nc.multiplyScalar(1 - f * 0.0015); // a hair toward the camera, in front of the atlas tile
      _m4.setPosition(_nc);
      mesh.matrix.copy(_m4);
      // mirror the fragment shader's dimming chain
      let dim = 1;
      if (focused >= 0 && i !== focused) dim *= u.uDim.value as number;
      const th = u.uTheme.value as number;
      if (th >= 0 && points[i].th !== th) dim *= u.uThemeDim.value as number;
      const nd = u.uNeighDim.value as number;
      if (nd < 1 && i !== hovered && !neigh.includes(i)) dim *= nd;
      (mesh.material as MeshBasicMaterial).color.setScalar(dim);
    }
  };

  const controls = createControls();
  const focusDolly = { dolly: 0 }; // inside mode: 0 at rest, 1 at apex
  const orbitR = { r: restGlobeR(0.5) }; // globe mode: current camera radius, rest -> apex
  let mode: OrbViewMode = "inside";
  let focused = -1;
  let hovered: number | null = null;
  let pointerNdc: [number, number] | null = null;
  let liveZoom = 0.5; // controls' wheel-zoom channel, latched each frame for focusTile/doBlur to read outside the loop
  let focusRaf1 = 0, focusRaf2 = 0; // reduced-motion focus's double-rAF; cancelled on dispose
  let focusCall: ReturnType<typeof gsap.delayedCall> | undefined; // pending onOpen handoff at 75% dolly
  const dir = new Vector3();
  const facing = (): 1 | -1 => (mode === "globe" ? -1 : 1);

  // yaw/pitch that place the camera on a unit direction's radial line, per the
  // current mode's orbit mapping (inside: forward = D; globe: camera = R*D).
  const anglesForDir = (x: number, y: number, z: number): { yaw: number; pitch: number } => {
    // globe branch negated to match the flipped orbit-position signs below
    // (user-felt trackball semantics, set empirically 2026-08-01)
    return mode === "globe"
      ? { yaw: -Math.atan2(x, z), pitch: -Math.asin(-y) }
      : { yaw: Math.atan2(x, -z), pitch: Math.asin(y) };
  };

  const anglesFor = (i: number): { yaw: number; pitch: number } =>
    anglesForDir(centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]);

  const ndcOf = (e: PointerEvent): [number, number] => {
    const r = canvas.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * 2 - 1, -(((e.clientY - r.top) / r.height) * 2 - 1)];
  };
  const onDown = (e: PointerEvent) => {
    canvas.setPointerCapture(e.pointerId);
    pointerNdc = ndcOf(e); // seed so a tap-without-move still has a pick target
    controls.down(e.clientX, e.clientY);
  };
  const onMove = (e: PointerEvent) => {
    pointerNdc = ndcOf(e);
    controls.move(e.clientX, e.clientY);
  };
  const onUp = (e: PointerEvent) => {
    const { tap } = controls.up();
    if (tap && focused < 0 && pointerNdc) {
      const hit = pickTile(pointerNdc[0], pointerNdc[1], camera, centers, TILE_HALF, facing(), aspects, scales);
      if (hit !== null) focusTile(hit);
    }
    canvas.releasePointerCapture(e.pointerId);
  };
  const onWheel = (e: WheelEvent) =>
    controls.wheel(normalizeWheelDelta(e.deltaY, e.deltaMode, canvas.clientHeight));
  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerup", onUp);
  canvas.addEventListener("wheel", onWheel, { passive: true });

  const apexRect = (i: number) => {
    dir.set(centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]);
    return tileScreenRect(camera, dir.clone(), TILE_HALF, canvas.clientWidth, canvas.clientHeight, facing());
  };

  // kills focus tweens/dims and returns the depth param to rest, for whichever
  // mode is current; setView calls this before flipping facing so a mode
  // switch mid-focus can't strand uFocused or leave the wrong depth tweening.
  function doBlur() {
    focusCall?.kill();
    focusCall = undefined;
    const done = () => { focused = -1; material.uniforms.uFocused.value = -1; };
    if (reducedMotion()) {
      if (mode === "globe") orbitR.r = restGlobeR(liveZoom); else focusDolly.dolly = 0;
      material.uniforms.uDim.value = 1;
      done();
      return;
    }
    // blur resumes at the live wheel-zoom radius, not a frozen constant, since
    // the user may have scrolled while focused
    if (mode === "globe") gsap.to(orbitR, { r: restGlobeR(liveZoom), duration: DUR.morph, onComplete: done });
    else gsap.to(focusDolly, { dolly: 0, duration: DUR.morph, onComplete: done });
    gsap.to(material.uniforms.uDim, { value: 1, duration: DUR.morph });
  }

  function focusTile(i: number) {
    focused = i;
    material.uniforms.uFocused.value = i;
    // the NoteViewer is about to cover the tile; a caption left over from
    // hover must not stay live behind it
    hovered = null;
    material.uniforms.uHovered.value = -1;
    showNeighbors(null);
    cb.onHover(null);
    const { yaw, pitch } = anglesFor(i);
    if (reducedMotion()) {
      controls.setTarget(yaw, pitch);
      if (mode === "globe") orbitR.r = GLOBE_APEX; else focusDolly.dolly = 1;
      material.uniforms.uDim.value = DIM_FOCUS;
      // one frame so the camera pose lands before projecting; handles tracked
      // so dispose() can cancel them if focus() fires just before unmount
      focusRaf1 = requestAnimationFrame(() => {
        focusRaf2 = requestAnimationFrame(() => {
          const rect = apexRect(i);
          cb.onOpen(i, rect);
        });
      });
      return;
    }
    controls.setTarget(yaw, pitch);
    if (mode === "globe") {
      orbitR.r = restGlobeR(liveZoom); // seed the tween's start at the live wheel-zoom radius, not a stale one
      gsap.to(orbitR, { r: GLOBE_APEX, duration: DUR.reveal });
    } else {
      gsap.to(focusDolly, { dolly: 1, duration: DUR.reveal });
    }
    gsap.to(material.uniforms.uDim, { value: DIM_FOCUS, duration: DUR.reveal });
    // let the FLIP panel start growing before the dolly finishes arriving,
    // so camera and panel motion overlap instead of running end-to-end
    focusCall = gsap.delayedCall(DUR.reveal * 0.75, () => {
      const rect = apexRect(i);
      cb.onOpen(i, rect);
    });
  }

  let raf = 0;
  let last = performance.now();
  let idle = 0; // seconds since the last drag, hover or focus; past IDLE_AFTER the sphere drifts
  const IDLE_AFTER = 2.5, DRIFT = 0.03; // rad/s once fully drifting
  const loop = (now: number) => {
    raf = requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    arcMat.uniforms.uTime.value += dt;
    const busy = controls.dragging || hovered !== null || focused >= 0;
    idle = busy ? 0 : idle + dt;
    if (idle > IDLE_AFTER && !reducedMotion()) controls.nudge(DRIFT * dt * Math.min(1, (idle - IDLE_AFTER) / 2));
    const { yaw, pitch, zoom } = controls.step(dt);
    liveZoom = zoom;
    if (mode === "globe") {
      // orbit-from-outside: camera circles the sphere at radius orbitR.r while
      // focused, otherwise at the live wheel-zoom radius; always looking at
      // the center. Signs flipped vs. inside mode: user-felt trackball
      // semantics, set empirically 2026-08-01.
      const gyaw = -yaw, gpitch = -pitch;
      const cosP = Math.cos(gpitch);
      const r = focused >= 0 ? orbitR.r : restGlobeR(zoom);
      camera.position.set(Math.sin(gyaw) * cosP * r, -Math.sin(gpitch) * r, Math.cos(gyaw) * cosP * r);
      camera.lookAt(0, 0, 0);
    } else {
      // orbit-from-origin: camera rotates in place, dollies toward the focused tile
      camera.position.set(0, 0, 0);
      if (focused >= 0 && focusDolly.dolly > 0) {
        dir.set(centers[focused * 3], centers[focused * 3 + 1], centers[focused * 3 + 2]);
        camera.position.addScaledVector(dir, focusDolly.dolly * DOLLY);
      }
      camera.rotation.set(0, 0, 0);
      camera.rotateY(-yaw);
      camera.rotateX(pitch);
      // wheel dolly: forward along the look direction, after orientation so it
      // moves along where the camera is actually pointed. Focus flight owns the
      // camera while focused; on blur this resumes from wherever zoom already is.
      if (focused < 0) {
        camera.getWorldDirection(dir);
        camera.position.addScaledVector(dir, wheelDollyOffset(zoom));
      }
    }
    camera.updateMatrixWorld();
    if (morphing) { stepMorph(); if (hovered !== null) buildArcs(hovered); }
    updateNear();
    if (!controls.dragging && focused < 0 && pointerNdc) {
      const hit = pickTile(pointerNdc[0], pointerNdc[1], camera, centers, TILE_HALF, facing(), aspects, scales);
      if (hit !== hovered) { hovered = hit; material.uniforms.uHovered.value = hit ?? -1; showNeighbors(hit); cb.onHover(hit); }
    }
    renderer.render(scene, camera);
  };
  raf = requestAnimationFrame(loop);
  if (reducedMotion()) material.uniforms.uBirth.value = 1;
  else gsap.to(material.uniforms.uBirth, { value: 1, duration: 1.8, ease: "power1.out" });

  const resize = new ResizeObserver(() => {
    const w = canvas.clientWidth, h = Math.max(1, canvas.clientHeight);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  });
  resize.observe(canvas);

  return {
    setLayout(name) {
      writeLayout(name);
      if (hovered !== null) buildArcs(hovered);
    },
    centerOf(i) {
      return [centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]];
    },
    setThemeFilter(th) { material.uniforms.uTheme.value = th ?? -1; },
    setView(next) {
      if (next === mode) return;
      if (focused >= 0) doBlur(); // mode switches mid-focus must not strand uFocused
      mode = next;
      material.uniforms.uFacing.value = mode === "globe" ? -1 : 1;
      coast.visible = coastVisible(mode, coastLoaded, terrain);
    },
    setTerrain(on) {
      terrain = on;
      coast.visible = coastVisible(mode, coastLoaded, terrain);
    },
    aimAt(dir) {
      const l = Math.hypot(dir[0], dir[1], dir[2]);
      if (l < 1e-9) return; // a degenerate centroid keeps the default pose
      const { yaw, pitch } = anglesForDir(dir[0] / l, dir[1] / l, dir[2] / l);
      controls.setTarget(yaw, pitch);
    },
    focus: focusTile,
    blur: doBlur,
    dispose() {
      disposed = true;
      cancelAnimationFrame(raf);
      cancelAnimationFrame(focusRaf1);
      cancelAnimationFrame(focusRaf2);
      focusCall?.kill();
      resize.disconnect();
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("wheel", onWheel);
      gsap.killTweensOf(focusDolly);
      gsap.killTweensOf(orbitR);
      gsap.killTweensOf(material.uniforms.uDim);
      gsap.killTweensOf([material.uniforms.uNeighDim, material.uniforms.uNeighScale, material.uniforms.uBirth]);
      gsap.killTweensOf([arcMat.uniforms.uOpacity, arcMat.uniforms.uProgress]);
      gsap.killTweensOf(morph);
      for (const m of nearPool) (m.material as MeshBasicMaterial).dispose();
      nearGeo.dispose();
      for (const t of nearCache.values()) t?.dispose();
      nearCache.clear();
      arcGeo.dispose();
      arcMat.dispose();
      plane.dispose();
      geo.dispose();
      material.dispose();
      atlas.dispose();
      coastGeo.dispose();
      coastMat.dispose();
      coastRamp.dispose();
      coastFallback.dispose();
      if (coastTex) coastTex.dispose();
      renderer.dispose();
    },
  };
}
