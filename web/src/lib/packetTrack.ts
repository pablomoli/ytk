import * as THREE from "three";
import type { Track, TrackPacket } from "../api/packet";
import {
  MODEL_STATIONS,
  STATIONS,
  byStation,
  heldFor,
  inkMean,
  inkWeight,
  logp,
  scaleT,
  short,
  ago,
} from "./packetModel";

/* The track (#213): one WebGL stage split in two, one instant. Rose on the
   left, seven sectors on a ring, a packet a bar whose length is the time
   held on a log scale; field on the right, seven stations on a plane and
   one surface rising over them. Green with a pulse while a model holds
   it. The values below were chosen by the owner from live prototype URLs
   (docs/design/packet-page/README.md) and are not knobs on this page. */

// FIELD.tilt was 0.75 in the record; the owner asked (2026-09-14) for the camera above the
// surface looking down, and 0.22 puts it there.
const ROSE = {
  tilt: 0.5,
  gap: 0.02,
  hub: 0.4,
  taper: 1,
  curve: 0.4,
  rings: 4,
  ticks: 84,
  spokes: 0.4,
};
const FIELD = { tilt: 0.22, spacing: 2.28, reach: 1.32, lift: 3.2, grain: 1, tail: 22 };
const MOTION = 0.7;
const GLOW = 1;
// the focus law: everyone else dims to this when a packet is hovered or selected
const DIM = 0.15;

const ACCENT = "#e2b04a";
const LIVE = "#4ade80";
const HOT = "#ff6a3d";
const INK = "#f0eee7";
const MUTE = "#83817a";
const R1 = 6.0;
const N = STATIONS.length;
const TAIL = 40;
const MAXP = 512;

export type TrackHover = {
  id: number;
  title: string;
  station: string;
  note: string;
  held: number;
  rounds: number;
  tokens: number;
  calls: number;
  x: number;
  y: number;
};

export type TrackStats = { packets: number; held: number; wait: number; ask: number; fps: number };

export type PacketTrack = {
  setData(track: Track | undefined, nowMs: () => number): void;
  setSelected(id: number | null): void;
  dispose(): void;
};

type Hit = { kind: "wedge"; a0: number; a1: number; r0: number; r1: number } | { kind: "point" };

type Slot = { x: number; y: number; z: number; len: number; first: boolean; hit?: Hit };
type Mark = {
  p: TrackPacket;
  st: number;
  since: number;
  x: number;
  y: number;
  z: number;
  hit?: Hit;
  model: boolean;
};

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const hex = (h: string) => new THREE.Color(h);
const lineMat = (c: number | string, o: number) =>
  new THREE.LineBasicMaterial({ color: c, transparent: true, opacity: o });

function circleGeo(r: number, n = 128, y = 0) {
  const p: number[] = [];
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI * 2;
    p.push(Math.cos(a) * r, y, Math.sin(a) * r);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
  return g;
}

function sectorGeo(
  g: THREE.BufferGeometry,
  eg: THREE.BufferGeometry,
  a0: number,
  a1: number,
  r0: number,
  r1: number,
  n = 10,
) {
  const p: number[] = [];
  const idx: number[] = [];
  for (let i = 0; i <= n; i++) {
    const a = a0 + ((a1 - a0) * i) / n;
    p.push(Math.cos(a) * r0, 0, Math.sin(a) * r0, Math.cos(a) * r1, 0, Math.sin(a) * r1);
  }
  for (let i = 0; i < n; i++) {
    const k = i * 2;
    idx.push(k, k + 1, k + 2, k + 1, k + 3, k + 2);
  }
  g.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
  g.setIndex(idx);
  g.computeBoundingSphere();
  const e: number[] = [];
  for (let i = 0; i <= n; i++) {
    const a = a0 + ((a1 - a0) * i) / n;
    e.push(Math.cos(a) * r0, 0, Math.sin(a) * r0);
  }
  for (let i = n; i >= 0; i--) {
    const a = a0 + ((a1 - a0) * i) / n;
    e.push(Math.cos(a) * r1, 0, Math.sin(a) * r1);
  }
  eg.setAttribute("position", new THREE.Float32BufferAttribute(e, 3));
}

// value noise, three octaves: the field's grain
function nhash(x: number, y: number) {
  const h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return h - Math.floor(h);
}
function vnoise(x: number, y: number) {
  const xi = Math.floor(x),
    yi = Math.floor(y),
    xf = x - xi,
    yf = y - yi;
  const u = xf * xf * (3 - 2 * xf),
    v = yf * yf * (3 - 2 * yf);
  const a = nhash(xi, yi),
    b = nhash(xi + 1, yi),
    c = nhash(xi, yi + 1),
    d = nhash(xi + 1, yi + 1);
  return lerp(lerp(a, b, u), lerp(c, d, u), v) * 2 - 1;
}
function fbm(x: number, y: number) {
  return (
    vnoise(x, y) * 0.55 +
    vnoise(x * 2.1 + 7.3, y * 2.1 - 3.1) * 0.3 +
    vnoise(x * 4.3 - 2.2, y * 4.3 + 9.7) * 0.15
  );
}

