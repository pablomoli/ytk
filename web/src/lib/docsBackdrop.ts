import * as THREE from "three";

export type BackdropHandle = { dispose: () => void };

const VERT = /* glsl */ `
  uniform float uTime;
  attribute float aPhase;
  attribute float aSize;
  attribute vec3 aColor;
  varying float vTwinkle;
  varying vec3 vColor;
  void main() {
    vec3 p = position;
    // drift is authored in the shader so the buffer never re-uploads
    p.x += sin(uTime * 0.03 + aPhase) * 0.6;
    p.y += cos(uTime * 0.021 + aPhase * 1.7) * 0.4;
    vTwinkle = 0.65 + 0.35 * sin(uTime * 0.5 + aPhase * 6.28);
    vColor = aColor;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_PointSize = aSize * (170.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

const FRAG = /* glsl */ `
  varying float vTwinkle;
  varying vec3 vColor;
  void main() {
    float d = length(gl_PointCoord - 0.5) * 2.0;
    // hard bright core, tight falloff: a star, not a smudge
    float core = smoothstep(0.35, 0.0, d);
    float halo = pow(max(1.0 - d, 0.0), 4.0) * 0.5;
    float a = (core + halo) * vTwinkle;
    if (a < 0.02) discard;
    gl_FragColor = vec4(vColor, a);
  }
`;

/** Sparse starfield behind the record grid. Purely decorative: the grid
    never depends on it, and reduced-motion viewers get a single still frame. */
export function mountBackdrop(canvas: HTMLCanvasElement): BackdropHandle {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false });
  // full retina density — a capped ratio is what made the points look soft
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 60);
  camera.position.z = 10;

  const N = 550;
  const pos = new Float32Array(N * 3);
  const phase = new Float32Array(N);
  const size = new Float32Array(N);
  const color = new Float32Array(N * 3);
  const brass = new THREE.Color("#e8b656");
  const white = new THREE.Color("#f0eee7");
  const c = new THREE.Color();
  for (let i = 0; i < N; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 26;
    pos[i * 3 + 1] = (Math.random() - 0.5) * 16;
    pos[i * 3 + 2] = -Math.random() * 14;
    phase[i] = Math.random() * Math.PI * 2;
    // mostly pinpricks, a handful of standouts
    size[i] = Math.random() < 0.06 ? 1.6 + Math.random() * 1.2 : 0.5 + Math.random() * 0.7;
    c.copy(Math.random() < 0.35 ? brass : white);
    c.multiplyScalar(0.7 + Math.random() * 0.3);
    color[i * 3] = c.r;
    color[i * 3 + 1] = c.g;
    color[i * 3 + 2] = c.b;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
  geo.setAttribute("aSize", new THREE.BufferAttribute(size, 1));
  geo.setAttribute("aColor", new THREE.BufferAttribute(color, 3));
  const mat = new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms: { uTime: { value: 0 } },
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const points = new THREE.Points(geo, mat);
  // positions move in the vertex shader; the base bounding sphere would cull wrongly
  points.frustumCulled = false;
  scene.add(points);

  const resize = () => {
    const w = canvas.clientWidth || 1;
    const h = canvas.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  resize();
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);

  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let raf = 0;
  let t = 0;
  const frame = () => {
    t += 1 / 60;
    mat.uniforms.uTime.value = t;
    renderer.render(scene, camera);
    if (!still) raf = requestAnimationFrame(frame);
  };
  const onVisibility = () => {
    cancelAnimationFrame(raf);
    if (!document.hidden) raf = requestAnimationFrame(frame);
  };
  document.addEventListener("visibilitychange", onVisibility);
  raf = requestAnimationFrame(frame);

  return {
    dispose() {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
      ro.disconnect();
      geo.dispose();
      mat.dispose();
      renderer.dispose();
    },
  };
}
