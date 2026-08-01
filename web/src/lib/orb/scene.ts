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
import { buildAtlas, COLS, uvRect } from "./atlas";
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
const GLOBE_R_CLOSE = 1.45; // wheel zoom=0: globe orbit radius
const GLOBE_R_FAR = 4.0; // wheel zoom=1: globe orbit radius
const restGlobeR = (z: number) => GLOBE_R_CLOSE + z * (GLOBE_R_FAR - GLOBE_R_CLOSE);
const FOV_ZOOMED = 50; // wheel zoom=0: inside-mode fov (narrow)
const FOV_WIDE = 70; // wheel zoom=1: inside-mode fov (wide); default zoom 0.5 -> 60

const VERT = /* glsl */ `
precision highp float;
in vec3 position;
in vec2 uv;
in vec3 iPos;   // tile center on the unit sphere
in vec3 iUv;    // atlas u, v, span
in float iIdx;
in float iTheme; // per-instance theme id
uniform mat4 modelViewMatrix, projectionMatrix;
uniform float uHovered, uHoverScale;
uniform float uFacing; // 1 inside (tiles face the origin), -1 globe (tiles face outward)
out vec2 vUv;
out float vIdx;
out float vTheme;
void main() {
  vec3 n = normalize(-iPos) * uFacing;
  vec3 ref = abs(n.y) > 0.9 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0);
  vec3 e1 = normalize(cross(ref, n));
  vec3 e2 = cross(n, e1);
  float s = (abs(iIdx - uHovered) < 0.5) ? uHoverScale : 1.0;
  vec3 world = iPos + (e1 * position.x + e2 * position.y) * s;
  vUv = vec2(iUv.x + uv.x * iUv.z, iUv.y + uv.y * iUv.z);
  vIdx = iIdx;
  vTheme = iTheme; // constant across the quad; interpolation is a no-op
  gl_Position = projectionMatrix * modelViewMatrix * vec4(world, 1.0);
}`;

const FRAG = /* glsl */ `
precision highp float;
uniform sampler2D uAtlas;
uniform float uFocused, uDim;      // focus dimming: everyone but uFocused
uniform float uTheme, uThemeDim;   // theme filter dim factor
in vec2 vUv;
in float vIdx;
in float vTheme;
out vec4 outColor;
void main() {
  vec3 c = texture(uAtlas, vUv).rgb;
  float dim = 1.0;
  if (uFocused >= 0.0 && abs(vIdx - uFocused) >= 0.5) dim *= uDim;
  if (uTheme >= 0.0 && abs(vTheme - uTheme) >= 0.5) dim *= uThemeDim;
  outColor = vec4(c * dim, 1.0);
}`;

export type OrbViewMode = "inside" | "globe";

export type OrbHandle = {
  setLayout(name: LayoutName): void;
  setThemeFilter(th: number | null): void;
  setView(mode: OrbViewMode): void;
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
  const atlas = buildAtlas(points, data.themes.length, () => {});

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
  const uvs = new Float32Array(n * 3);
  points.forEach((_, i) => {
    const r = uvRect(i);
    uvs.set([r.u, r.v, r.s], i * 3);
  });
  geo.setAttribute("iUv", new InstancedBufferAttribute(uvs, 3));
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
    },
  });
  scene.add(new Mesh(geo, material));

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

  // yaw/pitch that place the camera on tile i's radial line, per the current
  // mode's orbit mapping (inside: forward = D; globe: camera position = R*D).
  const anglesFor = (i: number): { yaw: number; pitch: number } => {
    const x = centers[i * 3], y = centers[i * 3 + 1], z = centers[i * 3 + 2];
    // globe branch negated to match the flipped orbit-position signs below
    // (user-felt trackball semantics, set empirically 2026-08-01)
    return mode === "globe"
      ? { yaw: -Math.atan2(x, z), pitch: -Math.asin(-y) }
      : { yaw: Math.atan2(x, -z), pitch: Math.asin(y) };
  };

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
      const hit = pickTile(pointerNdc[0], pointerNdc[1], camera, centers, TILE_HALF, facing());
      if (hit !== null) focusTile(hit);
    }
    canvas.releasePointerCapture(e.pointerId);
  };
  const onWheel = (e: WheelEvent) => controls.wheel(e.deltaY);
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
    console.log(`[orb-debug] focus i=${i} reducedMotion=${reducedMotion()} mode=${mode}`);
    focused = i;
    material.uniforms.uFocused.value = i;
    // the NoteViewer is about to cover the tile; a caption left over from
    // hover must not stay live behind it
    hovered = null;
    material.uniforms.uHovered.value = -1;
    cb.onHover(null);
    const { yaw, pitch } = anglesFor(i);
    if (reducedMotion()) {
      console.log("[orb-debug] focus path=reduced");
      controls.setTarget(yaw, pitch);
      if (mode === "globe") orbitR.r = GLOBE_APEX; else focusDolly.dolly = 1;
      material.uniforms.uDim.value = DIM_FOCUS;
      // one frame so the camera pose lands before projecting; handles tracked
      // so dispose() can cancel them if focus() fires just before unmount
      focusRaf1 = requestAnimationFrame(() => {
        focusRaf2 = requestAnimationFrame(() => {
          const rect = apexRect(i);
          console.log(`[orb-debug] onOpen rect=${JSON.stringify({ x: rect.x, y: rect.y, width: rect.width, height: rect.height })}`);
          cb.onOpen(i, rect);
        });
      });
      return;
    }
    console.log("[orb-debug] focus path=animated");
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
      console.log(`[orb-debug] onOpen rect=${JSON.stringify({ x: rect.x, y: rect.y, width: rect.width, height: rect.height })}`);
      cb.onOpen(i, rect);
    });
  }

  let raf = 0;
  let last = performance.now();
  const loop = (now: number) => {
    raf = requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
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
      // wheel zoom drives fov directly; independent of the focus dolly below
      const fov = FOV_ZOOMED + zoom * (FOV_WIDE - FOV_ZOOMED);
      if (fov !== camera.fov) { camera.fov = fov; camera.updateProjectionMatrix(); }
      // orbit-from-origin: camera rotates in place, dollies toward the focused tile
      camera.position.set(0, 0, 0);
      if (focused >= 0 && focusDolly.dolly > 0) {
        dir.set(centers[focused * 3], centers[focused * 3 + 1], centers[focused * 3 + 2]);
        camera.position.addScaledVector(dir, focusDolly.dolly * DOLLY);
      }
      camera.rotation.set(0, 0, 0);
      camera.rotateY(-yaw);
      camera.rotateX(pitch);
    }
    camera.updateMatrixWorld();
    if (!controls.dragging && focused < 0 && pointerNdc) {
      const hit = pickTile(pointerNdc[0], pointerNdc[1], camera, centers, TILE_HALF, facing());
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
    setView(next) {
      if (next === mode) return;
      if (focused >= 0) doBlur(); // mode switches mid-focus must not strand uFocused
      mode = next;
      material.uniforms.uFacing.value = mode === "globe" ? -1 : 1;
    },
    focus: focusTile,
    blur: doBlur,
    dispose() {
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
      plane.dispose();
      geo.dispose();
      material.dispose();
      atlas.dispose();
      renderer.dispose();
    },
  };
}
