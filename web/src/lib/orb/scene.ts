import {
  DoubleSide,
  GLSL3,
  InstancedBufferAttribute,
  InstancedBufferGeometry,
  Mesh,
  PerspectiveCamera,
  PlaneGeometry,
  RawShaderMaterial,
  Scene,
  Vector3,
  WebGLRenderer,
} from "three";
import { DUR, gsap, reducedMotion } from "../motion";
import type { LayoutName, OrbData } from "../../api/orb";
import { buildAtlas, uvRect } from "./atlas";
import { createControls } from "./controls";
import { pickTile, tileScreenRect } from "./pick";

export const TILE_HALF = 0.055; // ~4.5deg cell radius at 505 tiles
// From Task 9a's previz verdict: DOLLY = 1 - 0.055/(APEX * tan 30deg).
// 0.76 is the Apex40 default; replace with the user's chosen apex.
const DOLLY = 0.76;
const DIM_FOCUS = 0.25;
const DIM_FILTER = 0.15;

const VERT = /* glsl */ `
precision highp float;
in vec3 position;
in vec2 uv;
in vec3 iPos;   // tile center on the unit sphere
in vec3 iUv;    // atlas u, v, span
in float iIdx;
uniform mat4 modelViewMatrix, projectionMatrix;
uniform float uHovered, uHoverScale;
out vec2 vUv;
out float vIdx;
void main() {
  vec3 n = normalize(-iPos); // tiles face the origin
  vec3 ref = abs(n.y) > 0.9 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0);
  vec3 e1 = normalize(cross(ref, n));
  vec3 e2 = cross(n, e1);
  float s = (abs(iIdx - uHovered) < 0.5) ? uHoverScale : 1.0;
  vec3 world = iPos + (e1 * position.x + e2 * position.y) * s;
  vUv = vec2(iUv.x + uv.x * iUv.z, iUv.y + uv.y * iUv.z);
  vIdx = iIdx;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(world, 1.0);
}`;

const FRAG = /* glsl */ `
precision highp float;
uniform sampler2D uAtlas;
uniform float uFocused, uDim;      // focus dimming: everyone but uFocused
uniform float uTheme, uThemeDim;   // theme filter dim factor
in vec2 vUv;
in float vIdx;
uniform float uThemes[1024];       // per-instance theme id, uploaded once
out vec4 outColor;
void main() {
  vec3 c = texture(uAtlas, vUv).rgb;
  float dim = 1.0;
  if (uFocused >= 0.0 && abs(vIdx - uFocused) >= 0.5) dim *= uDim;
  if (uTheme >= 0.0 && abs(uThemes[int(vIdx)] - uTheme) >= 0.5) dim *= uThemeDim;
  outColor = vec4(c * dim, 1.0);
}`;

export type OrbHandle = {
  setLayout(name: LayoutName): void;
  setThemeFilter(th: number | null): void;
  focus(i: number): void;
  blur(): void;
  dispose(): void;
};