const GRID: [number, number][] = [
  [-1.5, -1],
  [-0.5, -1],
  [0.5, -1],
  [1.5, -1],
  [-1, 1],
  [0, 1],
  [1, 1],
];
const FLOOR_Y = -2.6;
const WR = 66,
  WC = 96;

export function mountPacketTrack(
  stage: HTMLElement,
  canvas: HTMLCanvasElement,
  labelsHost: HTMLElement,
  cb: {
    onHover: (h: TrackHover | null) => void;
    onSelect: (id: number) => void;
    onStats?: (s: TrackStats) => void;
  },
): PacketTrack {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setClearColor(0x0b0b0d, 1);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  const R0 = ROSE.hub;

  // ---- ring chrome
  const ringGroup = new THREE.Group();
  scene.add(ringGroup);
  const rings: { m: THREE.LineBasicMaterial; o: number }[] = [];
  const outer = new THREE.Line(circleGeo(R1), lineMat(0xffffff, 0.22));
  ringGroup.add(outer);
  rings.push({ m: outer.material, o: 0.22 });
  const inner = new THREE.Line(circleGeo(R0 * 0.7, 64), lineMat(0xffffff, 0.18));
  ringGroup.add(inner);
  rings.push({ m: inner.material, o: 0.18 });
  for (let i = 1; i <= ROSE.rings; i++) {
    const l = new THREE.Line(
      circleGeo(R0 + (i / (ROSE.rings + 1)) * (R1 - R0)),
      lineMat(0xffffff, 0.08),
    );
    ringGroup.add(l);
    rings.push({ m: l.material, o: 0.08 });
  }
  {
    const p: number[] = [];
    for (let i = 0; i < N; i++) {
      const a = -Math.PI / 2 + (i / N) * Math.PI * 2;
      p.push(
        Math.cos(a) * R0 * 0.7,
        0,
        Math.sin(a) * R0 * 0.7,
        Math.cos(a) * (R1 + 0.5),
        0,
        Math.sin(a) * (R1 + 0.5),
      );
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
    const spokes = new THREE.LineSegments(g, lineMat(0xffffff, ROSE.spokes));
    ringGroup.add(spokes);
    rings.push({ m: spokes.material, o: ROSE.spokes });
  }
  {
    const p: number[] = [];
    const nt = ROSE.ticks;
    for (let i = 0; i < nt; i++) {
      const a = (i / nt) * Math.PI * 2,
        long = i % Math.round(nt / 7) === 0;
      p.push(
        Math.cos(a) * (R1 + 0.6),
        0,
        Math.sin(a) * (R1 + 0.6),
        Math.cos(a) * (R1 + (long ? 1 : 0.8)),
        0,
        Math.sin(a) * (R1 + (long ? 1 : 0.8)),
      );
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
    const ticks = new THREE.LineSegments(g, lineMat(0xffffff, 0.25));
    ringGroup.add(ticks);
    rings.push({ m: ticks.material, o: 0.25 });
  }

  // ---- the field: one surface, seven hills
  const fieldPos = (st: number): [number, number, number] => [
    GRID[st]![0] * FIELD.spacing,
    FLOOR_Y,
    GRID[st]![1] * FIELD.spacing * 0.9,
  ];
  const fieldLoad = new Array<number>(N).fill(0),
    fieldLive = new Array<number>(N).fill(0);
  function fieldHeightAt(x: number, z: number): [number, number] {
    let h = 0,
      g = 0;
    for (let i = 0; i < N; i++) {
      const [px, , pz] = fieldPos(i);
      // a crowded station widens as well as rises: a massif, not a needle
      const sig = FIELD.reach * (1 + 0.45 * Math.min(1, fieldLoad[i]! / 3));
      const d2 = (x - px) * (x - px) + (z - pz) * (z - pz);
      const w = Math.exp(-d2 / (2 * sig * sig));
      h += fieldLoad[i]! * w;
      g += fieldLive[i]! * w;
    }
    return [h, g];
  }
  const fieldTop = (st: number) => {
    const [px, , pz] = fieldPos(st);
    const [h] = fieldHeightAt(px, pz);
    return FLOOR_Y + ((FIELD.lift * h) / (h + 0.9)) * 2;
  };
  const wakeGeo = new THREE.PlaneGeometry(1, 1, WC - 1, WR - 1);
  wakeGeo.setAttribute("aH", new THREE.BufferAttribute(new Float32Array(WC * WR), 1));
  wakeGeo.setAttribute("aLive", new THREE.BufferAttribute(new Float32Array(WC * WR), 1));
  // The surface is one shader: color by height on a ramp, a grid that stays one
  // pixel wide at any zoom, contour lines at fixed heights, fog with distance.
  const wakeMat = new THREE.ShaderMaterial({
    side: THREE.DoubleSide,
    uniforms: {
      uGround: { value: hex("#1a1612") },
      uBrass: { value: hex(ACCENT) },
      uPeak: { value: hex("#fff1c8") },
      uLive: { value: hex(LIVE) },
      uBg: { value: hex("#0b0b0d") },
      uGrid: { value: new THREE.Vector2(WC - 1, WR - 1) },
      uContours: { value: 9 },
      uFogNear: { value: 16 },
      uFogFar: { value: 42 },
    },
    vertexShader: `attribute float aH;attribute float aLive;varying vec2 vUv;varying float vH;varying float vLive;varying float vDepth;
void main(){vUv=uv;vH=aH;vLive=aLive;vec4 mv=modelViewMatrix*vec4(position,1.);vDepth=-mv.z;gl_Position=projectionMatrix*mv;}`,
    fragmentShader: `uniform vec3 uGround;uniform vec3 uBrass;uniform vec3 uPeak;uniform vec3 uLive;uniform vec3 uBg;uniform vec2 uGrid;uniform float uContours;uniform float uFogNear;uniform float uFogFar;
varying vec2 vUv;varying float vH;varying float vLive;varying float vDepth;
void main(){
  vec3 col=mix(uGround,uBrass,smoothstep(.12,.7,vH));col=mix(col,uPeak,smoothstep(.72,1.,vH));col=mix(col,uLive,clamp(vLive,0.,1.)*.85);
  vec2 gq=vUv*uGrid;vec2 gd=abs(fract(gq-.5)-.5)/fwidth(gq);float line=1.-min(min(gd.x,gd.y),1.);
  float cq=vH*uContours;float cd=abs(fract(cq-.5)-.5)/fwidth(cq);float contour=(1.-min(cd,1.))*smoothstep(.02,.06,vH);
  vec3 lit=col*(.18+.42*vH)+mix(col,vec3(.8,.75,.65),.35)*line*.4+vec3(1.,.95,.85)*contour*(.2+.4*vH);
  float fog=smoothstep(uFogNear,uFogFar,vDepth);
  gl_FragColor=vec4(mix(lit,uBg,fog*.7),1.);}`,
  });
  const wake = new THREE.Mesh(wakeGeo, wakeMat);
  scene.add(wake);
  // the sonar: a ring that swells from a station's foot while a model holds a packet there
  const sonar: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>[] = [];
  for (let i = 0; i < N; i++) {
    const m = new THREE.Mesh(
      new THREE.RingGeometry(0.92, 1, 64),
      new THREE.MeshBasicMaterial({
        color: LIVE,
        transparent: true,
        opacity: 0,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
      }),
    );
    m.rotation.x = -Math.PI / 2;
    m.visible = false;
    scene.add(m);
    sonar.push(m);
  }
  let noiseT = 0;
  let wakeKey = "";
  function updateWake(marks: Mark[], dt: number) {
    noiseT += dt * MOTION * 0.8;
    const key =
      marks.map((m) => `${m.p.id}:${m.st}:${Math.round(m.since)}`).join(",") +
      ":" +
      noiseT.toFixed(2);
    if (key === wakeKey) return;
    wakeKey = key;
    fieldLoad.fill(0);
    fieldLive.fill(0);
    for (const m of marks) {
      fieldLoad[m.st]! += logp(m.since);
      if (m.model) fieldLive[m.st]! += 1;
    }
    const pa = wakeGeo.attributes.position!.array as Float32Array,
      ha = wakeGeo.attributes.aH!.array as Float32Array,
      la = wakeGeo.attributes.aLive!.array as Float32Array;
    const X = 2.1 * FIELD.spacing,
      Z = 1.7 * FIELD.spacing,
      grain = FIELD.grain;
    for (let j = 0; j < WR; j++)
      for (let i = 0; i < WC; i++) {
        const x = -X + (2 * X * i) / (WC - 1),
          z = -Z + (2 * Z * j) / (WR - 1);
        // domain warp and a slow swell: hills stay where the data puts them, the ground between them moves
        const wx = grain * 0.9 * fbm(x * 0.35 + noiseT, z * 0.35 - noiseT * 0.7);
        const wz = grain * 0.9 * fbm(x * 0.35 - 13 + noiseT * 0.6, z * 0.35 + 5 + noiseT);
        const [h, g] = fieldHeightAt(x + wx, z + wz);
        const swell =
          grain * 0.5 * fbm(x * 0.5 + noiseT * 0.8, z * 0.5 + noiseT * 0.5) * (1 + h) +
          grain * 0.12 * Math.sin(x * 1.4 + noiseT * 2.2) * Math.cos(z * 1.1 - noiseT * 1.7);
        const k = j * WC + i;
        pa[k * 3] = x;
        pa[k * 3 + 1] = FLOOR_Y + ((FIELD.lift * h) / (h + 0.9)) * 2 + swell;
        pa[k * 3 + 2] = z;
        ha[k] = h / (h + 0.9);
        la[k] = Math.min(1, g / 0.35);
      }
    wakeGeo.attributes.position!.needsUpdate = true;
    wakeGeo.attributes.aH!.needsUpdate = true;
    wakeGeo.attributes.aLive!.needsUpdate = true;
    wakeGeo.computeBoundingSphere();
  }

  // ---- station reticles
  const reticles: {
    g: THREE.Group;
    c: THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial>;
    t: THREE.LineSegments<THREE.BufferGeometry, THREE.LineBasicMaterial>;
  }[] = [];
  for (let i = 0; i < N; i++) {
    const g = new THREE.Group();
    const c = new THREE.Line(circleGeo(0.28, 32), lineMat(0xffffff, 0.8));
    g.add(c);
    const p = [
      -0.5, 0, 0, -0.36, 0, 0, 0.36, 0, 0, 0.5, 0, 0, 0, 0, -0.5, 0, 0, -0.36, 0, 0, 0.36, 0, 0,
      0.5,
    ];
    const tg = new THREE.BufferGeometry();
    tg.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
    const t = new THREE.LineSegments(tg, lineMat(0xffffff, 0.8));
    g.add(t);
    scene.add(g);
    reticles.push({ g, c, t });
  }

  // ---- field points, a soft sprite each
  const pGeo = new THREE.BufferGeometry();
  const pPos = new Float32Array(MAXP * 3),
    pCol = new Float32Array(MAXP * 3),
    pSize = new Float32Array(MAXP),
    pLive = new Float32Array(MAXP);
  pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
  pGeo.setAttribute("color", new THREE.BufferAttribute(pCol, 3));
  pGeo.setAttribute("size", new THREE.BufferAttribute(pSize, 1));
  pGeo.setAttribute("live", new THREE.BufferAttribute(pLive, 1));
  pGeo.setDrawRange(0, 0);
  const pMat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: { uTime: { value: 0 }, uGlow: { value: GLOW }, uPx: { value: 1 } },
    vertexShader: `attribute float size;attribute float live;varying vec3 vC;varying float vL;uniform float uTime;uniform float uGlow;uniform float uPx;void main(){vC=color;vL=live;vec4 mv=modelViewMatrix*vec4(position,1.);float pulse=1.+live*.25*sin(uTime*5.);gl_PointSize=size*(1.+uGlow*2.)*pulse*uPx*(30./-mv.z);gl_Position=projectionMatrix*mv;}`,
    fragmentShader: `varying vec3 vC;varying float vL;uniform float uGlow;void main(){vec2 d=gl_PointCoord-.5;float r=length(d)*2.;if(r>1.)discard;float core=smoothstep(.30,.14,r);float halo=pow(1.-r,3.)*(.25+uGlow*.45);gl_FragColor=vec4(vC*(core*1.2+halo),core+halo*.9);}`,
    vertexColors: true,
  });
  const points = new THREE.Points(pGeo, pMat);
  scene.add(points);
  // a fading tail per point: where the packet came from
  const trails = new Map<
    number,
    { l: THREE.Line; g: THREE.BufferGeometry; pts: [number, number, number][] }
  >();
  function trailFor(id: number) {
    let t = trails.get(id);
    if (!t) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(TAIL * 3), 3));
      g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(TAIL * 3), 3));
      const l = new THREE.Line(
        g,
        new THREE.LineBasicMaterial({
          vertexColors: true,
          transparent: true,
          opacity: 0.9,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      );
      scene.add(l);
      t = { l, g, pts: [] };
      trails.set(id, t);
    }
    return t;
  }

  // ---- rose bars: additive fill plus a crisp edge, one pair per packet
  type Bar = {
    g: THREE.BufferGeometry;
    fill: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
    halo: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
    edge: THREE.LineLoop<THREE.BufferGeometry, THREE.LineBasicMaterial>;
  };
  const bars = new Map<number, Bar>();
  function barFor(id: number): Bar {
    let b = bars.get(id);
    if (!b) {
      const g = new THREE.BufferGeometry();
      const fill = new THREE.Mesh(
        g,
        new THREE.MeshBasicMaterial({
          color: 0xffffff,
          transparent: true,
          opacity: 0.5,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          side: THREE.DoubleSide,
        }),
      );
      const halo = new THREE.Mesh(
        g,
        new THREE.MeshBasicMaterial({
          color: 0xffffff,
          transparent: true,
          opacity: 0.16,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          side: THREE.DoubleSide,
        }),
      );
      const edge = new THREE.LineLoop(new THREE.BufferGeometry(), lineMat(0xffffff, 0.9));
      scene.add(fill, halo, edge);
      b = { g, fill, halo, edge };
      bars.set(id, b);
    }
    return b;
  }

  // ---- selected reticle
  const selRet = new THREE.Group();
  {
    selRet.add(new THREE.Line(circleGeo(0.42, 48), lineMat(INK, 0.9)));
    const p: number[] = [];
    for (const [sx, sz] of [
      [-1, -1],
      [1, -1],
      [1, 1],
      [-1, 1],
    ] as const)
      p.push(
        sx * 0.7,
        0,
        sz * 0.45,
        sx * 0.7,
        0,
        sz * 0.7,
        sx * 0.7,
        0,
        sz * 0.7,
        sx * 0.45,
        0,
        sz * 0.7,
      );
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
    selRet.add(new THREE.LineSegments(g, lineMat(INK, 0.9)));
  }
  selRet.visible = false;
  scene.add(selRet);

  // ---- state
  let track: Track | undefined;
  let nowMs: () => number = () => Date.now();
  let selected: number | null = null;
  let hover: number | null = null;
  let rot = 0,
    W = 0,
    H = 0,
    VX = 0,
    VW = 0;
  let rail = false;
  const slots = { rose: new Map<number, Slot>(), rail: new Map<number, Slot>() };
  const marksBy: { rose: Mark[]; rail: Mark[] } = { rose: [], rail: [] };
  const labelEls = new Map<string, HTMLDivElement>();
  const v3 = new THREE.Vector3();

  const LBL =
    "absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap font-data text-[12.5px] tracking-[.04em] lowercase text-ink2 tabular-nums pointer-events-none [text-shadow:0_0_6px_#000,0_0_2px_#000]";
  const LBL_PK =
    "absolute translate-x-[10px] -translate-y-1/2 whitespace-nowrap font-data text-[11.5px] tracking-[.04em] lowercase text-mute tabular-nums pointer-events-none [text-shadow:0_0_6px_#000,0_0_2px_#000]";
  function label(key: string, pk = false) {
    let e = labelEls.get(key);
    if (!e) {
      e = document.createElement("div");
      e.className = pk ? LBL_PK : LBL;
      labelsHost.appendChild(e);
      labelEls.set(key, e);
    }
    e.dataset.used = "1";
    return e;
  }
  function project(x: number, y: number, z: number): [number, number, boolean] {
    v3.set(x, y, z).project(camera);
    return [(v3.x * 0.5 + 0.5) * VW + VX, (-v3.y * 0.5 + 0.5) * H, v3.z < 1];
  }
  // The field camera is the owner's: drag orbits, the wheel zooms, and the
  // slow turn resumes a few seconds after the hand lets go. The rose keeps
  // its own slow turn; its wedges are hit-tested against it.
  const orbit = { az: 0, el: 0, dist: 15, idleAt: 0, dragging: false, lx: 0, ly: 0, moved: 0 };
  function placeCamera() {
    let el = rail ? lerp(1.2, 0.22, FIELD.tilt) : lerp(1.45, 0.28, ROSE.tilt);
    let az = rail ? Math.PI / 2 + rot * 0.4 : rot * 0.35 + Math.PI * 0.15;
    let dist = rail ? 15 : 23;
    if (rail) {
      el = Math.min(1.45, Math.max(0.08, el + orbit.el));
      az += orbit.az;
      dist = orbit.dist;
    }
    camera.position.set(
      Math.cos(az) * Math.cos(el) * dist,
      Math.sin(el) * dist,
      Math.sin(az) * Math.cos(el) * dist,
    );
    camera.lookAt(0, rail ? -2.2 : 0, 0);
    camera.updateMatrixWorld(true);
  }
  function setHalf(h: 0 | 1) {
    rail = h === 1;
    VX = h === 0 ? 0 : Math.floor(W / 2) + 1;
    VW = Math.floor(W / 2) - 1;
    camera.aspect = VW / Math.max(1, H);
    camera.updateProjectionMatrix();
    placeCamera();
  }
  function size() {
    const r = stage.getBoundingClientRect();
    const w = Math.round(r.width),
      h = Math.round(r.height);
    if (w !== W || h !== H) {
      W = w;
      H = h;
      const px = Math.min(2, devicePixelRatio || 1);
      renderer.setPixelRatio(px);
      renderer.setSize(w, h, false);
      pMat.uniforms.uPx!.value = px;
    }
  }
  function stationPos(st: number): [number, number, number, number] {
    if (rail) {
      const [x, y, z] = fieldPos(st);
      return [x, y, z, 0];
    }
    const a = -Math.PI / 2 + ((st + 0.5) / N) * Math.PI * 2 + rot;
    return [Math.cos(a) * (R1 + 1.3), 0, Math.sin(a) * (R1 + 1.3), a];
  }

  function draw(
    dt: number,
    half: 0 | 1,
  ): { held: number; wait: number; ask: number; marks: Mark[] } {
    size();
    setHalf(half);
    const t = nowMs();
    const A = hex(ACCENT);
    if (half === 0) {
      rot += dt * MOTION * 0.06;
      // while the field is held or freshly released, its own turn pauses, then eases back
      const sinceIdle = orbit.dragging ? 0 : (performance.now() - orbit.idleAt) / 1000;
      const resume = orbit.idleAt ? Math.min(1, Math.max(0, (sinceIdle - 3) / 4)) : 1;
      if (resume < 1) orbit.az -= dt * MOTION * 0.06 * 0.4 * (1 - resume);
      pMat.uniforms.uTime!.value += dt;
    }
    ringGroup.visible = !rail;
    ringGroup.rotation.y = -rot;
    for (const r of rings) r.m.opacity = r.o;
    const packets = track?.packets ?? [];
    const bySt = byStation(packets, t);
    const mean = inkMean(packets);
    const pos = rail ? slots.rail : slots.rose;
    const focusId = hover ?? selected;
    const e = 1 - Math.pow(0.002, dt);
    const sec = (Math.PI * 2) / N;
    let held = 0,
      wait = 0,
      ask = 0,
      n = 0;
    const marks: Mark[] = [];
    const seen = new Set<number>();
    // the field's hills need every mark before any point is placed
    const pre: Mark[] = [];
    bySt.forEach((arr, st) =>
      arr.forEach((p) =>
        pre.push({
          p,
          st,
          since: heldFor(p.station, t),
          x: 0,
          y: 0,
          z: 0,
          model: MODEL_STATIONS.has(st),
        }),
      ),
    );
    wake.visible = rail;
    if (rail) updateWake(pre, dt);
    for (let i = 0; i < N; i++) {
      const r = sonar[i]!;
      const on = rail && fieldLive[i]! > 0;
      r.visible = on;
      if (!on) continue;
      const phase = (((performance.now() / 2400 + i * 0.37) % 1) + 1) % 1;
      const [fx, , fz] = fieldPos(i);
      r.position.set(fx, fieldTop(i) + 0.45, fz);
      const sc = 0.3 + 2.4 * phase;
      r.scale.set(sc, sc, 1);
      r.material.opacity = 0.95 * (1 - phase) * (1 - phase);
    }
    bySt.forEach((arr, st) =>
      arr.forEach((p, rank) => {
        const isModel = MODEL_STATIONS.has(st);
        if (isModel) held++;
        else if (st === 6) ask++;
        else wait++;
        seen.add(p.id);
        const since = heldFor(p.station, t);
        const hot = hex(ACCENT).lerp(hex(HOT), Math.min(1, p.rounds / 5));
        const c = isModel ? hex(LIVE) : hot;
        const wgt = inkWeight(p.tokens, mean);
        const dim = focusId != null && p.id !== focusId ? DIM : 1;
        const count = arr.length;
        const a0 = -Math.PI / 2 + st * sec + rot;
        const len = rail ? logp(since) : scaleT(since, ROSE.curve);
        let s = pos.get(p.id);
        if (!s) {
          s = { x: 0, y: 0, z: 0, len: 0, first: false };
          pos.set(p.id, s);
        }
        s.len += (len - s.len) * e;
        let anchor: [number, number, number];
        if (rail) {
          const [fx, , fz] = fieldPos(st);
          const ra = (rank / Math.max(1, count)) * Math.PI * 2,
            rr = count > 1 ? 0.34 : 0;
          const tx = fx + Math.cos(ra) * rr,
            tz = fz + Math.sin(ra) * rr,
            ty = fieldTop(st) + 0.22;
          if (!s.first) {
            s.x = tx;
            s.y = ty;
            s.z = tz;
            s.first = true;
          }
          s.x += (tx - s.x) * e;
          s.y += (ty - s.y) * e;
          s.z += (tz - s.z) * e;
          s.hit = { kind: "point" };
          pPos.set([s.x, s.y, s.z], n * 3);
          pCol.set([c.r * dim, c.g * dim, c.b * dim], n * 3);
          pSize[n] = (p.id === selected ? 10 : 7) * Math.sqrt(wgt);
          pLive[n] = isModel ? 1 : 0;
          n++;
          const tr = trailFor(p.id);
          tr.pts.push([s.x, s.y, s.z]);
          while (tr.pts.length > FIELD.tail) tr.pts.shift();
          const pa = tr.g.attributes.position!.array as Float32Array,
            ca = tr.g.attributes.color!.array as Float32Array;
          for (let i = 0; i < TAIL; i++) {
            const q = tr.pts[Math.max(0, i - (TAIL - tr.pts.length))] ?? tr.pts[0]!;
            pa[i * 3] = q[0];
            pa[i * 3 + 1] = q[1];
            pa[i * 3 + 2] = q[2];
            const f =
              Math.pow(Math.max(0, i - (TAIL - FIELD.tail)) / Math.max(1, FIELD.tail - 1), 2.2) *
              0.55 *
              MOTION *
              dim;
            ca[i * 3] = c.r * f;
            ca[i * 3 + 1] = c.g * f;
            ca[i * 3 + 2] = c.b * f;
          }
          tr.g.attributes.position!.needsUpdate = true;
          tr.g.attributes.color!.needsUpdate = true;
          tr.l.visible = true;
          anchor = [s.x, s.y, s.z];
        } else {
          const b = barFor(p.id);
          b.fill.visible = b.halo.visible = b.edge.visible = true;
          b.fill.material.color.copy(c);
          b.halo.material.color.copy(c);
          b.edge.material.color.copy(p.id === selected ? hex(INK) : c);
          const pulse = isModel ? 1 + 0.06 * Math.sin(performance.now() / 180) : 1;
          const gap = sec * ROSE.gap;
          const ws = arr.map((j) => inkWeight(j.tokens, mean));
          const tot = ws.reduce((x, y) => x + y, 0);
          let off = 0;
          for (let q = 0; q < rank; q++) off += ws[q]!;
          const w = (sec - 2 * gap) / tot;
          let ba0 = a0 + gap + off * w + w * ws[rank]! * 0.08;
          let ba1 = a0 + gap + (off + ws[rank]!) * w - w * ws[rank]! * 0.08;
          const r0 = R0,
            r1 = R0 + s.len * (R1 - R0) * pulse;
          const mid = (ba0 + ba1) / 2,
            hw = ((ba1 - ba0) / 2) * lerp(0.35, 1, ROSE.taper);
          ba0 = mid - hw;
          ba1 = mid + hw;
          sectorGeo(b.g, b.edge.geometry, ba0, ba1, r0, Math.max(r0 + 0.06, r1));
          b.fill.material.opacity = 0.5 * dim;
          b.halo.material.opacity = 0.16 * dim;
          b.edge.material.opacity = (p.id === selected ? 1 : 0.5) * dim;
          anchor = [Math.cos(mid) * r1, 0, Math.sin(mid) * r1];
          s.x = anchor[0];
          s.y = 0;
          s.z = anchor[2];
          s.hit = { kind: "wedge", a0: ba0, a1: ba1, r0, r1 };
        }
        const mark: Mark = {
          p,
          st,
          since,
          x: anchor[0],
          y: anchor[1],
          z: anchor[2],
          model: isModel,
        };
        if (s.hit) mark.hit = s.hit;
        marks.push(mark);
      }),
    );
    for (const [id, b] of bars)
      if (!seen.has(id) || rail) b.fill.visible = b.halo.visible = b.edge.visible = false;
    for (const [id, tr] of trails)
      if (!seen.has(id) || !rail) {
        tr.l.visible = false;
        tr.pts.length = 0;
      }
    pGeo.setDrawRange(0, n);
    for (const k of ["position", "color", "size", "live"] as const)
      pGeo.attributes[k]!.needsUpdate = true;
    points.visible = rail;
    if (half === 0) for (const el of labelEls.values()) el.dataset.used = "";
    const side = rail ? "field" : "rose";
    for (let i = 0; i < N; i++) {
      const [x, y, z, ang] = stationPos(i);
      const r = reticles[i]!;
      const ly = rail ? fieldTop(i) + 0.6 : y;
      r.g.rotation.y = rail ? 0 : -ang;
      const cnt = bySt[i]!.length;
      const model = MODEL_STATIONS.has(i) && cnt > 0;
      const col = model ? hex(LIVE) : cnt ? A : hex(MUTE);
      r.c.material.color.copy(col);
      r.t.material.color.copy(col);
      r.c.material.opacity = r.t.material.opacity = cnt ? 0.95 : 0.5;
      r.g.visible = false;
      const [sx, sy, ok] = project(x, ly, z);
      const el = label(`${side}:st${i}`);
      el.style.left = `${sx}px`;
      el.style.top = `${sy - (rail ? 4 : 6)}px`;
      el.style.color = model ? LIVE : cnt ? INK : MUTE;
      el.textContent = STATIONS[i] + (cnt ? `  ${cnt}` : "");
      el.style.display = ok ? "block" : "none";
    }
    for (const m of marks) {
      if (!(selected === m.p.id || hover === m.p.id)) continue;
      const [sx, sy, ok] = project(m.x, m.y, m.z);
      const el = label(`${side}:pk${m.p.id}`, true);
      el.style.left = `${sx}px`;
      el.style.top = `${sy}px`;
      el.replaceChildren();
      const b = document.createElement("b");
      b.className = "font-normal text-ink";
      b.textContent = short(m.p.title, 26);
      el.append(b, ` · ${ago(m.since)}`);
      el.style.display = ok ? "block" : "none";
    }
    if (half === 1)
      for (const el of labelEls.values()) if (!el.dataset.used) el.style.display = "none";
    const sm = marks.find((m) => m.p.id === selected);
    if (sm) {
      selRet.visible = true;
      selRet.position.set(sm.x, sm.y, sm.z);
    } else selRet.visible = false;
    renderer.setViewport(VX, 0, VW, H);
    renderer.setScissor(VX, 0, VW, H);
    renderer.setScissorTest(true);
    renderer.render(scene, camera);
    return { held, wait, ask, marks };
  }

  // ---- hit test: wedges as whole sectors by a ray onto the floor, points by screen distance
  const rayc = new THREE.Raycaster(),
    floor = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0),
    fpt = new THREE.Vector3();
  function hit(ev: MouseEvent): Mark | null {
    const r = stage.getBoundingClientRect();
    const x = ev.clientX - r.left,
      y = ev.clientY - r.top;
    const half: 0 | 1 = x < W / 2 ? 0 : 1;
    setHalf(half);
    rayc.setFromCamera(new THREE.Vector2(((x - VX) / VW) * 2 - 1, -(y / H) * 2 + 1), camera);
    const onFloor = rayc.ray.intersectPlane(floor, fpt);
    let best: Mark | null = null,
      bd = 16;
    for (const m of half === 0 ? marksBy.rose : marksBy.rail) {
      if (m.hit?.kind === "wedge" && onFloor) {
        const ang = Math.atan2(fpt.z, fpt.x),
          rad = Math.hypot(fpt.x, fpt.z);
        let a = ang - m.hit.a0;
        a = ((a % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
        const w = (((m.hit.a1 - m.hit.a0) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
        if (a <= w && rad >= m.hit.r0 - 0.1 && rad <= m.hit.r1 + 0.1) return m;
      } else {
        const [sx, sy] = project(m.x, m.y, m.z);
        const d = Math.hypot(sx - x, sy - y);
        if (d < bd) {
          bd = d;
          best = m;
        }
      }
    }
    return best;
  }
  const onField = (ev: MouseEvent) => ev.clientX - stage.getBoundingClientRect().left >= W / 2;
  const onDown = (ev: MouseEvent) => {
    if (!onField(ev) || ev.button !== 0) return;
    orbit.dragging = true;
    orbit.moved = 0;
    orbit.lx = ev.clientX;
    orbit.ly = ev.clientY;
  };
  const onUp = () => {
    if (!orbit.dragging) return;
    orbit.dragging = false;
    orbit.idleAt = performance.now();
  };
  const onWheel = (ev: WheelEvent) => {
    if (!onField(ev)) return;
    ev.preventDefault();
    const step = ev.deltaMode === 1 ? ev.deltaY * 16 : ev.deltaY;
    orbit.dist = Math.min(40, Math.max(8, orbit.dist * Math.exp(step * 0.0012)));
    orbit.idleAt = performance.now();
  };
  const onMove = (ev: MouseEvent) => {
    if (orbit.dragging) {
      const dx = ev.clientX - orbit.lx,
        dy = ev.clientY - orbit.ly;
      orbit.lx = ev.clientX;
      orbit.ly = ev.clientY;
      orbit.moved += Math.abs(dx) + Math.abs(dy);
      orbit.az -= dx * 0.006;
      orbit.el += dy * 0.005;
      orbit.idleAt = performance.now();
      stage.style.cursor = "grabbing";
      cb.onHover(null);
      return;
    }
    const m = hit(ev);
    hover = m ? m.p.id : null;
    stage.style.cursor = m ? "pointer" : "default";
    if (!m) {
      cb.onHover(null);
      return;
    }
    const r = stage.getBoundingClientRect();
    cb.onHover({
      id: m.p.id,
      title: m.p.title,
      station: STATIONS[m.st]!,
      note: m.p.station.note,
      held: m.since,
      rounds: m.p.rounds,
      tokens: m.p.tokens,
      calls: m.p.calls,
      x: ev.clientX - r.left,
      y: ev.clientY - r.top,
    });
  };
  const onLeave = () => {
    hover = null;
    cb.onHover(null);
  };
  const onClick = (ev: MouseEvent) => {
    // a drag is not a click
    if (orbit.moved > 4) return;
    const m = hit(ev);
    if (m) cb.onSelect(m.p.id);
  };
  stage.addEventListener("mousemove", onMove);
  stage.addEventListener("mouseleave", onLeave);
  stage.addEventListener("mousedown", onDown);
  window.addEventListener("mouseup", onUp);
  stage.addEventListener("wheel", onWheel, { passive: false });
  stage.addEventListener("click", onClick);

  // ---- loop
  let raf = 0,
    last = performance.now(),
    fpsAcc = 0,
    fpsN = 0,
    fps = 0;
  const frame = (now: number) => {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const r = draw(dt, 0);
    marksBy.rose = r.marks;
    marksBy.rail = draw(dt, 1).marks;
    fpsAcc += dt;
    fpsN++;
    if (fpsAcc > 0.5) {
      fps = Math.round(fpsN / fpsAcc);
      fpsAcc = 0;
      fpsN = 0;
      cb.onStats?.({ packets: r.marks.length, held: r.held, wait: r.wait, ask: r.ask, fps });
    }
    raf = requestAnimationFrame(frame);
  };
  raf = requestAnimationFrame(frame);

  return {
    setData(next, clock) {
      track = next;
      nowMs = clock;
    },
    setSelected(id) {
      selected = id;
    },
    dispose() {
      cancelAnimationFrame(raf);
      stage.removeEventListener("mousemove", onMove);
      stage.removeEventListener("mouseleave", onLeave);
      stage.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
      stage.removeEventListener("wheel", onWheel);
      stage.removeEventListener("click", onClick);
      for (const el of labelEls.values()) el.remove();
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose?.();
        const mat = m.material as THREE.Material | undefined;
        mat?.dispose?.();
      });
      renderer.dispose();
    },
  };
}
