import {
  DynamicDrawUsage,
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
  Vector3,
} from "three";

/* The pending ring: every item still in the queue is one grain around the
   sphere. At rest a flat ring, newest at the inner edge, a gap at each month.
   The dial turns it through four shapes in a loop: the ring parts into three
   orbits, the orbits wind into one thread from pole to pole, newest at the
   top, the thread comes loose as dust, and the dust settles into the ring.
   Grains are placed here every frame and the pointer reads the same array.
   One grain can be read: it holds lit, and the scene may carry it off the
   ring, hide it or show it again. Nothing here reaches the queue: the page asks the hub. */

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
export const GRAIN = 0.02;
export const NO_COVER = 0.55; // size of a grain without a cover, against one with
const HOVER = 2.4;
export const SELECT = 3.2; // a grain being read, in grain sizes
const OMEGA = (Math.PI * 2) / 480; // inner edge: one turn in eight minutes
const THICK_INSIDE = 0.07, THICK_GLOBE = 0.034;
// seen from outside most grains hug the ring plane and a few stray off it, so the lanes and the month gaps survive
const LOFT = 2.6;
const FAR_INSIDE = 0.5; // behind the tiles the belt is backdrop, not content
// exploded, the ring parts into this many bands of radius, each swung about its own line through the center.
// Three, a third of a turn apart: from above, three ellipses crossed at 60 degrees.
export const SHELLS = 3;
const TILT = 1.15; // ~66 degrees: steep enough that the orbits cross over the globe
const SPIN = 5; // exploded, grains run their orbits this many times faster on top of the ring's drift
// swung out, a band draws in to a ribbon near one radius: a wide band tilted reads as haze, not an orbit
const ORBIT_IN = 1.3;
export const ORBIT_OUT = 1.5;
const SQUEEZE = 0.35; // share of a band's width its ribbon keeps
// contracted, each grain drifts out to a spot of its own in a shell this deep around the sphere
const DUST_IN = 1.2, DUST_OUT = 2.6;
const DUST_NEAR = 1.6; // above 1 the shell is denser toward the sphere
const DUST_SLIP = 1.2; // radians a grain may slide along the ring on its way out, so the cloud forgets the lanes
// past the orbits the queue winds into one thread around the sphere, pole to pole
const COIL_R = 1.4;
const COIL_LAT = 1.2; // the thread's first and last latitude, radians: the poles stay open
const COIL_TURNS = 7;
const COIL_WIDE = 0.05; // the thread's width, radians of latitude
const COIL_GAP = 14; // a month boundary breaks the thread for this many items' worth of length
const COIL_RATE = 2; // the thread turns about its axis this many times faster than the ring's inner edge

const hash = (x: number) => { const v = Math.sin(x * 12.9898) * 43758.5453; return v - Math.floor(v); };
const ramp = (a: number, b: number, x: number) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

// the dial's position, in turns from the ring, as a shape: 0 ring, 1 orbits, 2 thread, 3 dust, 4 the ring again.
// Each shape holds for a stretch around its stop, so a stop is a place to rest and not a single tick.
export const ringPhase = (c: number) => {
  const q = (c - Math.floor(c)) * 4, i = Math.min(3, Math.floor(q));
  return i + ramp(0.1, 0.9, q - i);
};
// how far the grains have left the ring's plane to circle the sphere: all the way as orbits and thread, not at all as ring and dust
export const ringOpen = (q: number) => (q < 1 ? q : q < 2 ? 1 : q < 3 ? 3 - q : 0);

