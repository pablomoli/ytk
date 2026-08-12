import {
  ClampToEdgeWrapping,
  Color,
  DataTexture,
  DoubleSide,
  Float32BufferAttribute,
  GLSL3,
  LinearFilter,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  PlaneGeometry,
  Points,
  PointsMaterial,
  RawShaderMaterial,
  RedFormat,
  RepeatWrapping,
  RingGeometry,
  Raycaster,
  SRGBColorSpace,
  Scene,
  SphereGeometry,
  Texture,
  TextureLoader,
  Vector2,
  Vector3,
  WebGLRenderer,
  BufferGeometry,
} from "three";
import { DUR, gsap, reducedMotion } from "../motion";
import { BG, DIM, PANEL, PUNCH_GAMMA, TEXT, planetColor, saturation } from "../palette";
import type { GalaxyData, GalaxyMoon } from "../../api/galaxy";
import { createControls } from "../orb/controls";
import { normalizeWheelDelta } from "../orb/scene";
import { ringNormal, slerp, spinRadPerSec, standoff, worldRadius, type V3 } from "./math";
import { pickPlanet } from "./pick";

const R_CLOSE = 1.6; // overview orbit radius at wheel zoom 0
const R_FAR = 4.0; // ... and at zoom 1
const STAR_R = 8.0;
const STARS = 600;
const MOON_ORBIT_R = 1.6; // in planet radii
const MOON_PERIOD = 45; // seconds
const COAST_AMP = 0.04; // shader-side micro-detail on top of the bake
const RING_INNER = 1.25; // in planet radii
const RING_OUTER = 1.32;
// no planet carries a median age: neutral default matching the 90-day
// activity window rather than a still galaxy
const NEUTRAL_AGE_DAYS = 90;

const VERT = /* glsl */ `
precision highp float;
in vec3 position;
in vec3 normal;
uniform mat4 modelViewMatrix, projectionMatrix;
out vec3 vN;
void main() {
  vN = normalize(normal);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const shoreAccent = planetColor(TEXT, 1).map((c) => c.toFixed(3)).join(", ");

const FRAG = /* glsl */ `
precision highp float;
uniform sampler2D uField;
uniform vec3 uHue;
uniform float uSpin, uSeed, uCoastAmp;
in vec3 vN;
out vec4 outColor;

float hash13(vec3 p) {
  return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
}

float vnoise(vec3 p) {
  vec3 i = floor(p);
  vec3 f = fract(p);
  vec3 u = f * f * (3.0 - 2.0 * f);
  float n00 = mix(hash13(i + vec3(0.0, 0.0, 0.0)), hash13(i + vec3(1.0, 0.0, 0.0)), u.x);
  float n10 = mix(hash13(i + vec3(0.0, 1.0, 0.0)), hash13(i + vec3(1.0, 1.0, 0.0)), u.x);
  float n01 = mix(hash13(i + vec3(0.0, 0.0, 1.0)), hash13(i + vec3(1.0, 0.0, 1.0)), u.x);
  float n11 = mix(hash13(i + vec3(0.0, 1.0, 1.0)), hash13(i + vec3(1.0, 1.0, 1.0)), u.x);
  return mix(mix(n00, n10, u.y), mix(n01, n11, u.y), u.z);
}

float fbm3(vec3 p) {
  float amp = 0.5, sum = 0.0, norm = 0.0;
  for (int i = 0; i < 3; i++) {
    sum += amp * vnoise(p);
    norm += amp;
    p *= 2.0;
    amp *= 0.5;
  }
  return sum / norm;
}

