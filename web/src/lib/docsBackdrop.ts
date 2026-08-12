import * as THREE from "three";

export type BackdropHandle = { dispose: () => void };

const VERT = /* glsl */ `
  uniform float uTime;
  attribute float aPhase;
  attribute float aSize;
  varying float vTwinkle;
  void main() {
    vec3 p = position;
    // drift is authored in the shader so the buffer never re-uploads
    p.x += sin(uTime * 0.03 + aPhase) * 0.6;
    p.y += cos(uTime * 0.021 + aPhase * 1.7) * 0.4;
    vTwinkle = 0.55 + 0.45 * sin(uTime * 0.4 + aPhase * 6.28);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_PointSize = aSize * (140.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

const FRAG = /* glsl */ `
  uniform vec3 uColor;
  varying float vTwinkle;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.0, d) * vTwinkle * 0.35;
    gl_FragColor = vec4(uColor, a);
  }
`;

/** Sparse ember dust behind the record grid. Purely decorative: the grid
    never depends on it, and reduced-motion viewers get a single still frame. */
export function mountBackdrop(canvas: HTMLCanvasElement): BackdropHandle {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 60);
  camera.position.z = 10;

  const N = 1200;
  const pos = new Float32Array(N * 3);
  const phase = new Float32Array(N);
  const size = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 26;
    pos[i * 3 + 1] = (Math.random() - 0.5) * 16;
    pos[i * 3 + 2] = -Math.random() * 14;
    phase[i] = Math.random() * Math.PI * 2;
    size[i] = 0.35 + Math.random() * 1.1;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
  geo.setAttribute("aSize", new THREE.BufferAttribute(size, 1));
  const mat = new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms: {
      uTime: { value: 0 },
      uColor: { value: new THREE.Color("#e2b04a") },
    },
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
