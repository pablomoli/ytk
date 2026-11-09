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
  Mesh,
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
  s *= born;
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
  const writeLayout = (name: LayoutName) => {
    const arr = data.sphere[name] ?? data.sphere[data.sphere.chosen];
    if (!arr || arr.length < n) {
      console.warn(`orb: layout "${name}" missing or short (${arr?.length ?? 0} < ${n}); keeping current centers`);
      return;
    }
    for (let i = 0; i < n; i++) centers.set(arr[i], i * 3);
  };
  writeLayout(data.sphere.chosen);

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
  const K_MAX = 8, SEG = 48;
  const arcPos = new Float32Array(K_MAX * SEG * 2 * 3);
  const arcT = new Float32Array(K_MAX * SEG * 2); // 0 at the hovered tile, 1 at the neighbor
  const arcK = new Float32Array(K_MAX * SEG * 2); // which neighbor, so pulses desynchronize
  const arcGeo = new BufferGeometry();
  // BufferAttribute wraps the arrays; Float32BufferAttribute would copy them and swallow every later write
  const arcAttr = new BufferAttribute(arcPos, 3);
  const arcTAttr = new BufferAttribute(arcT, 1);
  const arcKAttr = new BufferAttribute(arcK, 1);
  arcGeo.setAttribute("position", arcAttr);
  arcGeo.setAttribute("aT", arcTAttr);
  arcGeo.setAttribute("aK", arcKAttr);
  arcGeo.setDrawRange(0, 0);
  const arcMat = new RawShaderMaterial({
    glslVersion: GLSL3,
    vertexShader: /* glsl */ `
precision highp float;
in vec3 position; in float aT; in float aK;
uniform mat4 modelViewMatrix, projectionMatrix;
out float vT; out float vK;
void main() { vT = aT; vK = aK; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: /* glsl */ `
precision highp float;
uniform float uProgress; // how far along each arc has grown, 0..1
uniform float uOpacity;
uniform float uTime;
in float vT; in float vK;
out vec4 outColor;
void main() {
  if (vT > uProgress) discard;
  // a pulse leaves the hovered tile every ~2.2 s per arc, staggered by neighbor, with a tail behind it
  float ph = fract(uTime * 0.45 + vK * 0.19);
  float d = vT - ph;
  float head = exp(-d * d / 0.0012);
  float tail = d < 0.0 ? exp(d * 9.0) * 0.55 : 0.0;
  float glow = 0.28 + head + tail;
  vec3 brass = vec3(0.886, 0.690, 0.290);
  outColor = vec4(mix(brass, vec3(1.0, 0.95, 0.8), head) * glow, glow * uOpacity);
}`,
    uniforms: { uProgress: { value: 0 }, uOpacity: { value: 0 }, uTime: { value: 0 } },
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
          arcT[v] = f; arcK[v] = k; v++;
        }
      }
    }
    arcAttr.needsUpdate = true;
    arcTAttr.needsUpdate = true;
    arcKAttr.needsUpdate = true;
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
    for (let k = 0; k < K_MAX; k++) neigh[k] = k < nb.length ? nb[k] : -1;
    buildArcs(i);
    // arcs grow out from the tile, then the neighbors swell as the arcs arrive
    u.uProgress.value = 0;
    gsap.to(u.uOpacity, { value: 1, duration: DUR.base });
    gsap.to(u.uProgress, { value: 1, duration: DUR.reveal * 0.75, ease: "power2.out" });
    gsap.to(material.uniforms.uNeighDim, { value: 0.3, duration: DUR.morph });
    gsap.to(material.uniforms.uNeighScale, { value: 1.14, duration: DUR.morph, delay: DUR.reveal * 0.4 });
  }

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
      const hit = pickTile(pointerNdc[0], pointerNdc[1], camera, centers, TILE_HALF, facing(), aspects);
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
    if (!controls.dragging && focused < 0 && pointerNdc) {
      const hit = pickTile(pointerNdc[0], pointerNdc[1], camera, centers, TILE_HALF, facing(), aspects);
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
      iPos.needsUpdate = true;
      if (hovered !== null) buildArcs(hovered);
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
