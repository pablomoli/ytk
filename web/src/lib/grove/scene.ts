// Three.js scene hosting the data trees and two material readings of their
// shared geometry: botanical foliage and anatomical glow-wire x-ray.
import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  CircleGeometry,
  Color,
  DoubleSide,
  DynamicDrawUsage,
  FogExp2,
  InstancedBufferAttribute,
  InstancedMesh,
  LineSegments,
  Matrix4,
  Mesh,
  PerspectiveCamera,
  Scene,
  ShaderMaterial,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  EffectComposer,
  EffectPass,
  RenderPass,
  SMAAEffect,
  ToneMappingEffect,
  ToneMappingMode,
  VignetteEffect,
} from "postprocessing";
import { generateDataTree } from "./datatree";
import type { GrovePayload } from "./datatree";
import { buildLeafGeometry, DEFAULT_LEAF, leafBasis } from "./leaf";
import { paletteFor, paletteOffset, palettePhase } from "./palette";
import {
  leafFragment,
  leafVertex,
  lineVertex,
  tubeFragment,
  tubeVertex,
  xrayLineFragment,
  xrayTubeFragment,
} from "./shaders";
import { buildTreeGeometry, flattenTree, generateTree, rng } from "./tree";
import type { GroveParams } from "./tree";

export type GroveLook = "foliage" | "x-ray";
export const LOOKS: GroveLook[] = ["foliage", "x-ray"];

export type GroveHandle = {
  regenerate: (params: GroveParams) => void;
  setEffects: (params: GroveParams) => void;
  setLook: (look: GroveLook) => void;
  setData: (payload: GrovePayload | null) => void;
  replay: () => void;
  destroy: () => void;
};