export function mountOrb(
  canvas: HTMLCanvasElement,
  data: OrbData,
  cb: { onHover(i: number | null): void; onOpen(i: number, rect: DOMRect): void },
): OrbHandle {
  const n = data.points.length;
  const renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const camera = new PerspectiveCamera(60, canvas.clientWidth / Math.max(1, canvas.clientHeight), 0.01, 10);
  const scene = new Scene();
  const atlas = buildAtlas(data.points, data.themes.length, () => {});

  const centers = new Float32Array(n * 3);
  const writeLayout = (name: LayoutName) => {
    const arr = data.sphere[name] ?? data.sphere[data.sphere.chosen];
    if (!arr) return;
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
  const uvs = new Float32Array(n * 3);
  data.points.forEach((_, i) => {
    const r = uvRect(i);
    uvs.set([r.u, r.v, r.s], i * 3);
  });
  geo.setAttribute("iUv", new InstancedBufferAttribute(uvs, 3));
  geo.setAttribute("iIdx", new InstancedBufferAttribute(Float32Array.from({ length: n }, (_, i) => i), 1));
  geo.instanceCount = n;

  const themeArr = new Float32Array(1024).fill(-1);
  data.points.forEach((p, i) => { themeArr[i] = p.th; });
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
      uThemes: { value: themeArr },
    },
  });
  scene.add(new Mesh(geo, material));

  const controls = createControls();
  const zoom = { dolly: 0 }; // 0 at rest, 1 at apex
  let focused = -1;
  let hovered: number | null = null;
  let pointerNdc: [number, number] | null = null;
  const dir = new Vector3();

  const onDown = (e: PointerEvent) => { canvas.setPointerCapture(e.pointerId); controls.down(e.clientX, e.clientY); };
  const onMove = (e: PointerEvent) => {
    const r = canvas.getBoundingClientRect();
    pointerNdc = [((e.clientX - r.left) / r.width) * 2 - 1, -(((e.clientY - r.top) / r.height) * 2 - 1)];
    controls.move(e.clientX, e.clientY);
  };
  const onUp = (e: PointerEvent) => {
    const { tap } = controls.up();
    if (tap && hovered !== null && focused < 0) focusTile(hovered);
    canvas.releasePointerCapture(e.pointerId);
  };
  const onWheel = (e: WheelEvent) => controls.wheel(e.deltaY);
  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerup", onUp);
  canvas.addEventListener("wheel", onWheel, { passive: true });

  const apexRect = (i: number) => {
    dir.set(centers[i * 3], centers[i * 3 + 1], centers[i * 3 + 2]);
    return tileScreenRect(camera, dir.clone(), TILE_HALF, canvas.clientWidth, canvas.clientHeight);
  };

  function focusTile(i: number) {
    focused = i;
    material.uniforms.uFocused.value = i;
    const x = centers[i * 3], y = centers[i * 3 + 1], z = centers[i * 3 + 2];
    const yaw = Math.atan2(x, -z); // camera looks down -Z at yaw 0
    const pitch = Math.asin(y);
    if (reducedMotion()) {
      controls.setTarget(yaw, pitch);
      zoom.dolly = 1;
      material.uniforms.uDim.value = DIM_FOCUS;
      // one frame so the camera pose lands before projecting
      requestAnimationFrame(() => requestAnimationFrame(() => cb.onOpen(i, apexRect(i))));
      return;
    }
    controls.setTarget(yaw, pitch);
    gsap.to(zoom, { dolly: 1, duration: DUR.reveal, onComplete: () => cb.onOpen(i, apexRect(i)) });
    gsap.to(material.uniforms.uDim, { value: DIM_FOCUS, duration: DUR.reveal });
  }

  let raf = 0;
  let last = performance.now();
  const loop = (now: number) => {
    raf = requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const { yaw, pitch } = controls.step(dt);
    // orbit-from-origin: camera rotates in place, dollies toward the focused tile
    camera.position.set(0, 0, 0);
    if (focused >= 0 && zoom.dolly > 0) {
      dir.set(centers[focused * 3], centers[focused * 3 + 1], centers[focused * 3 + 2]);
      camera.position.addScaledVector(dir, zoom.dolly * DOLLY);
    }
    camera.rotation.set(0, 0, 0);
    camera.rotateY(-yaw);
    camera.rotateX(pitch);
    camera.updateMatrixWorld();
    if (!controls.dragging && focused < 0 && pointerNdc) {
      const hit = pickTile(pointerNdc[0], pointerNdc[1], camera, centers, TILE_HALF);
      if (hit !== hovered) { hovered = hit; material.uniforms.uHovered.value = hit ?? -1; cb.onHover(hit); }
    }
    renderer.render(scene, camera);
  };
  raf = requestAnimationFrame(loop);

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
    },
    setThemeFilter(th) { material.uniforms.uTheme.value = th ?? -1; },
    focus: focusTile,
    blur() {
      const done = () => { focused = -1; material.uniforms.uFocused.value = -1; };
      if (reducedMotion()) { zoom.dolly = 0; material.uniforms.uDim.value = 1; done(); return; }
      gsap.to(zoom, { dolly: 0, duration: DUR.morph, onComplete: done });
      gsap.to(material.uniforms.uDim, { value: 1, duration: DUR.morph });
    },
    dispose() {
      cancelAnimationFrame(raf);
      resize.disconnect();
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("wheel", onWheel);
      gsap.killTweensOf(zoom);
      gsap.killTweensOf(material.uniforms.uDim);
      plane.dispose();
      geo.dispose();
      material.dispose();
      atlas.dispose();
      renderer.dispose();
    },
  };
}
