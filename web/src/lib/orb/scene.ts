import {
  AdditiveBlending,
  BufferGeometry,
  ClampToEdgeWrapping,
  DataTexture,
  BufferAttribute,
  CanvasTexture,
  Group,
  LineBasicMaterial,
  LineLoop,
  Sprite,
  SpriteMaterial,
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
import { createRing, type RingData, type RingHandle, type RingItem } from "./ring";

export const TILE_HALF = 0.055; // ~4.5deg cell radius, sized for the content-set scale (~500 tiles)
// search gather: three rows of four span GATHER_FILL of the view height, and the
// widest cover takes GATHER_TILE of its slot. The grid is a flat sheet facing the
// camera, held just inside the shell or floated well clear of it from outside.
const MATCH_MAX = 12, GATHER_COLS = 4, GATHER_ROWS = 3, GATHER_FILL = 0.62, GATHER_TILE = 0.93;
const GATHER_LIFT_IN = 0.1, GATHER_LIFT_OUT = 0.4, GATHER_HOP = 0.1;
const GATHER_DUR = 0.85, GATHER_STAGGER = 0.035;
const SEARCH_DIM = 0.16;
// Apex40 previz verdict (user-reviewed, Apex Manim render): DOLLY = 1 -
// 0.055/(0.40 * tan 30deg) = 0.76. Final; do not derive from a different apex.
const DOLLY = 0.76;
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
// sphere radius range; below 0.45 the far globe orbit leaves the far plane
export const RADIUS_MIN = 0.45;
export const RADIUS_MAX = 2.5;
// theme tint: blob width in tile widths, and the alpha of one blob; ~8 overlap at lattice spacing
const TINT_SPAN = 3.4;
const TINT_LEVEL = 0.25;
// the veil over the tiles, as a share of the field: more from the globe, where tiles leave few gaps
const VEIL_GLOBE = 0.22;
const VEIL_INSIDE = 0.0;
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
in float iFlat;  // 0 on the sphere, 1 on the search sheet
uniform mat4 modelViewMatrix, projectionMatrix;
uniform vec3 uFlatR, uFlatU; // the sheet's right and up
uniform float uHovered, uHoverScale, uFocused;
uniform float uSize; // tile size against the unit sphere: falls as the sphere radius grows
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
  if (iFlat > 0.0) { e1 = normalize(mix(e1, uFlatR, iFlat)); e2 = normalize(mix(e2, uFlatU, iFlat)); }
  float s = (abs(iIdx - uHovered) < 0.5 || abs(iIdx - uFocused) < 0.5) ? uHoverScale : 1.0;
  for (int k = 0; k < 8; k++) if (abs(iIdx - uNeigh[k]) < 0.5) s *= uNeighScale;
  float born = smoothstep(0.0, 1.0, (uBirth * 1.35 - iIdx / uCount) / 0.35);
  s *= born * iScale * uSize;
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
uniform float uMatch[12];          // tiles a search has gathered (-1 = none)
uniform float uSearchDim;          // 1 = off; below 1 dims every tile the search did not match
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
    bool keep = abs(vIdx - uHovered) < 0.5 || abs(vIdx - uFocused) < 0.5;
    for (int k = 0; k < 8; k++) if (abs(vIdx - uNeigh[k]) < 0.5) keep = true;
    if (!keep) dim *= uNeighDim;
  }
  if (uSearchDim < 1.0) {
    bool hit = abs(vIdx - uFocused) < 0.5 || abs(vIdx - uHovered) < 0.5;
    for (int k = 0; k < 12; k++) if (abs(vIdx - uMatch[k]) < 0.5) hit = true;
    if (!hit) dim *= uSearchDim;
  }
  outColor = vec4(c * dim, 1.0);
}`;

// theme tint: one soft blob per tagged tile, pushed behind the shell
const TINT_VERT = /* glsl */ `
precision highp float;
in vec3 position;
in vec2 uv;
in vec3 iPos;
in vec3 iTint;
in float iScale;
in float iIdx;
in float iTheme;
in float iFlat;
uniform mat4 modelViewMatrix, projectionMatrix;
uniform float uFacing, uSpan, uBirth, uCount, uSize;
uniform float uLift; // radial offset: positive is behind the shell, negative in front
uniform float uTime;
out vec2 vP;
out float vBreath;
out vec3 vTint;
out float vTheme;
void main() {
  vec3 n = normalize(-iPos) * uFacing;
  vec3 ref = abs(n.y) > 0.9 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0);
  vec3 e1 = normalize(cross(ref, n));
  vec3 e2 = cross(n, e1);
  float born = smoothstep(0.0, 1.0, (uBirth * 1.35 - iIdx / uCount) / 0.35);
  vec3 world = iPos * (1.0 + uFacing * uLift) + (e1 * position.x + e2 * position.y) * uSpan * iScale * uSize * born * (1.0 - iFlat);
  vP = uv * 2.0 - 1.0;
  vTint = iTint;
  vTheme = iTheme;
  // two slow waves keyed to position: nearby blobs breathe together, so light drifts across a theme like mist
  vBreath = 0.56 + 0.3 * sin(uTime * 0.31 + dot(iPos, vec3(5.1, 3.7, 4.3))) + 0.14 * sin(uTime * 0.19 + dot(iPos, vec3(-3.3, 6.1, 2.2)));
  gl_Position = projectionMatrix * modelViewMatrix * vec4(world, 1.0);
}`;

const TINT_FRAG = /* glsl */ `
precision highp float;
uniform float uLevel, uTheme;
in vec2 vP;
in vec3 vTint;
in float vTheme;
in float vBreath;
out vec4 outColor;
void main() {
  if (vTheme < 0.0) discard;
  // gaussian that reaches exactly zero at the quad edge, so no square shows
  float r2 = dot(vP, vP);
  float a = exp(-r2 * 2.2) - 0.1108;
  if (a <= 0.0) discard;
  // a tight core hugs the tile; the wide tail is only a whisper, so the sky between stays black
  a = a * 0.15 + exp(-r2 * 10.0);
  if (uTheme >= 0.0 && abs(vTheme - uTheme) >= 0.5) a *= 0.12;
  outColor = vec4(vTint, a * uLevel * vBreath);
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
  setDock(px: number): void;
  setRadius(r: number): void;
  // tile indices, best first: they gather in front of the camera. null sends them home.
  // inset: css px the page's panels cover on the left; the sheet centers in what is left
  setSearch(hits: number[] | null, inset?: number): void;
  dispose(): void;
};

