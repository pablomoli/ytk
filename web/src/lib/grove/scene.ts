// PROTOTYPE (grove workshop) - throwaway until a look wins a real spec.
// Three.js scene hosting the Ballot trees: fresnel-rimmed tube shader with the
// clamped-cosine growth ramp (depth as phase) and a uTime pulse, plus the
// wireframe and foliage looks over the same generated geometry.
import { AdditiveBlending, BufferAttribute, BufferGeometry, CircleGeometry, Color, DoubleSide, DynamicDrawUsage, FogExp2, InstancedBufferAttribute, InstancedMesh, LineSegments, Matrix4, Mesh, MeshBasicMaterial, PerspectiveCamera, Points, Scene, ShaderMaterial, Vector3, WebGLRenderer } from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { buildLeafGeometry, DEFAULT_LEAF, leafBasis } from './leaf'
import { buildTreeGeometry, generateTree, rng } from './tree'
import type { GroveParams } from './tree'

export type GroveLook = 'tubes' | 'wires' | 'foliage'
export const LOOKS: GroveLook[] = ['tubes', 'wires', 'foliage']

const RAMP = `float ramp(float p){ return .5 - .5*cos(clamp(p,0.,1.)*3.14159265); }`

const tubeVertex = `attribute vec3 roff; attribute float depth;
uniform float uProgress;
varying float vDepth; varying float vGrow; varying vec3 vN; varying vec3 vView;
${RAMP}
void main(){
  float g = ramp(uProgress*1.35 - depth);
  vec3 p = position + roff*g;
  vDepth = depth; vGrow = g;
  vec4 mv = modelViewMatrix*vec4(p,1.);
  vN = normalMatrix*normalize(roff + vec3(1e-5));
  vView = -mv.xyz;
  gl_Position = projectionMatrix*mv; }`

const tubeFragment = `precision highp float;
uniform float uTime; uniform vec3 uBase; uniform vec3 uRim;
varying float vDepth; varying float vGrow; varying vec3 vN; varying vec3 vView;
void main(){
  if (vGrow < .03) discard;
  vec3 n = normalize(vN); vec3 v = normalize(vView);
  float fres = pow(1. - abs(dot(n, v)), 2.2);
  float pulse = .5 + .5*sin(uTime*1.7 - vDepth*7.5);
  vec3 c = uBase*(.25 + .3*abs(dot(n, v))) + uRim*fres*(.75 + .45*pulse);
  gl_FragColor = vec4(c, 1.); }`

const lineVertex = `attribute float depth;
uniform float uProgress;
varying float vDepth; varying float vGrow;
${RAMP}
void main(){
  vDepth = depth; vGrow = ramp(uProgress*1.35 - depth);
  gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }`

const lineFragment = `precision highp float;
uniform float uTime; uniform vec3 uRim;
varying float vDepth; varying float vGrow;
void main(){
  float pulse = .5 + .5*sin(uTime*1.7 - vDepth*7.5);
  float a = vGrow*(.28 + .5*pulse*(1.-vDepth) + .25*(1.-vDepth));
  gl_FragColor = vec4(uRim*a, a); }`

const leafVertex = `attribute float iDepth; attribute float iPhase;
uniform float uProgress; uniform float uTime;
varying vec3 vN; varying vec3 vView; varying float vPhase; varying float vAlong;
${RAMP}
void main(){
  float g = ramp(uProgress*1.35 - iDepth);
  // wind: stacked sines, tip moves more than base, no two leaves in step
  float along = uv.y;
  float sway = along*along*(.5*sin(uTime*1.9 + iPhase*6.28) + .3*sin(uTime*3.7 + iPhase*9.4) + .2*sin(uTime*.7 + iPhase*3.1))*.08;
  vec3 p = position*g;
  p.x += sway; p.z += sway*.6;
  #ifdef USE_INSTANCING
  vec4 world = modelViewMatrix*instanceMatrix*vec4(p,1.);
  vN = normalMatrix*mat3(instanceMatrix)*normal;
  #else
  vec4 world = modelViewMatrix*vec4(p,1.);
  vN = normalMatrix*normal;
  #endif
  vView = -world.xyz;
  vPhase = iPhase;
  vAlong = along;
  gl_Position = projectionMatrix*world; }`

const leafFragment = `precision highp float;
uniform vec3 uLeaf; uniform vec3 uBud; uniform vec3 uRim;
varying vec3 vN; varying vec3 vView; varying float vPhase; varying float vAlong;
void main(){
  vec3 n = normalize(vN); vec3 v = normalize(vView);
  float facing = abs(dot(n, v));
  float fres = pow(1. - facing, 2.);
  vec3 base = mix(uLeaf, uBud, vPhase*vPhase*.7);
  base *= .55 + .45*vAlong;
  vec3 c = base*(.3 + .5*facing) + uRim*fres*.5;
  gl_FragColor = vec4(c, 1.); }`