// pure so it's unit-testable: r, theta, shell, month band per item, in input order (newest first).
// Equal area per item, so a busy month is a wide band. Grains snap to concentric
// lanes: evenly scattered they read as sunflower spirals, in lanes as a ring.
// A shell is a run of whole lanes, so no lane is split between two orbits.
export function ringLayout(days: string[]): Float32Array {
  const n = days.length;
  const slot = new Float32Array(n);
  const month = new Int32Array(n);
  let gaps = 0, band = 0, prev = "";
  for (let k = 0; k < n; k++) {
    const key = days[k].slice(0, 7);
    if (k > 0 && key !== prev && band >= MIN_BAND) { gaps++; band = 0; }
    prev = key;
    band++;
    slot[k] = k + gaps * GAP;
    month[k] = gaps;
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
  const lanes = Math.max(1, count.length);
  const out = new Float32Array(n * 4);
  for (let k = 0; k < n; k++) {
    const l = lane[k];
    const j = (seen[l] = (seen[l] ?? -1) + 1);
    // a little disorder inside the lane, never enough to cross into the next
    out[k * 4] = RING_IN + (l + 0.5 + (hash(k + 0.5) - 0.5) * 0.45) * pitch;
    out[k * 4 + 1] = l * GOLDEN + ((j + (hash(k + 7.3) - 0.5) * 0.5) / count[l]) * Math.PI * 2;
    out[k * 4 + 2] = Math.min(SHELLS - 1, Math.floor((l / lanes) * SHELLS));
    out[k * 4 + 3] = month[k];
  }
  return out;
}

const VERT = /* glsl */ `
precision highp float;
in vec3 position;
in vec2 uv;
in vec3 iPos;   // where the grain is this frame
in float iSlot; // atlas slot, -1 = no cover
in float iIdx;
in float iFlag; // 1 = open question
uniform mat4 modelViewMatrix, projectionMatrix;
uniform float uGrain, uSize, uNoCover, uHover, uHoverScale, uSel, uSelScale, uClear;
uniform float uCols, uCell;
out vec2 vUv;
out float vHas, vHov, vSel, vFlag, vNear, vSeed;
void main() {
  float has = step(0.0, iSlot);
  float hov = abs(iIdx - uHover) < 0.5 ? 1.0 : 0.0;
  float sel = abs(iIdx - uSel) < 0.5 ? 1.0 : 0.0;
  vec4 cv = modelViewMatrix * vec4(iPos, 1.0);
  float dist = length(cv.xyz);
  // a grain about to pass through the camera shrinks away instead of filling the view
  float s = uGrain * uSize * mix(uNoCover, 1.0, has) * mix(mix(1.0, uHoverScale, hov), uSelScale, sel) * smoothstep(0.06, 0.3, dist);
  // loose dust never sits on the sphere's face: a grain between the eye and the sphere shrinks away
  vec3 c = modelViewMatrix[3].xyz;
  float t = dot(c, cv.xyz) / dot(cv.xyz, cv.xyz);
  s *= 1.0 - (1.0 - sel) * uClear * step(1.0, t) * (1.0 - smoothstep(1.0, 1.15, dot(c, c) - t * t * dot(cv.xyz, cv.xyz)));
  gl_Position = projectionMatrix * (cv + vec4(position.xy * s, 0.0, 0.0));
  float k = max(iSlot, 0.0);
  // inset: at the small mip levels a cell's edge carries its neighbor's color
  vec2 cell = vec2(mod(k, uCols), floor(k / uCols));
  vec2 q = 0.05 + uv * 0.9;
  vUv = vec2((cell.x + q.x) * uCell, 1.0 - (cell.y + 1.0 - q.y) * uCell);
  vHas = has;
  vHov = max(hov, sel);
  vSel = sel;
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
in float vHas, vHov, vSel, vFlag, vNear, vSeed;
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
  // a coverless grain being read is a pale mote, not a dark one
  c = mix(mix(speck, vec3(0.80, 0.78, 0.72), vSel), c, vHas);
  vec3 brass = vec3(0.886, 0.690, 0.290) * (0.3 + 0.7 * dot(c, vec3(0.333)) * 1.6);
  c = mix(c, brass, 0.45 * vFlag * (1.0 - near));
  outColor = vec4(c * mix(uFar, 1.0, vHov), uLevel);
}`;

export type RingHandle = {
  group: Group;
  // level: 0..1 opacity. size: the tiles' size factor, so grains shrink with them. paused: hold the motion.
  // phase: the shape, as ringPhase gives it: 0 ring, 1 orbits, 2 thread, 3 dust, 4 the ring again.
  update(dt: number, opts: { level: number; size: number; inside: boolean; paused: boolean; still: boolean; phase: number }): void;
  // grain under the pointer and its view depth, nearest first; null when none
  pick(ndcX: number, ndcY: number, camera: PerspectiveCamera): { k: number; depth: number } | null;
  setHover(k: number | null): void;
  // the grain being read: lit, held at scale times a grain's size. null lets it go.
  select(k: number | null, scale?: number): void;
  // a grain taken off the ring to a place in the world; null hands it back
  carry(k: number, to: Vector3 | null): void;
  hide(k: number): void;
  show(k: number): void;
  worldOf(k: number, out: Vector3): Vector3;
  dispose(): void;
};

export function createRing(data: RingData, atlasUrl: string, anisotropy: number): RingHandle {
  const n = data.items.length;
  const layout = ringLayout(data.items.map((it) => it.d));
  const r0 = new Float32Array(n), theta = new Float32Array(n);
  const rate = new Float32Array(n); // each grain's share of the inner edge's angular speed
  const height = new Float32Array(n), lift = new Float32Array(n); // place in the belt, -1..1, and the same once lofted
  const slot = new Float32Array(n), flag = new Float32Array(n);
  const axis = new Float32Array(n * 2); // the line the grain's shell swings about, as a direction in the ring plane
  const orbitR = new Float32Array(n);
  const dust = new Float32Array(n * 3); // radius, latitude, slip along the ring
  const coil = new Float32Array(n * 3); // distance from the axis, height, longitude
  // each shell's own middle radius, so its ribbon keeps the band's order across its width
  const lo = new Array<number>(SHELLS).fill(Infinity), hi = new Array<number>(SHELLS).fill(-Infinity);
  for (let k = 0; k < n; k++) {
    const sh = layout[k * 4 + 2];
    lo[sh] = Math.min(lo[sh], layout[k * 4]);
    hi[sh] = Math.max(hi[sh], layout[k * 4]);
  }
  const months = n ? layout[(n - 1) * 4 + 3] : 0;
  data.items.forEach((it, k) => {
    const r = (r0[k] = layout[k * 4]);
    theta[k] = layout[k * 4 + 1];
    rate[k] = Math.pow(RING_IN / r, 1.5);
    // height from a hash, so the belt's thickness needs no stored field
    height[k] = Math.max(-1, Math.min(1, (Math.sin(k * 12.9898) * 43758.5453) % 1));
    slot[k] = it.k;
    flag[k] = it.q ? 1 : 0;
    // the lines sit evenly around the ring, so the orbits' poles ring the globe's own
    const sh = layout[k * 4 + 2];
    axis[k * 2] = Math.cos((sh / SHELLS) * Math.PI * 2);
    axis[k * 2 + 1] = Math.sin((sh / SHELLS) * Math.PI * 2);
    orbitR[k] = ORBIT_IN + ((sh + 0.5) / SHELLS) * (ORBIT_OUT - ORBIT_IN) + (r - (lo[sh] + hi[sh]) / 2) * SQUEEZE;
    // evenly over all directions; the slip is small because the ring's own angles already cover the circle
    dust[k * 3] = DUST_IN + (DUST_OUT - DUST_IN) * Math.pow(hash(k + 11.1), DUST_NEAR);
    dust[k * 3 + 1] = Math.asin(2 * hash(k + 23.7) - 1);
    dust[k * 3 + 2] = (hash(k + 37.9) - 0.5) * DUST_SLIP;
    // along the thread by age. Latitude goes as the arcsine so grains are as dense on a short polar turn as on the equator's
    const t = (k + layout[k * 4 + 3] * COIL_GAP + 0.5) / (n + months * COIL_GAP);
    const lat = Math.asin(Math.sin(COIL_LAT) * (1 - 2 * t));
    const across = lat + (hash(k + 51.3) - 0.5) * COIL_WIDE;
    const cr = COIL_R + (hash(k + 63.1) - 0.5) * 0.02;
    coil.set([cr * Math.cos(across), cr * Math.sin(across), (COIL_TURNS * Math.PI * (COIL_LAT - lat)) / COIL_LAT], k * 3);
  });
  const pos = new Float32Array(n * 3);
  const where = new InstancedBufferAttribute(pos, 3);
  where.setUsage(DynamicDrawUsage);
  const plane = new PlaneGeometry(1, 1);
  const geo = new InstancedBufferGeometry();
  geo.index = plane.index;
  geo.setAttribute("position", plane.getAttribute("position"));
  geo.setAttribute("uv", plane.getAttribute("uv"));
  geo.setAttribute("iPos", where);
  geo.setAttribute("iSlot", new InstancedBufferAttribute(slot, 1));
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
      uGrain: { value: GRAIN }, uSize: { value: 1 }, uNoCover: { value: NO_COVER },
      uHover: { value: -1 }, uHoverScale: { value: HOVER },
      uSel: { value: -1 }, uSelScale: { value: SELECT },
      uCols: { value: data.cols }, uCell: { value: data.cell / data.size },
      uLevel: { value: 0 }, uFar: { value: 1 }, uClear: { value: 0 },
    },
  });
  const mesh = new Mesh(geo, material);
  mesh.frustumCulled = false; // instances are placed per frame; the base quad's bound says nothing
  mesh.renderOrder = -0.5; // before the selection glow
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

  let hover = -1, sel = -1;
  let time = 0;
  const held = new Map<number, Vector3>(); // carried grains, in the ring's own frame
  const off = new Uint8Array(n); // 1 hidden, 2 carried: neither answers the pointer
  const AWAY = 1e5; // past the far plane
  // from inside the camera sits in the ring plane, so the ring spreads into a belt; from outside most grains hug the plane
  let thick = THICK_INSIDE, loft = 1, lofted = NaN;
  const u = material.uniforms;
  const _mvp = new Matrix4();
  const _eye = new Vector3();
  // q: the shape. Each quarter blends two neighbors: ring to orbits, orbits to thread, thread to dust, dust to ring.
  const place = (q: number) => {
    const loose = q >= 2; // past the thread a grain starts from its place in the dust
    const wa = Math.min(1, q), wd = q < 3 ? 1 : 4 - q;
    const wc = q < 1 ? 0 : q < 2 ? q - 1 : q < 3 ? 3 - q : 0;
    if (loft !== lofted) {
      for (let k = 0; k < n; k++) lift[k] = Math.sign(height[k]) * Math.pow(Math.abs(height[k]), loft);
      lofted = loft;
    }
    const ct = Math.cos(TILT * wa), st = Math.sin(TILT * wa);
    const turn = time * OMEGA * COIL_RATE;
    for (let k = 0; k < n; k++) {
      // inner grains lap outer ones, as in a real ring
      const a = theta[k] + time * OMEGA * rate[k];
      const hy = lift[k] * thick;
      let x: number, y: number, z: number;
      if (loose) {
        // out along its own meridian: distance and latitude blend, so no grain cuts through the sphere on the way
        const rho = Math.hypot(r0[k], hy) * (1 - wd) + dust[k * 3] * wd;
        const lat = Math.atan2(hy, r0[k]) * (1 - wd) + dust[k * 3 + 1] * wd;
        const lon = a + dust[k * 3 + 2] * wd;
        x = rho * Math.cos(lat) * Math.cos(lon);
        y = rho * Math.sin(lat);
        z = rho * Math.cos(lat) * Math.sin(lon);
      } else {
        // the shell draws in to its ribbon and swings about its line through the center
        const r = r0[k] + (orbitR[k] - r0[k]) * wa;
        const fx = r * Math.cos(a), fz = r * Math.sin(a);
        const kx = axis[k * 2], kz = axis[k * 2 + 1], along = (kx * fx + kz * fz) * (1 - ct);
        x = fx * ct - kz * hy * st + kx * along;
        y = hy * ct + (kz * fx - kx * fz) * st;
        z = fz * ct + kx * hy * st + kz * along;
      }
      if (wc > 0) {
        const lon = coil[k * 3 + 2] + turn;
        const tx = coil[k * 3] * Math.cos(lon), ty = coil[k * 3 + 1], tz = coil[k * 3] * Math.sin(lon);
        const mx = x + (tx - x) * wc, my = y + (ty - y) * wc, mz = z + (tz - z) * wc;
        // a straight line between two points around the sphere dips toward it; hold the distance and blend only the bearing
        const keep = (Math.hypot(x, y, z) * (1 - wc) + Math.hypot(tx, ty, tz) * wc) / Math.max(1e-4, Math.hypot(mx, my, mz));
        x = mx * keep;
        y = my * keep;
        z = mz * keep;
      }
      pos[k * 3] = x;
      pos[k * 3 + 1] = y;
      pos[k * 3 + 2] = z;
    }
    for (let k = 0; k < n; k++) if (off[k] === 1) pos[k * 3 + 1] = AWAY;
    for (const [k, v] of held) pos.set([v.x, v.y, v.z], k * 3);
    where.needsUpdate = true;
  };
  return {
    group,
    update(dt, { level, size, inside, paused, still, phase }) {
      const q = Math.min(4, Math.max(0, phase));
      if (!paused && !still) time += dt * (1 + SPIN * ringOpen(q));
      u.uSize.value = size;
      u.uLevel.value = level;
      u.uClear.value = q < 2 ? 0 : q < 3 ? q - 2 : 4 - q;
      const ease = still ? 1 : 1 - Math.exp(-dt * 5);
      thick += ((inside ? THICK_INSIDE : THICK_GLOBE) - thick) * ease;
      loft += ((inside ? 1 : LOFT) - loft) * ease;
      u.uFar.value += ((inside ? FAR_INSIDE : 1) - u.uFar.value) * ease;
      place(q);
    },
    pick(ndcX, ndcY, camera) {
      if (!mesh.visible || (u.uLevel.value as number) < 0.5) return null;
      group.updateMatrixWorld();
      _mvp.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).multiply(group.matrixWorld);
      const e = _mvp.elements;
      const px = camera.projectionMatrix.elements[0], py = camera.projectionMatrix.elements[5];
      const side = GRAIN * (u.uSize.value as number);
      const clear = (u.uClear.value as number) > 0.5;
      const eye = group.worldToLocal(_eye.copy(camera.position)), far2 = eye.lengthSq();
      let best = -1, bestW = Infinity;
      for (let k = 0; k < n; k++) {
        const x = pos[k * 3], y = pos[k * 3 + 1], z = pos[k * 3 + 2];
        const w = e[3] * x + e[7] * y + e[11] * z + e[15];
        if (off[k] || w < 0.3 || w >= bestW) continue; // nearer than this the shader has shrunk the grain away
        if (clear) {
          // the shader's test: dust over the sphere's face is not drawn, so it cannot be hovered
          const dx = x - eye.x, dy = y - eye.y, dz = z - eye.z, d2 = dx * dx + dy * dy + dz * dz;
          const t = -(eye.x * dx + eye.y * dy + eye.z * dz) / d2;
          if (t >= 1 && far2 - t * t * d2 < 1) continue;
        }
        // small grains get a hit area a little larger than they are drawn
        const h = (side * (slot[k] >= 0 ? 1 : NO_COVER) * (k === sel ? (u.uSelScale.value as number) : k === hover ? HOVER : 1.5)) / 2;
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
    select(k, scale = SELECT) {
      sel = k ?? -1;
      u.uSel.value = sel;
      u.uSelScale.value = scale;
    },
    carry(k, to) {
      if (!to) { held.delete(k); if (off[k] === 2) off[k] = 0; return; }
      group.updateMatrixWorld();
      const v = held.get(k) ?? new Vector3();
      held.set(k, group.worldToLocal(v.copy(to)));
      if (off[k] !== 1) off[k] = 2;
    },
    hide(k) {
      held.delete(k);
      off[k] = 1;
    },
    show(k) {
      held.delete(k);
      off[k] = 0;
    },
    worldOf(k, out) {
      group.updateMatrixWorld();
      return out.set(pos[k * 3], pos[k * 3 + 1], pos[k * 3 + 2]).applyMatrix4(group.matrixWorld);
    },
    dispose() {
      disposed = true;
      tex?.dispose();
      plane.dispose();
      geo.dispose();
      material.dispose();
    },
  };
}
