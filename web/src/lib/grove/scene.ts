// PROTOTYPE (grove workshop) - throwaway until a look wins a real spec.
// Three.js scene hosting the Ballot trees: fresnel-rimmed tube shader with the
// clamped-cosine growth ramp (depth as phase) and a uTime pulse, plus the
// wireframe and foliage looks over the same generated geometry.
import { AdditiveBlending, BufferAttribute, BufferGeometry, CircleGeometry, Color, DoubleSide, FogExp2, LineSegments, Mesh, MeshBasicMaterial, PerspectiveCamera, Points, Scene, ShaderMaterial, Vector3, WebGLRenderer } from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
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

const budVertex = `attribute float depth; attribute float phase;
uniform float uProgress; uniform float uTime; uniform float uDpr;
varying float vA;
${RAMP}
void main(){
  float g = ramp(uProgress*1.35 - depth);
  vec4 mv = modelViewMatrix*vec4(position,1.);
  float tw = .75 + .25*sin(uTime*2.1 + phase*6.28);
  gl_PointSize = (2.4 + 2.6*g)*tw*uDpr;
  vA = g*tw;
  gl_Position = projectionMatrix*mv; }`

const budFragment = `precision highp float;
uniform vec3 uBud;
varying float vA;
void main(){
  vec2 p = gl_PointCoord*2.-1.; float d = dot(p,p); if (d > 1.) discard;
  float a = vA*(1.-d);
  gl_FragColor = vec4(uBud*a, a); }`

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

  const uniforms = { uProgress: { value: 0 }, uTime: { value: 0 }, uDpr: { value: Math.min(devicePixelRatio || 1, 2) }, uBase: { value: new Color('#4a4438') }, uRim: { value: new Color('#8fb8a8') }, uBud: { value: new Color('#d9c9a0') } }
  const tubeMaterial = new ShaderMaterial({ vertexShader: tubeVertex, fragmentShader: tubeFragment, uniforms, side: DoubleSide })
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
      // buds at every leaf tip; the foliage look thickens each tip into a cluster
      const budPos: number[] = []; const budDepth: number[] = []; const budPhase: number[] = []
      for (const tip of tree.tips) {
        const cluster = currentLookIsFoliage() ? 26 : 1
        for (let i = 0; i < cluster; i++) {
          const jitter = cluster === 1 ? new Vector3() : new Vector3(rand() - 0.5, rand() - 0.5, rand() - 0.5).multiplyScalar(next.stepScale * 0.9)
          budPos.push(tip.position.x + jitter.x, tip.position.y + jitter.y, tip.position.z + jitter.z)
          budDepth.push(tip.depth)
          budPhase.push(rand())
        }
      }
      const buds = new BufferGeometry()
      buds.setAttribute('position', new BufferAttribute(new Float32Array(budPos), 3))
      buds.setAttribute('depth', new BufferAttribute(new Float32Array(budDepth), 1))
      buds.setAttribute('phase', new BufferAttribute(new Float32Array(budPhase), 1))
      grown.push(new Points(buds, budMaterial))
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