const budVertex = `attribute float depth; attribute float phase;
uniform float uProgress; uniform float uTime; uniform float uDpr; uniform float uLeafSize;
varying float vA; varying float vPhase;
${RAMP}
void main(){
  float g = ramp(uProgress*1.35 - depth);
  vec4 mv = modelViewMatrix*vec4(position,1.);
  float tw = .7 + .3*sin(uTime*1.3 + phase*6.28);
  gl_PointSize = uLeafSize*(3.2 + 3.4*g)*tw*uDpr*(6./max(2., -mv.z));
  vA = g*tw;
  vPhase = phase;
  gl_Position = projectionMatrix*mv; }`

const budFragment = `precision highp float;
uniform vec3 uBud; uniform vec3 uLeaf;
varying float vA; varying float vPhase;
void main(){
  vec2 p = gl_PointCoord*2.-1.; float d = dot(p,p); if (d > 1.) discard;
  vec3 c = mix(uLeaf, uBud, vPhase*vPhase);
  float a = vA*(1.-d)*.6;
  gl_FragColor = vec4(c*a, a); }`

export type GroveHandle = { regenerate: (params: GroveParams) => void; setLook: (look: GroveLook) => void; replay: () => void; destroy: () => void }

export function mountGrove(canvas: HTMLCanvasElement, params: GroveParams, look: GroveLook): GroveHandle {
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true })
  const scene = new Scene()
  scene.fog = new FogExp2(new Color('#0a0a0c').getHex(), 0.055)
  const camera = new PerspectiveCamera(46, 1, 0.1, 120)
  camera.position.set(0, 2.4, 7.5)
  const controls = new OrbitControls(camera, canvas)
  controls.target.set(0, 1.4, 0)
  controls.enableDamping = true
  controls.maxPolarAngle = Math.PI * 0.55

  const uniforms = { uProgress: { value: 0 }, uTime: { value: 0 }, uDpr: { value: Math.min(devicePixelRatio || 1, 2) }, uLeafSize: { value: params.leafSize }, uBase: { value: new Color('#4a4438') }, uRim: { value: new Color('#8fb8a8') }, uBud: { value: new Color('#e3d2a4') }, uLeaf: { value: new Color('#7fae7f') } }
  const tubeMaterial = new ShaderMaterial({ vertexShader: tubeVertex, fragmentShader: tubeFragment, uniforms, side: DoubleSide })
  const leafMaterial = new ShaderMaterial({ vertexShader: leafVertex, fragmentShader: leafFragment, uniforms, side: DoubleSide })
  const leafGeometry = buildLeafGeometry(DEFAULT_LEAF)
  const lineMaterial = new ShaderMaterial({ vertexShader: lineVertex, fragmentShader: lineFragment, uniforms, transparent: true, blending: AdditiveBlending, depthWrite: false })
  const budMaterial = new ShaderMaterial({ vertexShader: budVertex, fragmentShader: budFragment, uniforms, transparent: true, blending: AdditiveBlending, depthWrite: false })

  const ground = new Mesh(new CircleGeometry(9, 48).rotateX(-Math.PI / 2), new MeshBasicMaterial({ color: new Color('#101012'), transparent: true, opacity: 0.55 }))
  scene.add(ground)

  let grown: Array<Mesh | LineSegments | Points> = []
  let currentLook = look
  let progressTarget = 1
  let growSeconds = params.growSeconds
  let lastParams = params

  const clear = () => { for (const object of grown) { object.geometry.dispose(); scene.remove(object) } grown = [] }

  const plant = (next: GroveParams) => {
    clear()
    lastParams = next
    growSeconds = next.growSeconds
    uniforms.uLeafSize.value = next.leafSize
    const rand = rng(next.seed)
    const spread = Math.max(1, next.trees - 1) * next.reach * 0.75
    for (let t = 0; t < next.trees; t++) {
      const origin = new Vector3(next.trees === 1 ? 0 : -spread / 2 + (t / Math.max(1, next.trees - 1)) * spread, 0, next.trees === 1 ? 0 : (rand() - 0.5) * next.reach)
      const tree = buildTreeGeometry(next, generateTree(next, rand, origin))
      const tube = new BufferGeometry()
      tube.setAttribute('position', new BufferAttribute(tree.position, 3))
      tube.setAttribute('roff', new BufferAttribute(tree.roff, 3))
      tube.setAttribute('depth', new BufferAttribute(tree.depth, 1))
      tube.setIndex(new BufferAttribute(tree.index, 1))
      grown.push(new Mesh(tube, tubeMaterial))
      const lines = new BufferGeometry()
      lines.setAttribute('position', new BufferAttribute(tree.linePosition, 3))
      lines.setAttribute('depth', new BufferAttribute(tree.lineDepth, 1))
      grown.push(new LineSegments(lines, lineMaterial))
      // foliage: crafted leaf cards instanced at every canopy site, oriented
      // by the site's branch frame; tubes/wires keep single bud points at tips
      if (currentLookIsFoliage()) {
        const perSite = Math.max(1, Math.round(next.leafDensity / 12))
        const count = tree.leafSites.length * perSite
        const leaves = new InstancedMesh(leafGeometry, leafMaterial, count)
        leaves.instanceMatrix.setUsage(DynamicDrawUsage)
        const iDepth = new Float32Array(count)
        const iPhase = new Float32Array(count)
        const matrix = new Matrix4()
        let n = 0
        for (const site of tree.leafSites) {
          for (let i = 0; i < perSite; i++) {
            const spin = rand() * Math.PI * 2
            const pitch = 0.35 + rand() * 0.75 // feather outward-and-along
            const { xAxis, yAxis, zAxis } = leafBasis(site.tangent, site.normal, spin, pitch)
            const seat = site.position.clone().add(yAxis.clone().multiplyScalar(site.radius * 0.8))
            const scale = next.leafSize * (0.55 + rand() * 0.75) * (0.6 + 0.4 * site.depth)
            matrix.makeBasis(xAxis.multiplyScalar(scale), yAxis.multiplyScalar(scale), zAxis.multiplyScalar(scale)).setPosition(seat)
            leaves.setMatrixAt(n, matrix)
            iDepth[n] = Math.min(1, site.depth + rand() * 0.08)
            iPhase[n] = rand()
            n++
          }
        }
        leaves.geometry = leafGeometry.clone()
        leaves.geometry.setAttribute('iDepth', new InstancedBufferAttribute(iDepth, 1))
        leaves.geometry.setAttribute('iPhase', new InstancedBufferAttribute(iPhase, 1))
        grown.push(leaves)
      } else {
        const budPos: number[] = []; const budDepth: number[] = []; const budPhase: number[] = []
        for (const tip of tree.tips) { budPos.push(tip.position.x, tip.position.y, tip.position.z); budDepth.push(tip.depth); budPhase.push(rand()) }
        const buds = new BufferGeometry()
        buds.setAttribute('position', new BufferAttribute(new Float32Array(budPos), 3))
        buds.setAttribute('depth', new BufferAttribute(new Float32Array(budDepth), 1))
        buds.setAttribute('phase', new BufferAttribute(new Float32Array(budPhase), 1))
        grown.push(new Points(buds, budMaterial))
      }
    }
    for (const object of grown) scene.add(object)
    applyLook()
    uniforms.uProgress.value = 0
    progressTarget = 1
  }

  const currentLookIsFoliage = () => currentLook === 'foliage'
  const applyLook = () => {
    grown.forEach((object) => {
      if (object instanceof Mesh) object.visible = currentLook !== 'wires'
      if (object instanceof LineSegments) object.visible = currentLook === 'wires'
    })
  }

  let frame = 0
  let last = 0
  const resize = () => { const w = canvas.clientWidth || innerWidth; const h = canvas.clientHeight || innerHeight; renderer.setSize(w, h, false); renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2)); camera.aspect = w / h; camera.updateProjectionMatrix() }
  const render = (now = 0) => {
    const dt = last ? Math.min(0.05, (now - last) / 1000) : 0.016
    last = now
    uniforms.uTime.value += dt
    if (uniforms.uProgress.value < progressTarget) uniforms.uProgress.value = Math.min(progressTarget, uniforms.uProgress.value + dt / Math.max(0.5, growSeconds))
    controls.update()
    renderer.render(scene, camera)
    frame = requestAnimationFrame(render)
  }
  resize()
  addEventListener('resize', resize)
  plant(params)
  render()

  return {
    regenerate: (next) => plant(next),
    setLook: (next) => { const rebuild = (next === 'foliage') !== currentLookIsFoliage(); currentLook = next; if (rebuild) plant({ ...lastParams, growSeconds: 0.5 }); else applyLook() },
    replay: () => { uniforms.uProgress.value = 0 },
    destroy: () => { cancelAnimationFrame(frame); removeEventListener('resize', resize); clear(); controls.dispose(); ground.geometry.dispose(); renderer.dispose() },
  }
}