export function mountOrb(
  canvas: HTMLCanvasElement,
  data: OrbData,
  cb: {
    onHover(i: number | null): void;
    onOpen(i: number, rect: DOMRect): void;
    onBlur(): void;
    onRingHover?(item: RingItem | null): void;
  },
): OrbHandle {
  const cap = COLS * COLS; // atlas has exactly this many slots; beyond it uvRect wraps
  const n = Math.min(data.points.length, cap);
  if (n < data.points.length) {
    console.warn(`orb: dropping ${data.points.length - n} points beyond atlas capacity (${cap})`);
  }
  const points = data.points.slice(0, n);
  const renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const camera = new PerspectiveCamera(60, canvas.clientWidth / Math.max(1, canvas.clientHeight), 0.01, 16);
  const scene = new Scene();
  // the scene stays a unit sphere: a radius R is drawn by shrinking tiles and camera distances instead
  const radius = { v: 1, target: 1 };
  // tiles give back a little of the shrink, so an exploded sphere is not a field of specks
  const sizeK = () => Math.pow(radius.v, -0.75);
  const half = () => TILE_HALF * sizeK();
  // the camera backs off slower than the sphere grows, so it swells in frame, and never ends up inside it
  const globeR = (z: number) => Math.max(restGlobeR(z) * Math.pow(Math.max(1, radius.v), 0.6), radius.v + 0.3) / radius.v;
  const apexR = () => 1 + (GLOBE_APEX - 1) * sizeK();
  const dollyK = () => 1 - (1 - DOLLY) * sizeK();

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
  // time lens: latitude by date rank (equal-area bands, newest at the north pole,
  // undated at the south), longitude from the neighbors layout so a theme stays
  // in its band of the sky while its members spread along it by age
  let timeLayout: number[][] | null = null;
  // ring per boundary: every month of the newest year, every year before it. Rank
  // latitude means a busy month is a fat band and a quiet year a thin one.
  const timeBounds: { lat: number; label: string }[] = [];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const timeArray = (): number[][] => {
    if (timeLayout) return timeLayout;
    const radial = data.sphere.radial;
    const order = points.map((_, i) => i).sort((a, b) => {
      const da = points[a].d ?? "", db = points[b].d ?? "";
      return da < db ? -1 : da > db ? 1 : a - b; // oldest first; undated ("") sort first = south pole
    });
    const out: number[][] = new Array(n);
    const latOf = (rank: number) => Math.asin((2 * rank) / n - 1); // -pi/2 oldest .. +pi/2 newest
    const newestYear = (points[order[n - 1]].d ?? "").slice(0, 4);
    let prevKey = "";
    order.forEach((i, rank) => {
      const lat = latOf(rank + 0.5);
      const lon = Math.atan2(radial[i][0], radial[i][2]);
      out[i] = [Math.cos(lat) * Math.sin(lon), Math.sin(lat), Math.cos(lat) * Math.cos(lon)];
      const d = points[i].d ?? "";
      if (!d) return;
      const key = d.slice(0, 4) === newestYear ? d.slice(0, 7) : d.slice(0, 4);
      if (key !== prevKey) {
        const label = key.length === 7 ? `${MONTHS[Number(key.slice(5, 7)) - 1]} ${key.slice(0, 4)}` : key;
        timeBounds.push({ lat: latOf(rank), label });
        prevKey = key;
      }
    });
    timeLayout = out;
    return out;
  };
  // the rings and their labels live in one group, shown only on the time lens
  const rings = new Group();
  rings.visible = false;
  scene.add(rings);
  const ringMat = new LineBasicMaterial({ color: 0xb7b5aa, transparent: true, opacity: 0, depthWrite: false });
  const ringLabels: { sprite: Sprite; lat: number }[] = [];
  let ringsBuilt = false;
  const ringLabelLevel = { v: 0 };
  const buildRings = () => {
    if (ringsBuilt) return;
    ringsBuilt = true;
    timeArray();
    for (const b of timeBounds) {
      const pts = new Float32Array(129 * 3);
      for (let k = 0; k <= 128; k++) {
        const a = (k / 128) * Math.PI * 2;
        pts.set([Math.cos(b.lat) * Math.sin(a), Math.sin(b.lat), Math.cos(b.lat) * Math.cos(a)], k * 3);
      }
      const g = new BufferGeometry();
      g.setAttribute("position", new BufferAttribute(pts, 3));
      rings.add(new LineLoop(g, ringMat));
      const c = document.createElement("canvas");
      c.width = 256; c.height = 64;
      const ctx = c.getContext("2d")!;
      ctx.font = "500 30px Newsreader, Georgia, serif";
      ctx.fillStyle = "#f0eee7";
      ctx.textBaseline = "middle";
      ctx.fillText(b.label, 8, 32);
      const tex = new CanvasTexture(c);
      tex.colorSpace = SRGBColorSpace;
      const sprite = new Sprite(new SpriteMaterial({ map: tex, transparent: true, opacity: 0, depthWrite: false, depthTest: false }));
      sprite.scale.set(0.22, 0.055, 1);
      sprite.center.set(0, 0.5); // anchored at the ring, text runs to the right
      rings.add(sprite);
      ringLabels.push({ sprite, lat: b.lat });
    }
  };
  let lens: LayoutName = data.sphere.chosen;
  const _rc = new Vector3();
  const updateRings = () => {
    if (!rings.visible) return;
    const f = facing();
    const r = 1 + f * 0.035; // behind the shell, like the arcs
    rings.scale.setScalar(r);
    // labels sit at the longitude that faces the camera, a little past the ring's front edge
    if (mode === "globe") _rc.copy(camera.position); else camera.getWorldDirection(_rc);
    const lon = Math.atan2(_rc.x, _rc.z) + (mode === "globe" ? 0.22 : -0.22);
    for (const { sprite, lat } of ringLabels) {
      sprite.position.set(Math.cos(lat) * Math.sin(lon), Math.sin(lat) + 0.012, Math.cos(lat) * Math.cos(lon));
      sprite.material.opacity = ringLabelLevel.v * (1 - selFade.v);
    }
  };
  const showRings = (on: boolean) => {
    gsap.killTweensOf([ringMat, ringLabelLevel]);
    if (on) {
      buildRings();
      rings.visible = true;
      gsap.to(ringMat, { opacity: 0.28, duration: 0.9, delay: 0.3 });
      gsap.to(ringLabelLevel, { v: 0.85, duration: 0.9, delay: 0.3 });
    } else {
      gsap.to(ringMat, { opacity: 0, duration: 0.4 });
      gsap.to(ringLabelLevel, { v: 0, duration: 0.4, onComplete: () => { rings.visible = false; } });
    }
  };
  const layoutArray = (name: LayoutName): number[][] | null => {
    if (name === "time") return timeArray();
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
  const flat = new Float32Array(n);
  const iFlat = new InstancedBufferAttribute(flat, 1);
  const sheet = { amt: flat, right: new Vector3(1, 0, 0), up: new Vector3(0, 1, 0) };
  geo.setAttribute("iScale", iScale);
  // home is where the lens puts each tile; centers and scales are what is drawn.
  // They differ only for tiles a search has in flight or gathered.
  const home = centers.slice(), homeScales = scales.slice();
  // tiles slide along the sphere from one layout to the next instead of jumping
  const writeLayout = (name: LayoutName) => {
    const arr = layoutArray(name);
    if (!arr) return;
    lens = name;
    showRings(name === "time");
    showThemeLabels(name === "lattice");
    morphFrom.set(home);
    scaleFrom.set(homeScales);
    for (let i = 0; i < n; i++) morphTo.set(arr[i], i * 3);
    densityScales(morphTo, aspects, scaleTo);
    if (reducedMotion()) {
      home.set(morphTo); homeScales.set(scaleTo);
      compose(0);
      return;
    }
    gsap.killTweensOf(morph);
    morph.t = 0; morphing = true;
    gsap.to(morph, { t: 1, duration: 0.9, ease: "power2.inOut", onComplete: () => { stepMorph(); compose(0); morphing = false; } });
  };
  const stepMorph = () => {
    const t = morph.t;
    for (let i = 0; i < n; i++) {
      const x = morphFrom[i * 3] + (morphTo[i * 3] - morphFrom[i * 3]) * t;
      const y = morphFrom[i * 3 + 1] + (morphTo[i * 3 + 1] - morphFrom[i * 3 + 1]) * t;
      const z = morphFrom[i * 3 + 2] + (morphTo[i * 3 + 2] - morphFrom[i * 3 + 2]) * t;
      const l = Math.hypot(x, y, z) || 1; // back onto the unit sphere; antipodal pairs are not in the data
      home[i * 3] = x / l; home[i * 3 + 1] = y / l; home[i * 3 + 2] = z / l;
      homeScales[i] = scaleFrom[i] + (scaleTo[i] - scaleFrom[i]) * t;
    }
  };

  // search gather: matched tiles leave their place on the sphere for a grid in
  // front of the camera, best match first in reading order, and fly home on release
  type Flight = {
    from: Vector3; to: Vector3 | null; cur: Vector3; // unit directions; to = null means home
    m0: number; m1: number; m: number; // how gathered: 0 at home, 1 in the grid
    size: number; lift: number; hop: number; t: number; delay: number;
  };
  const flights = new Map<number, Flight>();
  let searchHits: number[] = [];
  let matchSet = new Set<number>();
  let gatherCall: ReturnType<typeof gsap.delayedCall> | undefined;
  const _fh = new Vector3(), _gc = new Vector3(), _gp = new Vector3();
  // 1 with no search, 0 once the matches are gathered
  const searchOff = () => ((material.uniforms.uSearchDim.value as number) - SEARCH_DIM) / (1 - SEARCH_DIM);
  const homeDir = (i: number, out: Vector3) => out.set(home[i * 3], home[i * 3 + 1], home[i * 3 + 2]);
  const slerpDir = (a: Vector3, b: Vector3, t: number, out: Vector3) => {
    const om = Math.acos(Math.max(-1, Math.min(1, a.dot(b))));
    const so = Math.sin(om);
    if (so < 1e-4) return out.copy(t < 0.5 ? a : b); // same point, or exact opposites with no single path
    return out.copy(a).multiplyScalar(Math.sin((1 - t) * om) / so).addScaledVector(b, Math.sin(t * om) / so).normalize();
  };
  const launch = (i: number, to: Vector3 | null, m1: number, size: number, lift: number, delay: number) => {
    const old = flights.get(i);
    const from = old ? old.cur.clone() : homeDir(i, new Vector3());
    const m0 = old ? old.m : 0;
    const om = Math.acos(Math.max(-1, Math.min(1, from.dot(to ?? homeDir(i, _fh)))));
    // a long trip arcs off the shell toward the camera so it passes over the tiles between, not through them
    const hop = GATHER_HOP * Math.min(1, om / 0.8);
    // a trip home keeps the size and lift it left the grid with, and m carries both back to zero
    const keep = old && !to;
    flights.set(i, { from, to, cur: from.clone(), m0, m1, m: m0, size: keep ? old.size : size, lift: keep ? old.lift : lift, hop, t: 0, delay });
  };
  const stepFlights = (dt: number) => {
    const f = facing();
    for (const [i, fl] of flights) {
      fl.t += dt;
      const raw = reducedMotion() ? 1 : Math.max(0, Math.min(1, (fl.t - fl.delay) / GATHER_DUR));
      const e = raw * raw * (3 - 2 * raw);
      slerpDir(fl.from, fl.to ?? homeDir(i, _fh), e, fl.cur);
      fl.m = fl.m0 + (fl.m1 - fl.m0) * e;
      const rad = 1 - f * (fl.lift * fl.m + fl.hop * Math.sin(Math.PI * e));
      centers[i * 3] = fl.cur.x * rad; centers[i * 3 + 1] = fl.cur.y * rad; centers[i * 3 + 2] = fl.cur.z * rad;
      scales[i] = homeScales[i] + (fl.size - homeScales[i]) * fl.m;
      flat[i] = fl.m;
      if (raw >= 1 && fl.to === null) flights.delete(i);
    }
  };
  // the drawn buffers: every tile at home, then the flights on top
  const compose = (dt: number) => {
    centers.set(home);
    scales.set(homeScales);
    flat.fill(0);
    stepFlights(dt);
    iPos.needsUpdate = true; iScale.needsUpdate = true; iFlat.needsUpdate = true;
  };
  const dimSearch = (on: boolean) => {
    const u = material.uniforms.uSearchDim;
    gsap.killTweensOf(u);
    gsap.to(u, { value: on ? SEARCH_DIM : 1, duration: reducedMotion() ? 0 : DUR.morph });
  };
  const release = () => {
    gatherCall?.kill();
    gatherCall = undefined;
    gatherDue = false;
    for (const i of [...flights.keys()]) launch(i, null, 0, 1, 0, 0);
  };
  // anchored once per call: a flat sheet square to the camera as it looks now; it does not follow a drag
  const gather = () => {
    showNeighbors(null); // a tile just read leaves its arcs up, and their dim would fall on the sheet
    const e = camera.matrixWorld.elements;
    sheet.right.set(e[0], e[1], e[2]);
    sheet.up.set(e[4], e[5], e[6]);
    camera.getWorldDirection(_gc);
    const f = facing(), camR = camera.position.length();
    // from outside the sheet never passes the midpoint between shell and camera, however far in the zoom is
    const dist = mode === "globe"
      ? camR - (1 + Math.min(GATHER_LIFT_OUT, (camR - 1) * 0.45))
      : 1 - GATHER_LIFT_IN - camera.position.dot(_gc);
    _gp.copy(camera.position).addScaledVector(_gc, dist);
    const p5 = camera.projectionMatrix.elements[5];
    // half the covered strip, in world units at the sheet's distance
    _gp.addScaledVector(sheet.right, (searchInset * dist) / (p5 * Math.max(1, canvas.clientHeight)));
    // sized on screen, not on the sphere: the same grid whatever the zoom, the view or the slider
    const step = (2 * GATHER_FILL * dist) / (p5 * GATHER_ROWS);
    let widest = 1;
    for (const i of searchHits) { const sx = Math.sqrt(aspects[i]); widest = Math.max(widest, sx, 1 / sx); }
    const size = (GATHER_TILE * step) / (2 * widest * TILE_HALF * sizeK());
    const count = searchHits.length, rows = Math.ceil(count / GATHER_COLS);
    for (const i of [...flights.keys()]) if (!matchSet.has(i)) launch(i, null, 0, 1, 0, 0);
    searchHits.forEach((i, rank) => {
      const row = Math.floor(rank / GATHER_COLS);
      const cols = Math.min(GATHER_COLS, count - row * GATHER_COLS); // a short last row centers itself
      const to = new Vector3().copy(_gp)
        .addScaledVector(sheet.right, ((rank % GATHER_COLS) - (cols - 1) / 2) * step)
        .addScaledVector(sheet.up, ((rows - 1) / 2 - row) * step);
      const lift = f * (1 - to.length()); // each slot's own distance off the shell keeps the sheet flat
      launch(i, to.normalize(), 1, size, lift, rank * GATHER_STAGGER);
    });
    dimSearch(true);
  };
  // the sheet is measured from the camera, so the loop lays it out right after
  // placing the camera with nothing selected; a timer here would read a stale standpoint
  let gatherDue = false, searchInset = 0;
  const gatherSoon = (delay: number) => {
    gatherCall?.kill();
    gatherCall = undefined;
    if (delay <= 0 || reducedMotion()) gatherDue = true;
    else gatherCall = gsap.delayedCall(delay, () => { gatherDue = true; });
  };
  geo.setAttribute("iIdx", new InstancedBufferAttribute(Float32Array.from({ length: n }, (_, i) => i), 1));
  const themes = new Float32Array(n);
  points.forEach((p, i) => { themes[i] = p.th; });
  geo.setAttribute("iTheme", new InstancedBufferAttribute(themes, 1));
  geo.setAttribute("iFlat", iFlat);
  geo.instanceCount = n;

  const material = new RawShaderMaterial({
    glslVersion: GLSL3,
    vertexShader: VERT,
    fragmentShader: FRAG,
    side: DoubleSide,
    uniforms: {
      uAtlas: { value: atlas.texture },
      uHovered: { value: -1 }, uHoverScale: { value: 1.06 }, uSize: { value: 1 },
      uFocused: { value: -1 }, uDim: { value: 1 },
      uTheme: { value: -1 }, uThemeDim: { value: DIM_FILTER },
      uFacing: { value: 1 },
      uNeigh: { value: new Float32Array(8).fill(-1) }, uNeighDim: { value: 1 }, uNeighScale: { value: 1 },
      uBirth: { value: 0 }, uCount: { value: n },
      uMatch: { value: new Float32Array(MATCH_MAX).fill(-1) }, uSearchDim: { value: 1 },
      uFlatR: { value: sheet.right }, uFlatU: { value: sheet.up },
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
  // mirrors the vertex shader: tile i's basis from _nc, turned toward the sheet by its flat amount
  const tileBasis = (i: number, f: number) => {
    _nn.copy(_nc).negate().normalize().multiplyScalar(f);
    _nref.set(Math.abs(_nn.y) > 0.9 ? 1 : 0, Math.abs(_nn.y) > 0.9 ? 0 : 1, 0);
    _ne1.crossVectors(_nref, _nn).normalize();
    _ne2.crossVectors(_nn, _ne1);
    if (flat[i] > 0) {
      _ne1.lerp(sheet.right, flat[i]).normalize();
      _ne2.lerp(sheet.up, flat[i]).normalize();
      _nn.crossVectors(_ne1, _ne2).normalize();
    }
  };
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
      tileBasis(i, f);
      // mirror the vertex shader's scale chain exactly
      let sc = scales[i] * (i === hovered || i === focused ? (u.uHoverScale.value as number) : 1);
      if (neigh.includes(i)) sc *= u.uNeighScale.value as number;
      const bornT = (birth * 1.35 - i / n) / 0.35;
      const born = bornT <= 0 ? 0 : bornT >= 1 ? 1 : bornT * bornT * (3 - 2 * bornT);
      sc *= born;
      const sx = Math.sqrt(aspects[i]);
      _ne1.multiplyScalar(half() * 2 * sx * sc);
      _ne2.multiplyScalar(((half() * 2) / sx) * sc);
      _m4.makeBasis(_ne1, _ne2, _nn);
      _nc.multiplyScalar(1 - f * 0.0015); // a hair toward the camera, in front of the atlas tile
      _m4.setPosition(_nc);
      mesh.matrix.copy(_m4);
      // mirror the fragment shader's dimming chain
      let dim = 1;
      const th = u.uTheme.value as number;
      if (th >= 0 && points[i].th !== th) dim *= u.uThemeDim.value as number;
      const nd = u.uNeighDim.value as number;
      if (nd < 1 && i !== hovered && i !== focused && !neigh.includes(i)) dim *= nd;
      const sd = u.uSearchDim.value as number;
      if (sd < 1 && i !== hovered && i !== focused && !matchSet.has(i)) dim *= sd;
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
  let focusCall: ReturnType<typeof gsap.delayedCall> | undefined; // pending onOpen handoff
  // reading pane width in css px; while a tile is selected the picture shifts
  // left by half of it (lens shift, no rotation) so the tile centers in the sky that remains
  let dockPx = 0;
  const dock = { px: 0 };
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
    anglesForDir(home[i * 3], home[i * 3 + 1], home[i * 3 + 2]);

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
    if (tap && pointerNdc && ringHover === null) {
      const hit = pickTile(pointerNdc[0], pointerNdc[1], camera, centers, half(), facing(), aspects, scales, sheet);
      if (hit !== null) { if (hit !== focused) focusTile(hit); }
      else if (focused >= 0) { doBlur(); cb.onBlur(); }
    }
    canvas.releasePointerCapture(e.pointerId);
  };
  const onLeave = () => {
    pointerNdc = null;
    setRingHover(null);
    if (hovered === null) return;
    hovered = null;
    material.uniforms.uHovered.value = -1;
    if (focused < 0) showNeighbors(null);
    cb.onHover(null);
  };
  const onWheel = (e: WheelEvent) =>
    controls.wheel(normalizeWheelDelta(e.deltaY, e.deltaMode, canvas.clientHeight));
  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerup", onUp);
  canvas.addEventListener("pointerleave", onLeave);
  canvas.addEventListener("wheel", onWheel, { passive: true });

  const apexRect = (i: number) => {
    dir.set(home[i * 3], home[i * 3 + 1], home[i * 3 + 2]);
    return tileScreenRect(camera, dir.clone(), half(), canvas.clientWidth, canvas.clientHeight, facing());
  };

  // selection glow: a brass radial falloff drawn additively just behind the
  // tile, 2.4 tile widths across; the opaque tile hides the core and the
  // halo shows around its edge. Breathes slowly so the selection reads as alive.
  const glowTex = (() => {
    const c = document.createElement("canvas");
    c.width = c.height = 256;
    const g = c.getContext("2d")!;
    const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    grad.addColorStop(0, "rgba(240,238,231,0.5)");
    grad.addColorStop(0.45, "rgba(240,238,231,0.32)");
    grad.addColorStop(0.7, "rgba(240,238,231,0.09)");
    grad.addColorStop(1, "rgba(240,238,231,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, 256, 256);
    const t = new CanvasTexture(c);
    t.colorSpace = SRGBColorSpace;
    return t;
  })();
  const glowMat = new MeshBasicMaterial({ map: glowTex, transparent: true, opacity: 0, depthWrite: false, blending: AdditiveBlending });
  const glow = new Mesh(new PlaneGeometry(1, 1), glowMat);
  glow.matrixAutoUpdate = false;
  glow.renderOrder = 5;
  glow.visible = false;
  scene.add(glow);
  const glowLevel = { v: 0 }; // tweened 0..1; the breath rides on top
  // 1 while a tile is selected: the camera is close to the shell then, and
  // captions riding the shell would land huge over the selected tile
  const selFade = { v: 0 };
  const GLOW_SPAN = 1.7;
  let glowTime = 0;
  const placeGlow = (dt: number) => {
    glowTime += dt;
    if (glowLevel.v <= 0.001 || focused < 0) { glow.visible = false; return; }
    glow.visible = true;
    const i = focused, f = facing();
    const u = material.uniforms;
    _nc.set(centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]);
    tileBasis(i, f);
    const sc = scales[i] * (u.uHoverScale.value as number);
    const sx = Math.sqrt(aspects[i]);
    // square halo sized to the tile's longer side so a portrait reel gets the same margin as a landscape thumb
    const side = half() * 2 * sc * Math.max(sx, 1 / sx) * GLOW_SPAN;
    _ne1.multiplyScalar(side);
    _ne2.multiplyScalar(side);
    _m4.makeBasis(_ne1, _ne2, _nn);
    _nc.multiplyScalar(1 + f * 0.004); // behind the tile, in front of the arcs
    _m4.setPosition(_nc);
    glow.matrix.copy(_m4);
    const breath = reducedMotion() ? 1 : 0.85 + 0.15 * Math.sin(glowTime * 1.6);
    glowMat.opacity = glowLevel.v * breath;
  };

  // returns the camera depth and the lens shift to rest, for whichever mode is
  // current; setView calls this before flipping facing so a mode switch
  // mid-selection can't strand uFocused or leave the wrong depth tweening.
  function doBlur() {
    focusCall?.kill();
    focusCall = undefined;
    // back from a result: the matches gather again where the camera now looks
    if (focused >= 0 && searchHits.length) gatherSoon(DUR.reveal);
    const done = () => { focused = -1; material.uniforms.uFocused.value = -1; };
    gsap.killTweensOf([focusDolly, orbitR, dock, glowLevel]);
    if (reducedMotion()) {
      if (mode === "globe") orbitR.r = globeR(liveZoom); else focusDolly.dolly = 0;
      dock.px = 0;
      glowLevel.v = 0;
      selFade.v = 0;
      done();
      return;
    }
    gsap.to(glowLevel, { v: 0, duration: DUR.morph });
    gsap.to(selFade, { v: 0, duration: DUR.reveal, delay: DUR.morph });
    // blur resumes at the live wheel-zoom radius, not a frozen constant, since
    // the user may have scrolled while selected
    if (mode === "globe") gsap.to(orbitR, { r: globeR(liveZoom), duration: DUR.reveal, onComplete: done });
    else gsap.to(focusDolly, { dolly: 0, duration: DUR.reveal, onComplete: done });
    gsap.to(dock, { px: 0, duration: DUR.reveal });
  }

  // select a tile: the camera flies to it, its arcs and neighbors stay lit,
  // and the picture shifts to make room for the reading pane. Selecting
  // another tile while one is selected is a walk: step back, then approach.
  function focusTile(i: number) {
    const walking = focused >= 0;
    // the tile is read in its real place: the gather lets go and everyone flies home
    release();
    dimSearch(false);
    focused = i;
    material.uniforms.uFocused.value = i;
    if (hovered !== i) { hovered = i; material.uniforms.uHovered.value = i; cb.onHover(i); }
    showNeighbors(i);
    const { yaw, pitch } = anglesFor(i);
    controls.setTarget(yaw, pitch);
    cb.onOpen(i, apexRect(i));
    gsap.killTweensOf([focusDolly, orbitR, dock, glowLevel]);
    if (reducedMotion()) {
      if (mode === "globe") orbitR.r = apexR(); else focusDolly.dolly = 1;
      dock.px = dockPx;
      glowLevel.v = 0.8;
      selFade.v = 1;
      return;
    }
    // the glow lands as the camera arrives, not before
    gsap.fromTo(glowLevel, { v: walking ? glowLevel.v * 0.3 : 0 }, { v: 0.8, duration: DUR.reveal, delay: walking ? DUR.reveal * 0.5 : DUR.reveal * 0.4 });
    gsap.to(dock, { px: dockPx, duration: DUR.reveal });
    gsap.to(selFade, { v: 1, duration: DUR.morph });
    if (mode === "globe") {
      if (!walking) orbitR.r = globeR(liveZoom); // seed at the live wheel-zoom radius, not a stale one
      else gsap.to(orbitR, { r: apexR() + 0.5, duration: DUR.reveal * 0.5, ease: "power2.out" });
      gsap.to(orbitR, { r: apexR(), duration: walking ? DUR.reveal * 0.7 : DUR.reveal, delay: walking ? DUR.reveal * 0.5 : 0 });
    } else if (walking) {
      // a straight swap would snap the camera between two points inside the
      // sphere; stepping back to the center first reads as one movement
      gsap.to(focusDolly, { dolly: 0.15, duration: DUR.reveal * 0.5, ease: "power2.out" });
      gsap.to(focusDolly, { dolly: 1, duration: DUR.reveal * 0.7, delay: DUR.reveal * 0.5 });
    } else {
      gsap.to(focusDolly, { dolly: 1, duration: DUR.reveal });
    }
  }

  // theme tint: the blobs of one theme sum into a soft field that spans its
  // members and rides the same instance buffers, so it follows every lens morph
  const tintColors = new Float32Array(n * 3);
  {
    const nT = data.themes.length;
    const lat = data.sphere.lattice;
    const first = new Array<number>(nT).fill(2);
    if (lat) for (let i = 0; i < n; i++) {
      const th = points[i].th;
      if (th >= 0 && th < nT) first[th] = Math.min(first[th], lat[i][2]);
    }
    const rank = new Array<number>(nT);
    first.map((_, th) => th).sort((a, b) => first[a] - first[b]).forEach((th, k) => { rank[th] = k; });
    const hsl = (h: number, sat: number, l: number) => {
      const a = sat * Math.min(l, 1 - l);
      const ch = (k: number) => { const q = (k + h / 30) % 12; return l - a * Math.max(-1, Math.min(q - 3, 9 - q, 1)); };
      return [ch(0), ch(8), ch(4)];
    };
    for (let i = 0; i < n; i++) {
      const th = points[i].th;
      if (th < 0 || th >= nT) continue;
      // magenta through brass to teal, never blue; golden-ratio steps keep bands next to each other ~95 degrees apart
      const hue = (290 + ((rank[th] * 0.618034) % 1) * 245) % 360;
      tintColors.set(hsl(hue, 0.5, 0.56), i * 3);
    }
  }
  const tintGeo = new InstancedBufferGeometry();
  tintGeo.index = plane.index;
  tintGeo.setAttribute("position", plane.getAttribute("position"));
  tintGeo.setAttribute("uv", plane.getAttribute("uv"));
  for (const name of ["iPos", "iScale", "iIdx", "iTheme", "iFlat"]) tintGeo.setAttribute(name, geo.getAttribute(name));
  tintGeo.setAttribute("iTint", new InstancedBufferAttribute(tintColors, 3));
  tintGeo.instanceCount = n;
  const tintTime = { value: 0 };
  const tintLayer = (lift: number, order: number) => {
    const mat = new RawShaderMaterial({
      glslVersion: GLSL3,
      vertexShader: TINT_VERT,
      fragmentShader: TINT_FRAG,
      side: DoubleSide,
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
      uniforms: {
        uFacing: material.uniforms.uFacing, uBirth: material.uniforms.uBirth, uTheme: material.uniforms.uTheme, uSize: material.uniforms.uSize,
        uCount: { value: n }, uSpan: { value: TINT_SPAN }, uLevel: { value: 0 }, uLift: { value: lift }, uTime: tintTime,
      },
    });
    const m = new Mesh(tintGeo, mat);
    m.frustumCulled = false; // same reason as the tile mesh
    m.renderOrder = order;
    m.visible = false;
    scene.add(m);
    return m;
  };
  // the field behind the shell fills the gaps; a fainter veil in front lays the
  // same hue over the tiles, so a theme reads from the globe where gaps are few
  const tint = tintLayer(0.05, -1);
  const veil = tintLayer(-0.03, 4);
  const tintMat = tint.material as RawShaderMaterial, veilMat = veil.material as RawShaderMaterial;
  const tintLevel = { v: 0 };

  // theme labels. The lattice runs each theme along the Fibonacci spiral, so
  // a theme is a band of z around the spiral axis: a ring around the view when
  // you look along the axis, a vertical band from the side. Each band gets a
  // serif label riding its camera-facing side, shown only on the themes lens.
  type Band = { z: number; r: number; row: number; w: number; sprite: Sprite; mat: SpriteMaterial };
  const bands: Band[] = [];
  const labelGroup = new Group();
  labelGroup.visible = false;
  scene.add(labelGroup);
  let labelsOn = false;
  const buildThemeLabels = () => {
    if (bands.length) return;
    const arr = data.sphere.lattice;
    if (!arr) return;
    const lo = data.themes.map(() => 2), hi = data.themes.map(() => -2), cnt = data.themes.map(() => 0);
    for (let i = 0; i < n; i++) {
      const th = points[i].th;
      if (th < 0 || th >= lo.length) continue;
      lo[th] = Math.min(lo[th], arr[i][2]); hi[th] = Math.max(hi[th], arr[i][2]); cnt[th]++;
    }
    const order = data.themes.map((_, th) => th).filter((th) => cnt[th] > 0).sort((a, b) => lo[a] - lo[b]);
    order.forEach((th, k) => {
      const z = (lo[th] + hi[th]) / 2;
      const c = document.createElement("canvas");
      const g = c.getContext("2d")!;
      const font = "500 34px Newsreader, Georgia, serif";
      const text = data.themes[th].toLowerCase();
      const count = String(cnt[th]);
      g.font = font;
      const tw = Math.ceil(g.measureText(text).width);
      g.font = "500 24px Newsreader, Georgia, serif";
      const cw = Math.ceil(g.measureText(count).width);
      const w = tw + cw + 60;
      c.width = w; c.height = 72;
      g.fillStyle = "rgba(6,6,8,0.6)";
      g.beginPath(); g.roundRect(0, 8, w, 56, 10); g.fill();
      g.textBaseline = "middle";
      g.font = font; g.fillStyle = "#f0eee7"; g.fillText(text, 22, 37);
      g.font = "500 24px Newsreader, Georgia, serif"; g.fillStyle = "#e2b04a"; g.fillText(count, 22 + tw + 16, 38);
      const tex = new CanvasTexture(c);
      tex.colorSpace = SRGBColorSpace;
      const mat = new SpriteMaterial({ map: tex, transparent: true, opacity: 0, depthWrite: false, depthTest: false });
      const sprite = new Sprite(mat);
      sprite.center.set(0.5, 0.5);
      labelGroup.add(sprite);
      // bands are ~10 deg wide along the axis and a label is ~3x that, so
      // labels take turns in three rows around the band, a ladder, never a pile
      bands.push({ z, r: Math.sqrt(Math.max(0, 1 - z * z)), row: (k % 3) - 1, w: w / 72, sprite, mat });
    });
  };
  const labelLevel = { v: 0 };
  const _lv = new Vector3(), _lp = new Vector3();
  const updateThemeLabels = () => {
    if (!labelGroup.visible) return;
    const f = facing();
    if (mode === "globe") _lv.copy(camera.position).normalize(); else camera.getWorldDirection(_lv);
    // the label sits where the band faces the camera, a little past that point so it reads beside the tiles there
    const az0 = Math.atan2(_lv.y, _lv.x);
    const rr = 1 - f * 0.07;
    const h = mode === "globe" ? 0.06 : 0.034; // sprites shrink with distance; the globe sits ~2.5 away
    const step = mode === "globe" ? 0.42 : 0.46;
    // from outside, bands near the axis poles converge on the limb; fade them earlier
    const lo = mode === "globe" ? 0.4 : 0.25, span = mode === "globe" ? 0.4 : 0.45;
    for (const b of bands) {
      const az = az0 + b.row * step;
      _lp.set(b.r * Math.cos(az), b.r * Math.sin(az), b.z);
      b.sprite.position.copy(_lp).multiplyScalar(rr);
      b.sprite.scale.set(h * b.w, h, 1);
      const d = _lp.dot(_lv);
      const t = Math.min(1, Math.max(0, (d - lo) / span));
      b.mat.opacity = labelLevel.v * (1 - selFade.v) * searchOff() * t * t * (3 - 2 * t);
    }
  };
  const showThemeLabels = (on: boolean) => {
    if (on === labelsOn) return;
    labelsOn = on;
    gsap.killTweensOf([labelLevel, tintLevel]);
    if (on) {
      buildThemeLabels();
      labelGroup.visible = true;
      tint.visible = veil.visible = true;
      gsap.to(labelLevel, { v: 0.92, duration: 0.9, delay: 0.5 });
      gsap.to(tintLevel, { v: TINT_LEVEL, duration: 1.2, delay: 0.3 });
    } else {
      gsap.to(tintLevel, { v: 0, duration: 0.4, onComplete: () => { tint.visible = veil.visible = false; } });
      gsap.to(labelLevel, { v: 0, duration: 0.4, onComplete: () => { labelGroup.visible = false; } });
    }
  };

  // the pending ring: absent when the hub has no ring route, so the orb works without it
  let ring: RingHandle | null = null;
  let ringItems: RingItem[] = [];
  let ringHover: number | null = null;
  const ringIn = { v: 0 };
  const _rv = new Vector3();
  const setRingHover = (k: number | null) => {
    if (k === ringHover) return;
    ringHover = k;
    ring?.setHover(k);
    cb.onRingHover?.(k === null ? null : ringItems[k]);
  };
  fetch("/api/orb-ring")
    .then((r) => (r.ok ? (r.json() as Promise<RingData>) : null))
    .then((d) => {
      if (!d || disposed) return;
      ring = createRing(d, "/api/orb-ring.jpg", renderer.capabilities.getMaxAnisotropy());
      ringItems = d.items;
      scene.add(ring.group);
      gsap.to(ringIn, { v: 1, duration: reducedMotion() ? 0 : 1.4 });
    })
    .catch(() => {});

  let raf = 0;
  let last = performance.now();
  let idle = 0; // seconds since the last drag, hover or focus; past IDLE_AFTER the sphere drifts
  const IDLE_AFTER = 2.5, DRIFT = 0.03; // rad/s once fully drifting
  const loop = (now: number) => {
    raf = requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    arcMat.uniforms.uTime.value += dt;
    const busy = controls.dragging || hovered !== null || focused >= 0 || ringHover !== null || searchHits.length > 0;
    idle = busy ? 0 : idle + dt;
    if (idle > IDLE_AFTER && !reducedMotion()) controls.nudge(DRIFT * dt * Math.min(1, (idle - IDLE_AFTER) / 2));
    const { yaw, pitch, zoom } = controls.step(dt);
    liveZoom = zoom;
    radius.v = reducedMotion() ? radius.target : radius.v + (radius.target - radius.v) * (1 - Math.exp(-dt * 9));
    material.uniforms.uSize.value = sizeK();
    if (mode === "globe") {
      // orbit-from-outside: camera circles the sphere at radius orbitR.r while
      // focused, otherwise at the live wheel-zoom radius; always looking at
      // the center. Signs flipped vs. inside mode: user-felt trackball
      // semantics, set empirically 2026-08-01.
      const gyaw = -yaw, gpitch = -pitch;
      const cosP = Math.cos(gpitch);
      const r = focused >= 0 ? orbitR.r : globeR(zoom);
      camera.position.set(Math.sin(gyaw) * cosP * r, -Math.sin(gpitch) * r, Math.cos(gyaw) * cosP * r);
      camera.lookAt(0, 0, 0);
    } else {
      // orbit-from-origin: camera rotates in place, dollies toward the focused tile
      camera.position.set(0, 0, 0);
      if (focused >= 0 && focusDolly.dolly > 0) {
        dir.set(home[focused * 3], home[focused * 3 + 1], home[focused * 3 + 2]);
        camera.position.addScaledVector(dir, focusDolly.dolly * dollyK());
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
    // lens shift: three scales filmOffset by near/filmWidth against a frustum
    // 2*tan(fov/2)*aspect wide, so a fraction f of the viewport is f times that
    const frac = dock.px / (2 * Math.max(1, canvas.clientWidth));
    const shift = frac * camera.getFilmWidth() * 2 * Math.tan((camera.fov * Math.PI) / 360) * camera.aspect;
    if (shift !== camera.filmOffset) { camera.filmOffset = shift; camera.updateProjectionMatrix(); }
    camera.updateMatrixWorld();
    if (gatherDue && focused < 0) { gatherDue = false; gather(); }
    if (morphing) stepMorph();
    if (morphing || flights.size) { compose(dt); if (hovered !== null) buildArcs(hovered); }
    updateNear();
    updateRings();
    placeGlow(dt);
    // the tint steps back with the crowd when a hover dims it, and while reading
    if (tint.visible) {
      if (!reducedMotion()) tintTime.value += dt;
      const lv = tintLevel.v * (0.35 + 0.65 * (material.uniforms.uNeighDim.value as number)) * (1 - 0.4 * selFade.v)
        * (0.3 + 0.7 * (material.uniforms.uSearchDim.value as number));
      tintMat.uniforms.uLevel.value = lv;
      veilMat.uniforms.uLevel.value = lv * (mode === "globe" ? VEIL_GLOBE : VEIL_INSIDE);
    }
    updateThemeLabels();
    ring?.update(dt, {
      level: ringIn.v * (1 - selFade.v) * (0.35 + 0.65 * searchOff()),
      size: sizeK(),
      inside: mode !== "globe",
      paused: ringHover !== null,
      still: reducedMotion(),
    });
    if (!controls.dragging && pointerNdc) {
      let hit = pickTile(pointerNdc[0], pointerNdc[1], camera, centers, half(), facing(), aspects, scales, sheet);
      const grain = ring?.pick(pointerNdc[0], pointerNdc[1], camera) ?? null;
      let over: number | null = null;
      if (grain) {
        // a grain wins only when it is nearer than the tile under the pointer
        if (hit === null) over = grain.k;
        else {
          _rv.set(centers[hit * 3], centers[hit * 3 + 1], centers[hit * 3 + 2]).applyMatrix4(camera.matrixWorldInverse);
          if (grain.depth < -_rv.z) over = grain.k;
        }
        if (over !== null) hit = null;
      }
      setRingHover(over);
      if (hit !== hovered) {
        hovered = hit;
        material.uniforms.uHovered.value = hit ?? -1;
        // while selected the arcs belong to the selection; while a search is gathered they would tie the grid to the shell
        if (focused < 0) showNeighbors(searchHits.length ? null : hit);
        cb.onHover(hit);
      }
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
      return [home[i * 3], home[i * 3 + 1], home[i * 3 + 2]];
    },
    setThemeFilter(th) { material.uniforms.uTheme.value = th ?? -1; },
    setView(next) {
      if (next === mode) return;
      if (focused >= 0) { doBlur(); cb.onBlur(); } // mode switches mid-selection must not strand uFocused
      mode = next;
      material.uniforms.uFacing.value = mode === "globe" ? -1 : 1;
      coast.visible = coastVisible(mode, coastLoaded, terrain);
      // the grid was anchored for the other view; the camera takes a frame to move
      if (searchHits.length && focused < 0) gatherSoon(0.1);
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
    setRadius(r) { radius.target = Math.min(RADIUS_MAX, Math.max(RADIUS_MIN, r)); },
    setSearch(hits, inset = 0) {
      searchInset = inset;
      searchHits = (hits ?? []).filter((i) => i >= 0 && i < n).slice(0, MATCH_MAX);
      matchSet = new Set(searchHits);
      const match = material.uniforms.uMatch.value as Float32Array;
      match.fill(-1);
      searchHits.forEach((i, k) => { match[k] = i; });
      if (!searchHits.length) { release(); dimSearch(false); return; }
      if (focused >= 0) return; // gathers when the reader closes
      showNeighbors(null);
      gatherSoon(0);
    },
    setDock(px) { dockPx = px; if (focused >= 0) gsap.to(dock, { px, duration: DUR.morph }); },
    dispose() {
      disposed = true;
      cancelAnimationFrame(raf);
      cancelAnimationFrame(focusRaf1);
      cancelAnimationFrame(focusRaf2);
      focusCall?.kill();
      gatherCall?.kill();
      resize.disconnect();
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointerleave", onLeave);
      canvas.removeEventListener("wheel", onWheel);
      gsap.killTweensOf(focusDolly);
      gsap.killTweensOf(orbitR);
      gsap.killTweensOf([focusDolly, orbitR, dock, glowLevel, labelLevel]);
      glowTex.dispose();
      ring?.dispose();
      gsap.killTweensOf(tintLevel);
      tintGeo.dispose();
      tintMat.dispose();
      veilMat.dispose();
      for (const b of bands) { b.mat.map?.dispose(); b.mat.dispose(); }
      gsap.killTweensOf([material.uniforms.uNeighDim, material.uniforms.uNeighScale, material.uniforms.uBirth]);
      gsap.killTweensOf([arcMat.uniforms.uOpacity, arcMat.uniforms.uProgress]);
      gsap.killTweensOf(morph);
      gsap.killTweensOf([ringMat, ...ringLabels.map((l) => l.sprite.material)]);
      for (const l of ringLabels) { l.sprite.material.map?.dispose(); l.sprite.material.dispose(); }
      for (const o of rings.children) if (o instanceof LineLoop) o.geometry.dispose();
      ringMat.dispose();
      void lens;
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