export function mountGrove(
  canvas: HTMLCanvasElement,
  params: GroveParams,
  look: GroveLook,
): GroveHandle {
  const renderer = new WebGLRenderer({ canvas, antialias: false, alpha: true });
  const scene = new Scene();
  scene.fog = new FogExp2(new Color("#0a0a0c").getHex(), 0.055);
  const camera = new PerspectiveCamera(46, 1, 0.1, 120);
  camera.position.set(0, 2.4, 7.5);
  const controls = new OrbitControls(camera, canvas);
  controls.target.set(0, 1.4, 0);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.72;

  /* Compositor: vignette + filmic tone response + AA. Output filtering only —
     nothing new is drawn. No grain: the ground is a large flat translucent
     surface, and per-pixel noise over it reads as a corrupted mesh. */
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  composer.addPass(
    new EffectPass(
      camera,
      new SMAAEffect(),
      new ToneMappingEffect({ mode: ToneMappingMode.ACES_FILMIC }),
      new VignetteEffect({ offset: 0.3, darkness: 0.55 }),
    ),
  );

  const uniforms = {
    uProgress: { value: 0 },
    uTime: { value: 0 },
    uWind: { value: params.wind },
    uPaletteTravel: { value: params.paletteTravel },
    uPaletteMotion: { value: params.paletteMotion },
    uPaletteStrength: { value: params.paletteStrength },
    uWireGlow: { value: params.wireGlow },
    uWirePulse: { value: params.wirePulse },
    uWireBody: { value: params.wireBody },
  };
  // Materials share animation/effect uniforms by reference, while palette
  // coefficients are owned per topic. This is decorative, not data-derived.
  const treeMaterials: ShaderMaterial[] = [];
  const vector = (v: readonly [number, number, number]) => new Vector3(v[0], v[1], v[2]);
  const paletteUniforms = (topic: string, requested: string | undefined, root: boolean) => {
    const p = paletteFor(topic, requested);
    return {
      uPaletteA: { value: vector(p.a) },
      uPaletteB: { value: vector(p.b) },
      uPaletteC: { value: vector(p.c) },
      uPaletteD: { value: vector(p.d) },
      uPaletteOffset: { value: paletteOffset(topic) },
      uPalettePhase: { value: palettePhase(topic) },
      uRoot: { value: root ? 1 : 0 },
    };
  };
  const remember = (material: ShaderMaterial) => {
    treeMaterials.push(material);
    return material;
  };
  const tubeMaterialsFor = (topic: string, requested: string | undefined, root = false) => {
    const topicUniforms = paletteUniforms(topic, requested, root);
    return {
      foliage: remember(
        new ShaderMaterial({
          vertexShader: tubeVertex,
          fragmentShader: tubeFragment,
          uniforms: { ...uniforms, ...topicUniforms },
          side: DoubleSide,
        }),
      ),
      xray: remember(
        new ShaderMaterial({
          vertexShader: tubeVertex,
          fragmentShader: xrayTubeFragment,
          uniforms: { ...uniforms, ...topicUniforms },
          side: DoubleSide,
          transparent: true,
          blending: AdditiveBlending,
          depthWrite: false,
        }),
      ),
    };
  };
  const leafMaterialFor = (topic: string, requested?: string) =>
    remember(
      new ShaderMaterial({
        vertexShader: leafVertex,
        fragmentShader: leafFragment,
        uniforms: { ...uniforms, ...paletteUniforms(topic, requested, false) },
        side: DoubleSide,
      }),
    );
  const lineMaterialFor = (topic: string, requested: string | undefined, root = false) =>
    remember(
      new ShaderMaterial({
        vertexShader: lineVertex,
        fragmentShader: xrayLineFragment,
        uniforms: { ...uniforms, ...paletteUniforms(topic, requested, root) },
        transparent: true,
        blending: AdditiveBlending,
        depthWrite: false,
      }),
    );
  const leafGeometry = buildLeafGeometry(DEFAULT_LEAF);

  const groundMaterial = new ShaderMaterial({
    vertexShader:
      "varying vec2 vUv; void main(){ vUv = uv*2.-1.; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }",
    fragmentShader:
      "precision highp float; varying vec2 vUv; void main(){ float r = length(vUv); float disc = smoothstep(1., .25, r); float rim = smoothstep(.02, .0, abs(r - .985))*.35; float a = disc*.16 + rim; gl_FragColor = vec4(vec3(.62,.66,.62)*a + vec3(.05,.055,.05)*disc*.3, a + disc*.12); }",
    transparent: true,
    depthWrite: false,
    side: DoubleSide,
  });
  const ground = new Mesh(new CircleGeometry(9, 64).rotateX(-Math.PI / 2), groundMaterial);
  scene.add(ground);

  let grown: Array<Mesh | LineSegments> = [];
  let currentLook = look;
  let progressTarget = 1;
  let growSeconds = params.growSeconds;
  let lastParams = params;
  // data mode: one tree per bucket, structure from /api/grove topology
  let dataPayload: GrovePayload | null = null;

  const applyEffects = (next: GroveParams) => {
    uniforms.uPaletteTravel.value = next.paletteTravel;
    uniforms.uPaletteMotion.value = next.paletteMotion;
    uniforms.uPaletteStrength.value = next.paletteStrength;
    uniforms.uWireGlow.value = next.wireGlow;
    uniforms.uWirePulse.value = next.wirePulse;
    uniforms.uWireBody.value = next.wireBody;
  };

  const clear = () => {
    for (const object of grown) {
      object.geometry.dispose();
      scene.remove(object);
    }
    grown = [];
    for (const m of treeMaterials) m.dispose();
    treeMaterials.length = 0;
  };
  const tagged = <T extends Mesh | LineSegments>(
    object: T,
    role: "wood" | "root" | "line" | "root-line" | "leaves",
    foliage?: ShaderMaterial,
    xray?: ShaderMaterial,
  ) => {
    object.userData.groveRole = role;
    object.userData.foliageMaterial = foliage;
    object.userData.xrayMaterial = xray;
    return object;
  };

  const plant = (next: GroveParams) => {
    clear();
    lastParams = next;
    growSeconds = next.growSeconds;
    uniforms.uWind.value = next.wind;
    applyEffects(next);
    const rand = rng(next.seed);
    const buckets = dataPayload?.buckets ?? [];
    const treeCount = buckets.length || next.trees;
    const maxBucketNotes = Math.max(1, ...buckets.map((b) => b.n_notes));
    const ringRadius =
      buckets.length > 1 ? Math.max(2.4, Math.sqrt(treeCount) * next.reach * 0.42) : 0;
    if (buckets.length) {
      // frame the whole ring; the user can still orbit in from there.
      // azimuth rotates the viewpoint around the vertical axis (E7 control)
      const az = dataPayload?.azimuth ?? 0;
      const dist = ringRadius * 1.55 + 6;
      camera.position.set(Math.sin(az) * dist, ringRadius * 0.55 + 2.2, Math.cos(az) * dist);
      controls.target.set(0, 1.1, 0);
    }
    const spread = Math.max(1, treeCount - 1) * next.reach * 0.75;
    for (let t = 0; t < treeCount; t++) {
      // data mode plants the buckets in a ring; aesthetic mode keeps the line
      const origin = buckets.length
        ? new Vector3(
            Math.cos((t / treeCount) * Math.PI * 2) * ringRadius,
            0,
            Math.sin((t / treeCount) * Math.PI * 2) * ringRadius,
          )
        : new Vector3(
            treeCount === 1 ? 0 : -spread / 2 + (t / Math.max(1, treeCount - 1)) * spread,
            0,
            treeCount === 1 ? 0 : (rand() - 0.5) * next.reach,
          );
      // topic size sets tree scale: epicmap towers, a two-note interest is
      // a seedling. sqrt keeps the 1000x mass range within one grove.
      const bucket = buckets[t];
      const topic = bucket?.bucket ?? `seed:${next.seed}`;
      const requestedPalette = bucket?.palette;
      const sizeScale = bucket ? 0.45 + 0.55 * Math.sqrt(bucket.n_notes / maxBucketNotes) : 1;
      const treeParams = bucket
        ? {
            ...next,
            reach: lastParams.reach * sizeScale,
            girth: lastParams.girth * (0.5 + 0.5 * sizeScale),
          }
        : next;
      const tubeGeo = (g: {
        position: Float32Array;
        roff: Float32Array;
        depth: Float32Array;
        index: Uint32Array;
      }) => {
        const tube = new BufferGeometry();
        tube.setAttribute("position", new BufferAttribute(g.position, 3));
        tube.setAttribute("roff", new BufferAttribute(g.roff, 3));
        tube.setAttribute("depth", new BufferAttribute(g.depth, 1));
        tube.setIndex(new BufferAttribute(g.index, 1));
        return tube;
      };
      const lineGeo = (g: { linePosition: Float32Array; lineDepth: Float32Array }) => {
        const lines = new BufferGeometry();
        lines.setAttribute("position", new BufferAttribute(g.linePosition, 3));
        lines.setAttribute("depth", new BufferAttribute(g.lineDepth, 1));
        return lines;
      };
      const canopyBudget = Math.max(700, Math.floor(4400 / treeCount));
      const tree = buildTreeGeometry(
        treeParams,
        bucket
          ? generateDataTree(treeParams, rand, origin, bucket, canopyBudget)
          : generateTree(treeParams, rand, origin, canopyBudget),
      );
      const woodMaterials = tubeMaterialsFor(topic, requestedPalette);
      grown.push(
        tagged(
          new Mesh(tubeGeo(tree), woodMaterials.foliage),
          "wood",
          woodMaterials.foliage,
          woodMaterials.xray,
        ),
      );
      grown.push(
        tagged(new LineSegments(lineGeo(tree), lineMaterialFor(topic, requestedPalette)), "line"),
      );
      // root system: the same organism grown the opposite way - shorter
      // reach, inverted up bias, a touch gnarlier, darker wood
      const rootParams = {
        ...treeParams,
        reach: treeParams.reach * 0.8,
        upBias: -0.45,
        initialChildren: Math.max(2, treeParams.initialChildren),
        branchChance: Math.min(0.6, treeParams.branchChance + 0.1),
        noise: treeParams.noise * 1.25,
        stepScale: treeParams.stepScale * 0.8,
        girth: treeParams.girth * 1.1,
        stiffness: treeParams.stiffness * 0.85,
      };
      const roots = buildTreeGeometry(
        rootParams,
        flattenTree(
          generateTree(rootParams, rand, origin, Math.max(200, Math.floor(1200 / treeCount))),
          0.4,
        ),
      );
      // roots are anchored: same shaders, but their wind uniform is pinned to 0
      const still = (m: ShaderMaterial) => {
        m.uniforms.uWind = { value: 0 };
        return m;
      };
      const rootMaterials = tubeMaterialsFor(topic, requestedPalette, true);
      still(rootMaterials.foliage);
      still(rootMaterials.xray);
      grown.push(
        tagged(
          new Mesh(tubeGeo(roots), rootMaterials.foliage),
          "root",
          rootMaterials.foliage,
          rootMaterials.xray,
        ),
      );
      grown.push(
        tagged(
          new LineSegments(lineGeo(roots), still(lineMaterialFor(topic, requestedPalette, true))),
          "root-line",
        ),
      );
      // Foliage geometry is always built once, then hidden in x-ray. Switching
      // looks only changes visibility/materials and never regenerates topology.
      {
        const perSite = Math.max(1, Math.round(treeParams.leafDensity / 12));
        // instance budget per tree: stride sites rather than truncate the
        // canopy so dense settings thin evenly instead of balding at the top
        const stride = Math.max(
          1,
          Math.ceil((tree.leafSites.length * perSite) / Math.max(2500, 14_000 / treeCount)),
        );
        const sites = tree.leafSites.filter((_, index) => index % stride === 0);
        const count = sites.length * perSite;
        const leaves = new InstancedMesh(
          leafGeometry,
          leafMaterialFor(topic, requestedPalette),
          count,
        );
        leaves.instanceMatrix.setUsage(DynamicDrawUsage);
        const iDepth = new Float32Array(count);
        const iPhase = new Float32Array(count);
        const matrix = new Matrix4();
        let n = 0;
        for (const site of sites) {
          for (let i = 0; i < perSite; i++) {
            const spin = rand() * Math.PI * 2;
            const pitch = 0.35 + rand() * 0.75; // feather outward-and-along
            const { xAxis, yAxis, zAxis } = leafBasis(site.tangent, site.normal, spin, pitch);
            const seat = site.position.clone().add(yAxis.clone().multiplyScalar(site.radius * 0.8));
            const scale = treeParams.leafSize * (0.55 + rand() * 0.75) * (0.6 + 0.4 * site.depth);
            matrix
              .makeBasis(
                xAxis.multiplyScalar(scale),
                yAxis.multiplyScalar(scale),
                zAxis.multiplyScalar(scale),
              )
              .setPosition(seat);
            leaves.setMatrixAt(n, matrix);
            iDepth[n] = Math.min(1, site.depth + rand() * 0.08);
            iPhase[n] = rand();
            n++;
          }
        }
        leaves.geometry = leafGeometry.clone();
        leaves.geometry.setAttribute("iDepth", new InstancedBufferAttribute(iDepth, 1));
        leaves.geometry.setAttribute("iPhase", new InstancedBufferAttribute(iPhase, 1));
        grown.push(tagged(leaves, "leaves"));
      }
    }
    for (const object of grown) scene.add(object);
    applyLook();
    uniforms.uProgress.value = 0;
    progressTarget = 1;
  };

  const applyLook = () => {
    grown.forEach((object) => {
      const role = object.userData.groveRole;
      object.visible =
        role === "leaves"
          ? currentLook === "foliage"
          : role === "line" || role === "root-line"
            ? currentLook === "x-ray"
            : true;
      if (role === "wood" || role === "root") {
        object.material =
          currentLook === "x-ray" ? object.userData.xrayMaterial : object.userData.foliageMaterial;
      }
    });
  };

  let frame = 0;
  let last = 0;
  const resize = () => {
    const w = canvas.clientWidth || innerWidth;
    const h = canvas.clientHeight || innerHeight;
    renderer.setSize(w, h, false);
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    composer.setSize(w, h);
  };
  const render = (now = 0) => {
    const dt = last ? Math.min(0.05, (now - last) / 1000) : 0.016;
    last = now;
    uniforms.uTime.value += dt;
    if (uniforms.uProgress.value < progressTarget)
      uniforms.uProgress.value = Math.min(
        progressTarget,
        uniforms.uProgress.value + dt / Math.max(0.5, growSeconds),
      );
    controls.update();
    composer.render();
    frame = requestAnimationFrame(render);
  };
  resize();
  addEventListener("resize", resize);
  plant(params);
  render();

  return {
    regenerate: (next) => plant(next),
    setEffects: (next) => {
      lastParams = next;
      applyEffects(next);
    },
    setData: (payload) => {
      dataPayload = payload;
      plant(lastParams);
    },
    setLook: (next) => {
      currentLook = next;
      applyLook();
    },
    replay: () => {
      uniforms.uProgress.value = 0;
    },
    destroy: () => {
      cancelAnimationFrame(frame);
      removeEventListener("resize", resize);
      clear();
      controls.dispose();
      leafGeometry.dispose();
      ground.geometry.dispose();
      groundMaterial.dispose();
      composer.dispose();
      renderer.dispose();
    },
  };
}
