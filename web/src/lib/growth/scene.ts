import {
  ClampToEdgeWrapping,
  DataTexture,
  FloatType,
  HalfFloatType,
  LinearFilter,
  Mesh,
  OrthographicCamera,
  PlaneGeometry,
  RGBAFormat,
  Scene,
  ShaderMaterial,
  Vector2,
  WebGLRenderer,
  WebGLRenderTarget,
} from "three";
import { growthRenderFragment, growthUpdateFragment, growthVertex } from "./shaders";

export type GrowthKind = "related" | "novel";
export type GrowthStatus = {
  count: number;
  phase: "resting" | "growing" | "paused";
  message: string;
  progress: number;
};

export type GrowthHandle = {
  add: (kind: GrowthKind) => void;
  reset: () => void;
  setPaused: (paused: boolean) => void;
  destroy: () => void;
};

type Node = { x: number; y: number; radius: number; parent: number };
type GrowthEvent = {
  kind: GrowthKind;
  from: Vector2;
  to: Vector2;
  radius: number;
  seed: number;
  label: string;
};

const SIZE = 384;
const INITIAL_NODES: Node[] = [
  { x: 0.48, y: 0.51, radius: 0.15, parent: -1 },
  { x: 0.34, y: 0.57, radius: 0.105, parent: 0 },
  { x: 0.24, y: 0.68, radius: 0.082, parent: 1 },
  { x: 0.17, y: 0.58, radius: 0.065, parent: 1 },
  { x: 0.39, y: 0.72, radius: 0.095, parent: 0 },
  { x: 0.53, y: 0.7, radius: 0.12, parent: 0 },
  { x: 0.66, y: 0.61, radius: 0.11, parent: 0 },
  { x: 0.76, y: 0.72, radius: 0.083, parent: 6 },
  { x: 0.71, y: 0.43, radius: 0.13, parent: 0 },
  { x: 0.83, y: 0.35, radius: 0.075, parent: 8 },
  { x: 0.55, y: 0.3, radius: 0.1, parent: 0 },
  { x: 0.36, y: 0.32, radius: 0.09, parent: 0 },
  { x: 0.25, y: 0.25, radius: 0.062, parent: 11 },
];

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
const fract = (value: number) => value - Math.floor(value);
const randomFrom = (seed: number) => fract(Math.sin(seed * 91.733) * 43758.5453123);

function segmentDistance(px: number, py: number, ax: number, ay: number, bx: number, by: number) {
  const abx = bx - ax;
  const aby = by - ay;
  const apx = px - ax;
  const apy = py - ay;
  const h = clamp((apx * abx + apy * aby) / Math.max(0.00001, abx * abx + aby * aby), 0, 1);
  return Math.hypot(apx - abx * h, apy - aby * h);
}

function makeSeedTexture(nodes: Node[]) {
  const data = new Float32Array(SIZE * SIZE * 4);
  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      const px = (x + 0.5) / SIZE;
      const py = (y + 0.5) / SIZE;
      let body = 0;
      let vessel = 0;
      for (let index = 0; index < nodes.length; index++) {
        const node = nodes[index];
        const dx = (px - node.x) / (node.radius * (0.86 + randomFrom(index + 2) * 0.32));
        const dy = (py - node.y) / (node.radius * (0.72 + randomFrom(index + 9) * 0.44));
        const ripple = Math.sin((px * 31 + py * 19 + index) * 2.1) * 0.035;
        body = Math.max(body, clamp(1.08 - Math.hypot(dx, dy) + ripple, 0, 1));
        if (node.parent >= 0) {
          const parent = nodes[node.parent];
          const distance = segmentDistance(px, py, parent.x, parent.y, node.x, node.y);
          const bridge = clamp(1 - distance / (node.radius * 0.38), 0, 1);
          const vein = clamp(1 - distance / Math.max(0.006, node.radius * 0.09), 0, 1);
          body = Math.max(body, bridge * 0.76);
          vessel = Math.max(vessel, vein);
        }
      }
      const centerDistance = Math.hypot(px - nodes[0].x, py - nodes[0].y);
      vessel = Math.max(vessel, clamp(1 - centerDistance / 0.085, 0, 1));
      const offset = (y * SIZE + x) * 4;
      data[offset] = body;
      data[offset + 1] = vessel;
      data[offset + 2] = 0;
      data[offset + 3] = 1;
    }
  }
  const texture = new DataTexture(data, SIZE, SIZE, RGBAFormat, FloatType);
  texture.needsUpdate = true;
  texture.minFilter = LinearFilter;
  texture.magFilter = LinearFilter;
  texture.wrapS = ClampToEdgeWrapping;
  texture.wrapT = ClampToEdgeWrapping;
  return texture;
}