void main() {
  // equirect sample of the baked field; 0.5 = shoreline (ytk/coast.py contract)
  float lon = atan(vN.y, vN.x);
  float lat = asin(clamp(vN.z, -1.0, 1.0));
  vec2 uv = vec2(lon / 6.28318530718 + 0.5 + uSpin, 0.5 + lat / 3.14159265359);
  float d = texture(uField, uv).r + uCoastAmp * (fbm3(vN * 9.0 + uSeed) - 0.5);
  float land = smoothstep(0.5, 0.505, d);
  float depth = pow(clamp((d - 0.5) * 2.0, 0.0, 1.0), ${PUNCH_GAMMA.toFixed(2)});
  vec3 landCol = uHue * (0.35 + 0.65 * depth);
  vec3 seaCol = uHue * 0.08 * clamp(d * 2.0, 0.0, 1.0);
  float shore = smoothstep(0.012, 0.0, abs(d - 0.5)) * 0.35;
  outColor = vec4(mix(seaCol, landCol, land) + vec3(${shoreAccent}) * shore, 1.0);
}`;

export type GalaxyHandle = {
  visit(theme: number): void;
  overview(): void;
  dispose(): void;
};

export type GalaxyCallbacks = {
  onHover(theme: number | null): void;
  onVisit(theme: number | null): void;
  onMoonOpen(moon: { path: string; title: string }): void;
};

const median = (xs: number[]): number | null => {
  if (xs.length === 0) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

// unit ring in the plane tangent to `n`, used for moon orbits
const tangentBasis = (n: Vector3): [Vector3, Vector3] => {
  const ref = Math.abs(n.y) > 0.9 ? new Vector3(1, 0, 0) : new Vector3(0, 1, 0);
  const e1 = new Vector3().crossVectors(ref, n).normalize();
  return [e1, new Vector3().crossVectors(n, e1)];
};

export function mountGalaxy(canvas: HTMLCanvasElement, data: GalaxyData, cb: GalaxyCallbacks): GalaxyHandle {
  const planets = data.planets;
  const renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(BG);
  // far plane clears the starfield shell at STAR_R plus the widest orbit radius
  const camera = new PerspectiveCamera(60, canvas.clientWidth / Math.max(1, canvas.clientHeight), 0.01, 20);
  const scene = new Scene();

  let disposed = false;
  const loader = new TextureLoader();
  const loaded: Texture[] = []; // async arrivals, disposed with the scene

  // 1x1 mid-gray = the shoreline value: a planet whose bake 404s or is still
  // in flight paints as an all-coast world instead of failing the frame.
  const fallback = new DataTexture(new Uint8Array([128]), 1, 1, RedFormat);
  fallback.needsUpdate = true;

  const cohesions = planets.map((p) => p.cohesion);
  const coLo = Math.min(...cohesions);
  const coHi = Math.max(...cohesions);
  const ages = planets.map((p) => p.median_age_days).filter((a): a is number => a !== null);
  const populationMedian = median(ages) ?? NEUTRAL_AGE_DAYS;

  const base = new RawShaderMaterial({
    glslVersion: GLSL3,
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms: {
      uField: { value: fallback },
      uHue: { value: new Vector3(1, 1, 1) },
      uSpin: { value: 0 },
      uSeed: { value: 0 },
      uCoastAmp: { value: COAST_AMP },
    },
  });

  const sphereGeos: SphereGeometry[] = [];
  const materials: RawShaderMaterial[] = [];
  const turnsPerSec: number[] = [];
  const centers: Vector3[] = [];
  const standoffDir: Vector3[] = [];
  const standoffR: number[] = [];
  const themeIndex = new Map<number, number>();

  planets.forEach((p, i) => {
    themeIndex.set(p.theme, i);
    const R = worldRadius(p.radius_deg);
    const geo = new SphereGeometry(R, 48, 24);
    const mat = base.clone();
    const [r, g, b] = planetColor(p.hue, saturation(p.cohesion, coLo, coHi));
    mat.uniforms.uHue.value = new Vector3(r, g, b);
    mat.uniforms.uSeed.value = p.theme;
    const mesh = new Mesh(geo, mat);
    mesh.position.set(p.pos[0], p.pos[1], p.pos[2]);
    scene.add(mesh);
    sphereGeos.push(geo);
    materials.push(mat);
    centers.push(mesh.position.clone());
    // the channel encodes only where it earned: a planet that failed the spin
    // gate turns at the population-median rate, not its own age
    const rate = spinRadPerSec(p.spin.earned ? p.spin.median_age_days : null, populationMedian);
    turnsPerSec.push(rate / (2 * Math.PI));
    const so = standoff(p.pos, p.radius_deg);
    const soV = new Vector3(so[0], so[1], so[2]);
    standoffR.push(soV.length());
    standoffDir.push(soV.clone().normalize());

    loader.load(
      `/galaxy-tex/${p.tex}`,
      (tex) => {
        if (disposed) {
          tex.dispose();
          return;
        }
        // ytk/coast.py grid() writes lat row 0 = -pi/2 (south pole) first, PIL
        // makes that the PNG's top row, flipY=false keeps top at v=0, so v=1.0
        // samples the north pole exactly as equirectUv defines it.
        tex.flipY = false;
        tex.wrapS = RepeatWrapping; // uSpin scrolls u past the seam
        tex.wrapT = ClampToEdgeWrapping;
        tex.minFilter = LinearFilter;
        tex.magFilter = LinearFilter;
        tex.generateMipmaps = false;
        tex.needsUpdate = true;
        loaded.push(tex);
        mat.uniforms.uField.value = tex;
      },
      undefined,
      () => {}, // 404 stays on the fallback texture; not fatal
    );
  });

  const ringGeos: RingGeometry[] = [];
  const ringMat = new MeshBasicMaterial({ color: TEXT, transparent: true, opacity: 0.35, side: DoubleSide });
  planets.forEach((p, i) => {
    if (!p.rings.earned) return;
    const R = worldRadius(p.radius_deg);
    const geo = new RingGeometry(RING_INNER * R, RING_OUTER * R, 64);
    const mesh = new Mesh(geo, ringMat);
    mesh.position.copy(centers[i]);
    const partner = p.rings.partners[0];
    const pIdx = partner === undefined ? undefined : themeIndex.get(partner.theme);
    // no resolvable partner: ringNormal's degenerate branch still yields a
    // deterministic tilt, so an earned channel is never silently dropped
    const partnerPos: V3 = pIdx === undefined ? p.pos : planets[pIdx].pos;
    const n = ringNormal(p.pos, partnerPos);
    mesh.lookAt(mesh.position.x + n[0], mesh.position.y + n[1], mesh.position.z + n[2]);
    scene.add(mesh);
    ringGeos.push(geo);
  });

  type MoonSlot = { mesh: Mesh; moon: GalaxyMoon; center: Vector3; e1: Vector3; e2: Vector3; r: number; phase: number };
  const moonSlots: MoonSlot[] = [];
  const moonMats: MeshBasicMaterial[] = [];
  const moonGeo = new PlaneGeometry(1, 1);
  planets.forEach((p, i) => {
    if (p.moons.length === 0) return;
    const R = worldRadius(p.radius_deg);
    const [e1, e2] = tangentBasis(centers[i].clone().normalize());
    p.moons.forEach((moon, j) => {
      const mat = new MeshBasicMaterial({ color: PANEL, transparent: false });
      if (moon.thumb) {
        loader.load(
          `/vault-media/${moon.thumb}`,
          (tex) => {
            if (disposed) {
              tex.dispose();
              return;
            }
            // thumbnails are color, unlike the planet distance fields:
            // MeshBasicMaterial's colorspace_fragment would otherwise apply an
            // uncancelled linear-to-sRGB pass and wash them out
            tex.colorSpace = SRGBColorSpace;
            loaded.push(tex);
            mat.map = tex;
            mat.color = new Color(0xffffff);
            mat.needsUpdate = true;
          },
          undefined,
          () => {}, // 404 leaves the PANEL quad
        );
      }
      const mesh = new Mesh(moonGeo, mat);
      const half = R * (0.18 + 0.02 * Math.min(moon.size, 10));
      mesh.scale.set(half * 2, half * 2, 1);
      scene.add(mesh);
      moonMats.push(mat);
      moonSlots.push({
        mesh,
        moon,
        center: centers[i],
        e1,
        e2,
        r: MOON_ORBIT_R * R,
        phase: (j / p.moons.length) * Math.PI * 2,
      });
    });
  });

  const starGeo = new BufferGeometry();
  const stars = new Float32Array(STARS * 3);
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < STARS; i++) {
    const y = 1 - (2 * (i + 0.5)) / STARS;
    const rr = Math.sqrt(Math.max(0, 1 - y * y));
    const phi = i * golden;
    stars.set([Math.cos(phi) * rr * STAR_R, y * STAR_R, Math.sin(phi) * rr * STAR_R], i * 3);
  }
  starGeo.setAttribute("position", new Float32BufferAttribute(stars, 3));
  const starMat = new PointsMaterial({ color: DIM, size: 0.02 });
  const starPoints = new Points(starGeo, starMat);
  // the shell's bounding sphere is correct, but a Points cloud that vanishes
  // when its center leaves the frustum reads as a rendering bug; keep it drawn
  starPoints.frustumCulled = false;
  scene.add(starPoints);

  const controls = createControls();
  const raycaster = new Raycaster();
  const ndc = new Vector2();
  let pointerNdc: [number, number] | null = null;
  let hovered: number | null = null;
  let visiting: number | null = null; // planet index the camera is flying to / parked at
  const flight = { t: 1 }; // 1 = arrived; a tween drives 0 -> 1
  const fromDir: V3 = [0, 0, 1];
  let fromR = R_CLOSE;
  const fromLook = new Vector3();
  const _ov = new Vector3();
  const _toDir = new Vector3();
  const _look = new Vector3();
  const _lookNow = new Vector3();
  const _toT: V3 = [0, 0, 0];
  let orbitT = 0; // moon orbit clock; frozen under reduced motion
  // read once at mount, as orb does: a per-frame matchMedia is a needless
  // allocation and the setting does not change mid-session in practice
  const frozen = reducedMotion();

  const overviewPos = (yaw: number, pitch: number, zoom: number, out: Vector3) => {
    // orb globe-mode semantics: same negated yaw/pitch trackball feel
    const r = R_CLOSE + zoom * (R_FAR - R_CLOSE);
    const gyaw = -yaw, gpitch = -pitch;
    const cosP = Math.cos(gpitch);
    return out.set(Math.sin(gyaw) * cosP * r, -Math.sin(gpitch) * r, Math.cos(gyaw) * cosP * r);
  };

  // seed the rest pose so a visit() before the first frame has a real
  // departure direction; slerp from a zero vector collapses the arc
  overviewPos(0, 0, 0.5, camera.position);
  camera.lookAt(0, 0, 0);

  const startFlight = () => {
    const r = camera.position.length();
    fromDir[0] = camera.position.x / r;
    fromDir[1] = camera.position.y / r;
    fromDir[2] = camera.position.z / r;
    fromR = r;
    fromLook.copy(_lookNow);
    gsap.killTweensOf(flight);
    if (frozen) {
      flight.t = 1;
      return;
    }
    flight.t = 0;
    gsap.to(flight, { t: 1, duration: DUR.reveal });
  };

  function doVisit(theme: number) {
    const i = themeIndex.get(theme);
    if (i === undefined) return;
    if (hovered !== null) {
      hovered = null;
      cb.onHover(null);
    }
    startFlight();
    visiting = i;
    cb.onVisit(theme); // fires at departure: the caption follows the camera, not the arrival
  }

  function doOverview() {
    startFlight();
    visiting = null;
    cb.onVisit(null);
  }

  const ndcOf = (e: PointerEvent): [number, number] => {
    const r = canvas.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * 2 - 1, -(((e.clientY - r.top) / r.height) * 2 - 1)];
  };
  const onDown = (e: PointerEvent) => {
    canvas.setPointerCapture(e.pointerId);
    pointerNdc = ndcOf(e);
    controls.down(e.clientX, e.clientY);
  };
  const onMove = (e: PointerEvent) => {
    pointerNdc = ndcOf(e);
    controls.move(e.clientX, e.clientY);
  };
  const onUp = (e: PointerEvent) => {
    const { tap } = controls.up();
    if (tap && pointerNdc) {
      ndc.set(pointerNdc[0], pointerNdc[1]);
      raycaster.setFromCamera(ndc, camera);
      const hit = moonSlots.length ? raycaster.intersectObjects(moonSlots.map((m) => m.mesh), false)[0] : undefined;
      const slot = hit && moonSlots.find((m) => m.mesh === hit.object);
      if (slot) cb.onMoonOpen({ path: slot.moon.path, title: slot.moon.title });
      else {
        const p = pickPlanet(pointerNdc[0], pointerNdc[1], camera, planets);
        if (p !== null) doVisit(planets[p].theme);
      }
    }
    canvas.releasePointerCapture(e.pointerId);
  };
  const onWheel = (e: WheelEvent) => controls.wheel(normalizeWheelDelta(e.deltaY, e.deltaMode, canvas.clientHeight));
  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerup", onUp);
  canvas.addEventListener("wheel", onWheel, { passive: true });

  let raf = 0;
  let last = performance.now();
  const loop = (now: number) => {
    raf = requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const { yaw, pitch, zoom } = controls.step(dt);

    if (!frozen) {
      for (let i = 0; i < materials.length; i++) materials[i].uniforms.uSpin.value += turnsPerSec[i] * dt;
      orbitT += dt;
    }

    overviewPos(yaw, pitch, zoom, _ov);
    let toR: number;
    if (visiting !== null) {
      _toDir.copy(standoffDir[visiting]);
      toR = standoffR[visiting];
      _look.copy(centers[visiting]);
    } else {
      toR = _ov.length();
      _toDir.copy(_ov).divideScalar(toR);
      _look.set(0, 0, 0);
    }
    if (flight.t < 1) {
      _toT[0] = _toDir.x; _toT[1] = _toDir.y; _toT[2] = _toDir.z;
      const d = slerp(fromDir, _toT, flight.t);
      const r = fromR + (toR - fromR) * flight.t;
      camera.position.set(d[0] * r, d[1] * r, d[2] * r);
      _lookNow.lerpVectors(fromLook, _look, flight.t);
    } else {
      camera.position.copy(_toDir).multiplyScalar(toR);
      _lookNow.copy(_look);
    }
    camera.lookAt(_lookNow);
    camera.updateMatrixWorld();

    for (const m of moonSlots) {
      const a = m.phase + (orbitT / MOON_PERIOD) * Math.PI * 2;
      m.mesh.position.copy(m.center)
        .addScaledVector(m.e1, Math.cos(a) * m.r)
        .addScaledVector(m.e2, Math.sin(a) * m.r);
      m.mesh.quaternion.copy(camera.quaternion);
    }

    if (visiting === null && !controls.dragging && pointerNdc) {
      const hit = pickPlanet(pointerNdc[0], pointerNdc[1], camera, planets);
      const theme = hit === null ? null : planets[hit].theme;
      if (theme !== hovered) {
        hovered = theme;
        cb.onHover(theme);
      }
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
    visit: doVisit,
    overview: doOverview,
    dispose() {
      disposed = true;
      cancelAnimationFrame(raf);
      gsap.killTweensOf(flight);
      resize.disconnect();
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("wheel", onWheel);
      for (const g of sphereGeos) g.dispose();
      for (const g of ringGeos) g.dispose();
      for (const m of materials) m.dispose();
      for (const m of moonMats) m.dispose();
      moonGeo.dispose();
      ringMat.dispose();
      starGeo.dispose();
      starMat.dispose();
      base.dispose();
      fallback.dispose();
      for (const t of loaded) t.dispose();
      renderer.dispose();
    },
  };
}