export function mountGrowth(
  canvas: HTMLCanvasElement,
  onStatus: (status: GrowthStatus) => void,
): GrowthHandle {
  const renderer = new WebGLRenderer({
    canvas,
    antialias: false,
    alpha: false,
    powerPreference: "high-performance",
  });
  renderer.setClearColor(0x020304, 1);
  const camera = new OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const geometry = new PlaneGeometry(2, 2);
  const simulationScene = new Scene();
  const displayScene = new Scene();
  const seedTexture = makeSeedTexture(INITIAL_NODES);
  const targetOptions = {
    type: HalfFloatType,
    format: RGBAFormat,
    minFilter: LinearFilter,
    magFilter: LinearFilter,
    depthBuffer: false,
    stencilBuffer: false,
  };
  const targets = [
    new WebGLRenderTarget(SIZE, SIZE, targetOptions),
    new WebGLRenderTarget(SIZE, SIZE, targetOptions),
  ];
  targets.forEach((target) => {
    target.texture.wrapS = ClampToEdgeWrapping;
    target.texture.wrapT = ClampToEdgeWrapping;
  });

  const updateUniforms = {
    uState: { value: seedTexture },
    uTexel: { value: new Vector2(1 / SIZE, 1 / SIZE) },
    uFrom: { value: new Vector2(0.5, 0.5) },
    uTo: { value: new Vector2(0.5, 0.5) },
    uRadius: { value: 0.08 },
    uProgress: { value: 0 },
    uSeed: { value: 1 },
    uActive: { value: 0 },
    uCopy: { value: 1 },
  };
  const updateMaterial = new ShaderMaterial({
    vertexShader: growthVertex,
    fragmentShader: growthUpdateFragment,
    uniforms: updateUniforms,
  });
  simulationScene.add(new Mesh(geometry, updateMaterial));

  const displayUniforms = {
    uState: { value: targets[0].texture },
    uTexel: { value: new Vector2(1 / SIZE, 1 / SIZE) },
    uTime: { value: 0 },
    uAspect: { value: 1 },
    uPulse: { value: 0 },
  };
  const displayMaterial = new ShaderMaterial({
    vertexShader: growthVertex,
    fragmentShader: growthRenderFragment,
    uniforms: displayUniforms,
  });
  displayScene.add(new Mesh(geometry, displayMaterial));

  let readIndex = 0;
  let nodes = INITIAL_NODES.map((node) => ({ ...node }));
  let eventCount = 0;
  let current: GrowthEvent | null = null;
  let eventElapsed = 0;
  let paused = false;
  let destroyed = false;
  let frame = 0;
  let lastTime = performance.now();
  const queue: GrowthEvent[] = [];

  const simulate = (source: DataTexture | null = null) => {
    const writeIndex = 1 - readIndex;
    updateUniforms.uState.value = source ?? targets[readIndex].texture;
    renderer.setRenderTarget(targets[writeIndex]);
    renderer.render(simulationScene, camera);
    renderer.setRenderTarget(null);
    readIndex = writeIndex;
    displayUniforms.uState.value = targets[readIndex].texture;
  };

  const resetState = () => {
    nodes = INITIAL_NODES.map((node) => ({ ...node }));
    eventCount = 0;
    current = null;
    queue.length = 0;
    eventElapsed = 0;
    readIndex = 1;
    updateUniforms.uCopy.value = 1;
    simulate(seedTexture);
    updateUniforms.uCopy.value = 0;
    onStatus({
      count: eventCount,
      phase: paused ? "paused" : "resting",
      message: "mature baseline · waiting for an event",
      progress: 0,
    });
  };

  const eventFor = (kind: GrowthKind): GrowthEvent => {
    const seed = 800 + eventCount * 37 + (kind === "novel" ? 17 : 0);
    let parentIndex: number;
    let angle: number;
    let distance: number;
    if (kind === "related") {
      parentIndex = 1 + Math.floor(randomFrom(seed) * (nodes.length - 1));
      angle = randomFrom(seed + 3) * Math.PI * 2;
      distance = 0.08 + randomFrom(seed + 5) * 0.07;
    } else {
      parentIndex = nodes.reduce((best, node, index) => {
        const radius = Math.hypot(node.x - 0.48, node.y - 0.51);
        const bestRadius = Math.hypot(nodes[best].x - 0.48, nodes[best].y - 0.51);
        return radius > bestRadius ? index : best;
      }, 0);
      const parent = nodes[parentIndex];
      angle = Math.atan2(parent.y - 0.51, parent.x - 0.48) + (randomFrom(seed + 7) - 0.5) * 0.65;
      distance = 0.14 + randomFrom(seed + 11) * 0.08;
    }
    const parent = nodes[parentIndex];
    const to = new Vector2(
      clamp(parent.x + Math.cos(angle) * distance, 0.08, 0.92),
      clamp(parent.y + Math.sin(angle) * distance, 0.08, 0.92),
    );
    return {
      kind,
      from: new Vector2(parent.x, parent.y),
      to,
      radius:
        kind === "novel"
          ? 0.08 + randomFrom(seed + 13) * 0.025
          : 0.052 + randomFrom(seed + 13) * 0.02,
      seed,
      label:
        kind === "novel"
          ? "novel material · budding a new lobe"
          : "related material · reinforcing a living region",
    };
  };

  const startNext = () => {
    if (current || !queue.length || paused) return;
    current = queue.shift()!;
    eventElapsed = 0;
    updateUniforms.uFrom.value.copy(current.from);
    updateUniforms.uTo.value.copy(current.to);
    updateUniforms.uRadius.value = current.radius;
    updateUniforms.uSeed.value = current.seed;
    updateUniforms.uActive.value = 1;
    onStatus({ count: eventCount, phase: "growing", message: current.label, progress: 0 });
  };

  const resize = () => {
    const width = canvas.clientWidth || innerWidth;
    const height = canvas.clientHeight || innerHeight;
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.setSize(width, height, false);
    displayUniforms.uAspect.value = width / Math.max(1, height);
  };

  const render = (now: number) => {
    if (destroyed) return;
    const dt = Math.min(0.05, Math.max(0.001, (now - lastTime) / 1000));
    lastTime = now;
    displayUniforms.uTime.value += dt;
    if (!paused) {
      startNext();
      if (current) {
        eventElapsed += dt;
        const progress = Math.min(1, eventElapsed / 2.6);
        updateUniforms.uProgress.value = progress;
        displayUniforms.uPulse.value = Math.sin(progress * Math.PI);
        simulate();
        onStatus({ count: eventCount, phase: "growing", message: current.label, progress });
        if (progress >= 1) {
          nodes.push({ x: current.to.x, y: current.to.y, radius: current.radius, parent: 0 });
          eventCount++;
          const completed = current;
          current = null;
          updateUniforms.uActive.value = 0;
          displayUniforms.uPulse.value = 0;
          onStatus({
            count: eventCount,
            phase: "resting",
            message: `${completed.kind} event settled into permanent state`,
            progress: 1,
          });
        }
      }
    }
    renderer.setRenderTarget(null);
    renderer.render(displayScene, camera);
    frame = requestAnimationFrame(render);
  };

  resize();
  addEventListener("resize", resize);
  resetState();
  frame = requestAnimationFrame(render);

  return {
    add(kind) {
      queue.push(eventFor(kind));
      startNext();
    },
    reset: resetState,
    setPaused(next) {
      paused = next;
      onStatus({
        count: eventCount,
        phase: next ? "paused" : current ? "growing" : "resting",
        message: next ? "simulation paused" : (current?.label ?? "organism resumed"),
        progress: current ? Math.min(1, eventElapsed / 2.6) : 0,
      });
      if (!next) startNext();
    },
    destroy() {
      destroyed = true;
      cancelAnimationFrame(frame);
      removeEventListener("resize", resize);
      seedTexture.dispose();
      targets.forEach((target) => target.dispose());
      updateMaterial.dispose();
      displayMaterial.dispose();
      geometry.dispose();
      renderer.dispose();
    },
  };
}
