import type { MapData, MapPoint, MapTerrain } from '../api/map'
import { aggFactor, groupStats, pointDomain, pointGroup, subCells } from './mapAggregation'
import type { SubCell } from './mapAggregation'
import { DIM, focusLevel, groupTargets, pointPhases, ramp as ease } from './mapGroups'
import type { MapFocus } from './mapGroups'
import { decay, pushSample, releaseVelocity } from './mapInertia'
import type { VelocitySample } from './mapInertia'

export type MapHover = { point: MapPoint; x: number; y: number }
export type MapRenderer = { setView: (view: 'all' | 'content') => void; setDimension: (flat: boolean) => void; setFilters: (signal: boolean, recent: boolean) => void; setFocus: (focus: MapFocus) => void; setHover: (hover?: MapFocus) => void; setHiddenDomains: (doms: Set<number>) => void; setLegendOpen: (open: boolean) => void; setTerrain: (on: boolean) => void; destroy: () => void }

// Both layouts ride in the buffer: p0/p1 are the 3D everything/content
// positions, q0/q1 the dedicated 2D embeddings. The morph uniform blends
// everything<->content, the dim uniform blends flat<->volume. Focus and
// hover dimming live in per-group uniform arrays (focDom/focSub A->B pairs)
// swept by a growth ramp phased from cluster centers, so focus changes are
// pure uniform animation over a static buffer too.
const vertex = `attribute vec3 p0; attribute vec3 p1; attribute vec2 q0; attribute vec2 q1;
attribute vec3 color0; attribute vec3 color1; attribute vec3 colorSub;
attribute float alpha0; attribute float alpha1; attribute float size;
attribute float grp; attribute float dm; attribute float phase;
uniform float morph; uniform float dim; uniform float zoom; uniform vec2 pan;
uniform float theta; uniform float phi; uniform float dpr;
uniform float aggDom[32]; uniform float aggSub[96];
uniform float focDomA[32]; uniform float focDomB[32];
uniform float focSubA[96]; uniform float focSubB[96];
uniform float focusT; uniform float level; uniform float subColorT;
uniform float introT; uniform float time;
varying vec3 c; varying float a; varying float depthV;
float rampf(float p){ return .5 - .5*cos(clamp(p,0.,1.)*3.14159265); }
void main(){
  vec3 p3=mix(p0,p1,morph); vec2 p2=mix(q0,q1,morph); vec3 q=mix(vec3(p2,0.),p3,dim);
  float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi);
  q=vec3(ct*q.x+st*q.z,sp*(st*q.x-ct*q.z)+cp*q.y,-cp*(st*q.x-ct*q.z)+sp*q.y);
  float depth=1.35-q.z*.24; depthV=q.z;
  gl_Position=vec4(q.xy*.88*zoom/depth+pan,q.z*.12,1.);
  int di=int(dm+.5); int si=int(max(grp,0.)+.5);
  float r=rampf(focusT*1.6-phase*.6);
  float fa=grp<0. ? mix(focDomA[di],focDomB[di],r) : mix(focSubA[si],focSubB[si],r);
  float agg=grp<0. ? 1. : (level<.5 ? aggDom[di] : aggSub[si]);
  float grow=rampf(introT*1.8-phase*.8);
  gl_PointSize=clamp(size*zoom/depth*dpr,1.8,26.*dpr)*grow;
  c=mix(mix(color0,colorSub,subColorT),color1,morph);
  float pulse=1.+.12*sin(time*2.2-phase*5.)*step(1.5,level+focusT);
  a=mix(alpha0,alpha1,morph)*fa*agg*grow*pulse; }`
const fragment = `precision mediump float; varying vec3 c; varying float a; varying float depthV;
void main(){ vec2 p=gl_PointCoord*2.-1.; float d2=dot(p,p); float edge=smoothstep(1.,.82,sqrt(d2)); if(edge<=0.) discard;
 float z=sqrt(max(0.,1.-d2)); vec3 n=vec3(p.x,-p.y,z); vec3 light=normalize(vec3(-.45,.55,.72));
 float wrap=(dot(n,light)+.6)/1.6; float diff=.35+.65*clamp(wrap,0.,1.);
 float spec=pow(max(dot(reflect(-light,n),vec3(0.,0.,1.)),0.),12.)*.10;
 float rim=pow(1.-z,2.5)*.35;
 vec3 shaded=c*diff*(.75+.25*z)+vec3(spec)+c*rim;
 float fog=smoothstep(-1.2,1.,depthV)*.35+.65;
 float alpha=a*edge*fog; gl_FragColor=vec4(shaded*alpha,alpha); }`
// Density-terrain overlay: contour + ridge polylines live in the 2D layout
// plane (z=0) and ride the same camera transform as the points. The terrain
// describes the dedicated 2D embedding only, so it fades out with dim (the
// 3D positions are a different embedding) and crossfades across view morphs.
const lineVertex = `attribute vec2 pos; attribute float alpha;
uniform float zoom; uniform vec2 pan; uniform float theta; uniform float phi;
varying float a;
void main(){ vec3 q=vec3(pos,0.);
 float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi);
 q=vec3(ct*q.x+st*q.z,sp*(st*q.x-ct*q.z)+cp*q.y,-cp*(st*q.x-ct*q.z)+sp*q.y);
 float depth=1.35-q.z*.24;
 gl_Position=vec4(q.xy*.88*zoom/depth+pan,q.z*.12,1.); a=alpha; }`
const lineFragment = `precision mediump float; uniform vec3 col; uniform float master; varying float a;
void main(){ float al=a*master; gl_FragColor=vec4(col*al,al); }`
const CONTOUR_COL: [number, number, number] = [1, 1, 1]
const RIDGE_COL: [number, number, number] = [.886, .69, .29] // hub gold

const ramp = ['#5b7cfa', '#2fb7c9', '#43c26a', '#d9a520', '#e8703a', '#e0507e', '#9d6bf0']
const gray: [number, number, number] = [.435, .427, .4]
const rgb = (hex: string): [number, number, number] => [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255) as [number, number, number]
function rampColor(value: number): [number, number, number] { const x = Math.max(0, Math.min(.9999, value)) * (ramp.length - 1); const i = Math.floor(x); const f = x - i; const a = rgb(ramp[i]); const b = rgb(ramp[i + 1]); return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f] }
const css = (color: [number, number, number]) => `rgb(${color.map((channel) => Math.round(channel * 255)).join(', ')})`
// Ramp position of a domain (by size rank) and of a subtopic (its domain's
// position hue-shifted across +-0.08 by index-within-domain) — the single
// source of truth for both the vertex buffer and the legend swatches.
function domainPos(data: MapData, index: number): number { const order = data.all.domains.map((domain, i) => ({ i, n: domain.n })).sort((a, b) => b.n - a.n); const rank = order.findIndex((item) => item.i === index); return Math.max(0, rank) / Math.max(1, order.length - 1) }
function subPos(data: MapData, index: number): number { const domain = data.all.groups[index]?.domain ?? -1; const siblings = data.all.groups.flatMap((group, i) => group.domain === domain ? [i] : []); const k = siblings.indexOf(index); const spread = siblings.length > 1 ? (k / (siblings.length - 1) - .5) * .16 : 0; return Math.max(0, Math.min(.9999, domainPos(data, domain) + spread)) }
export function mapDomainColor(data: MapData, index: number): string { return css(rampColor(domainPos(data, index))) }
export function mapSubColor(data: MapData, index: number): string { return css(rampColor(subPos(data, index))) }
export function mapGroupColor(data: MapData, view: 'all' | 'content', index: number): string { return view === 'content' ? css(rampColor(index / 7)) : mapSubColor(data, index) }

function shader(gl: WebGLRenderingContext, type: number, source: string) {
  const value = gl.createShader(type)!
  gl.shaderSource(value, source)
  gl.compileShader(value)
  if (!gl.getShaderParameter(value, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(value) || 'shader compilation failed')
  return value
}

// One intro per SPA session: remounting the route replays instantly.
let introPlayed = false

type RenderedPoint = { point: MapPoint; p3a: number[]; p3b: number[]; p2a: number[]; p2b: number[]; group: number; domain: number }

export function mountMapRenderer(canvas: HTMLCanvasElement, data: MapData, onHover?: (hover?: MapHover) => void, labels?: HTMLElement, onFocus?: (focus: MapFocus) => void, leaders?: SVGSVGElement, opts?: { intro?: boolean }): MapRenderer {
  const gl = canvas.getContext('webgl', { antialias: false, alpha: true, premultipliedAlpha: true })
  if (!gl) throw new Error('WebGL is unavailable in this browser')
  if ((gl.getParameter(gl.MAX_VERTEX_UNIFORM_VECTORS) as number) < 512) console.warn('map: vertex uniform budget below 512 vectors, focus arrays may not fit')
  const program = gl.createProgram()!
  gl.attachShader(program, shader(gl, gl.VERTEX_SHADER, vertex))
  gl.attachShader(program, shader(gl, gl.FRAGMENT_SHADER, fragment))
  gl.linkProgram(program)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || 'program link failed')
  gl.useProgram(program)
  gl.enable(gl.BLEND)
  gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
  const buffer = gl.createBuffer()!
  const orbBuffer = gl.createBuffer()!
  // --- terrain overlay resources (absent on pre-terrain map.json builds)
  let lineProgram: WebGLProgram | undefined
  let lineU: Record<'zoom' | 'pan' | 'theta' | 'phi' | 'col' | 'master', WebGLUniformLocation | null> | undefined
  let linePos = 0
  let lineAlpha = 0
  type TerrainBuffers = { contours: WebGLBuffer; contourCount: number; ridges: WebGLBuffer; ridgeCount: number }
  const terrainBuffers: Partial<Record<'all' | 'content', TerrainBuffers>> = {}
  if (data.all.terrain || data.content.terrain) {
    lineProgram = gl.createProgram()!
    gl.attachShader(lineProgram, shader(gl, gl.VERTEX_SHADER, lineVertex))
    gl.attachShader(lineProgram, shader(gl, gl.FRAGMENT_SHADER, lineFragment))
    gl.linkProgram(lineProgram)
    if (!gl.getProgramParameter(lineProgram, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(lineProgram) || 'terrain program link failed')
    linePos = gl.getAttribLocation(lineProgram, 'pos')
    lineAlpha = gl.getAttribLocation(lineProgram, 'alpha')
    lineU = { zoom: gl.getUniformLocation(lineProgram, 'zoom'), pan: gl.getUniformLocation(lineProgram, 'pan'), theta: gl.getUniformLocation(lineProgram, 'theta'), phi: gl.getUniformLocation(lineProgram, 'phi'), col: gl.getUniformLocation(lineProgram, 'col'), master: gl.getUniformLocation(lineProgram, 'master') }
    const upload = (segments: number[]) => { const buf = gl.createBuffer()!; gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(segments), gl.STATIC_DRAW); return buf }
    const build = (terrain: MapTerrain | undefined, key: 'all' | 'content') => {
      if (!terrain) return
      // GL_LINES pairs; per-vertex alpha bakes the contour level so one draw
      // call renders the whole nest (deeper level = brighter line).
      const contours: number[] = []
      for (const c of terrain.contours) for (let i = 0; i + 1 < c.path.length; i++) { const a = .05 + c.lv * .022; contours.push(c.path[i][0], c.path[i][1], a, c.path[i + 1][0], c.path[i + 1][1], a) }
      const ridges: number[] = []
      for (const r of terrain.ridges) for (let i = 0; i + 1 < r.length; i++) ridges.push(r[i][0], r[i][1], 1, r[i + 1][0], r[i + 1][1], 1)
      terrainBuffers[key] = { contours: upload(contours), contourCount: contours.length / 3, ridges: upload(ridges), ridgeCount: ridges.length / 3 }
    }
    build(data.all.terrain, 'all')
    build(data.content.terrain, 'content')
  }
  const position0 = gl.getAttribLocation(program, 'p0')
  const position1 = gl.getAttribLocation(program, 'p1')
  const flat0 = gl.getAttribLocation(program, 'q0')
  const flat1 = gl.getAttribLocation(program, 'q1')
  const color0 = gl.getAttribLocation(program, 'color0')
  const color1 = gl.getAttribLocation(program, 'color1')
  const colorSub = gl.getAttribLocation(program, 'colorSub')
  const alpha0 = gl.getAttribLocation(program, 'alpha0')
  const alpha1 = gl.getAttribLocation(program, 'alpha1')
  const size = gl.getAttribLocation(program, 'size')
  const grp = gl.getAttribLocation(program, 'grp')
  const dm = gl.getAttribLocation(program, 'dm')
  const phaseAttr = gl.getAttribLocation(program, 'phase')
  const aggDomU = gl.getUniformLocation(program, 'aggDom[0]')
  const aggSubU = gl.getUniformLocation(program, 'aggSub[0]')
  const focDomAU = gl.getUniformLocation(program, 'focDomA[0]')
  const focDomBU = gl.getUniformLocation(program, 'focDomB[0]')
  const focSubAU = gl.getUniformLocation(program, 'focSubA[0]')
  const focSubBU = gl.getUniformLocation(program, 'focSubB[0]')
  const focusTU = gl.getUniformLocation(program, 'focusT')
  const levelU = gl.getUniformLocation(program, 'level')
  const subColorTU = gl.getUniformLocation(program, 'subColorT')
  const introTU = gl.getUniformLocation(program, 'introT')
  const timeU = gl.getUniformLocation(program, 'time')
  const morphUniform = gl.getUniformLocation(program, 'morph')
  const dimUniform = gl.getUniformLocation(program, 'dim')
  const zoom = gl.getUniformLocation(program, 'zoom')
  const pan = gl.getUniformLocation(program, 'pan')
  const theta = gl.getUniformLocation(program, 'theta')
  const phi = gl.getUniformLocation(program, 'phi')
  const dpr = gl.getUniformLocation(program, 'dpr')
  let view: 'all' | 'content' = 'all'
  let frame = 0
  let scale = 1
  let scaleTarget = 1
  let flyItem: RenderedPoint | undefined
  let offset: [number, number] = [0, 0]
  let drag: { x: number; y: number } | undefined
  let moved = 0
  let orbit = false
  let samples: VelocitySample[] = []
  let momentum: { vx: number; vy: number } = { vx: 0, vy: 0 }
  const killMomentum = () => { momentum = { vx: 0, vy: 0 }; samples = [] }
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches
  let angle = .5
  let tilt = .3
  let signalOnly = false
  let recentOnly = false
  let geometryDirty = true
  let pointCount = 0
  let renderedPoints: RenderedPoint[] = []
  let hoveredPoint: MapPoint | undefined
  let labelsDirty = true
  let labelItems: Array<{ c3: number[]; c2: number[]; radius: number; node: HTMLDivElement; line?: SVGLineElement; rank: number; n: number }> = []
  let morph = location.hash === '#content' ? 1 : 0
  let morphTarget = morph
  let dimVal = location.hash === '#2d' ? 0 : 1
  let dimTarget = dimVal
  let legendOpen = true
  let focus: MapFocus = {}
  let hover: MapFocus | undefined
  let hiddenDoms = new Set<number>()
  const nDom = data.all.domains.length
  const nSub = data.all.groups.length
  if (nDom > 32 || nSub > 96) console.warn(`map: hierarchy exceeds shader capacity (${nDom} domains, ${nSub} subtopics)`)
  let focA: { dom: Float32Array; sub: Float32Array } = { dom: new Float32Array(nDom).fill(1), sub: new Float32Array(nSub).fill(1) }
  let focB: { dom: Float32Array; sub: Float32Array } = { dom: new Float32Array(nDom).fill(1), sub: new Float32Array(nSub).fill(1) }
  let focusT = 1
  let subColorT = 0
  let terrainOn = false
  let terrainT = 0
  const intro = (opts?.intro ?? false) && !introPlayed
  if (intro) { introPlayed = true; canvas.dataset.intro = '1' }
  let introT = intro ? 0 : 1
  const phases = pointPhases(data.points)
  const domPosArr = data.all.domains.map((_, index) => domainPos(data, index))
  const subPosArr = data.all.groups.map((_, index) => subPos(data, index))
  // Themes act as single-level domains in the content view; theme dims ride
  // both arrays because content points carry the theme in grp AND dm.
  // dom is sized by the all-view domain count: themes beyond nDom would be
  // silently truncated (8 themes vs 9 domains today - revisit if that flips).
  const contentTargets = () => {
    const n = data.content.groups.length
    const dom = new Float32Array(nDom).fill(1)
    const sub = new Float32Array(nSub).fill(1)
    for (let d = 0; d < n && d < nDom; d++) dom[d] = focus.dom === undefined || (hover?.dom ?? focus.dom) === d ? 1 : DIM
    if (hover?.dom !== undefined) for (let d = 0; d < n && d < nDom; d++) dom[d] = hover.dom === d ? 1 : DIM
    for (let d = 0; d < n && d < nSub; d++) sub[d] = dom[d]
    return { dom, sub }
  }
  const retarget = () => {
    // Freeze the currently displayed value as the new A so mid-flight
    // retargets do not jump: the per-point ramp is approximated with the
    // group-level ramp(focusT).
    const t = ease(Math.max(0, Math.min(1, focusT)))
    for (let i = 0; i < nDom; i++) focA.dom[i] = focA.dom[i] + (focB.dom[i] - focA.dom[i]) * t
    for (let i = 0; i < nSub; i++) focA.sub[i] = focA.sub[i] + (focB.sub[i] - focA.sub[i]) * t
    const view2 = view === 'content'
    focB = view2
      ? contentTargets()
      : groupTargets(nDom, data.all.groups, focus, hover, hiddenDoms)
    focusT = 0
  }
  const subCache: Record<string, SubCell[]> = {}

  const lerp3 = (a: number[], b: number[], t: number) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
  // flat<->volume blend of a morphed 3D position and its 2D counterpart
  const blend = (p3: number[], p2: number[]) => [p2[0] + (p3[0] - p2[0]) * dimVal, p2[1] + (p3[1] - p2[1]) * dimVal, p3[2] * dimVal]
  const morph3 = (item: RenderedPoint) => lerp3(item.p3a, item.p3b, morph)
  const morph2 = (item: RenderedPoint) => [item.p2a[0] + (item.p2b[0] - item.p2a[0]) * morph, item.p2a[1] + (item.p2b[1] - item.p2a[1]) * morph]
  const worldOf = (item: RenderedPoint) => blend(morph3(item), morph2(item))
  const project = (world: number[]) => { const [x, y, z] = world; const ea = angle * dimVal, et = tilt * dimVal; const ct = Math.cos(ea), st = Math.sin(ea), cp = Math.cos(et), sp = Math.sin(et); const rx = ct * x + st * z; const rz = -st * x + ct * z; const ry = sp * -rz + cp * y; const depth = 1.35 - (cp * rz + sp * y) * .24; return [(rx * .88 * scale / depth + offset[0] + 1) * canvas.clientWidth / 2, (1 - (ry * .88 * scale / depth + offset[1])) * canvas.clientHeight / 2, depth] }

  const resize = () => { const ratio = Math.min(devicePixelRatio || 1, 2); canvas.width = innerWidth * ratio; canvas.height = innerHeight * ratio; canvas.style.width = `${innerWidth}px`; canvas.style.height = `${innerHeight}px`; gl.viewport(0, 0, canvas.width, canvas.height) }
  const draw = (time: number) => {
    if (geometryDirty) {
      renderedPoints = []
      const points = data.points.flatMap((point, index) => {
      const p3a = point.z3
      const p3b = point.c3 ?? point.z3
      const p2a = [point.x, point.y]
      const p2b = [point.cx ?? point.x, point.cy ?? point.y]
      const days = point.d ? (Date.parse(document.lastModified) - Date.parse(point.d)) / 86_400_000 : Infinity
      const recency = recentOnly ? Math.max(.12, Math.pow(.5, Math.max(0, days) / 90)) : 1
      const sig = signalOnly && point.r < 1 ? .04 : recency
      const alphaFor = (base: number) => sig === .04 ? .04 : base * sig
      const domColor = point.dom >= 0 ? rampColor(domPosArr[point.dom] ?? 0) : gray
      const subColor = point.g >= 0 ? rampColor(subPosArr[point.g] ?? 0) : domColor
      const themeColor = point.th !== undefined && point.th >= 0 ? rampColor(point.th / 7) : gray
      const alpha0 = alphaFor(point.g < 0 ? .4 : 1)
      const alpha1 = alphaFor(point.c3 ? .95 : 0)
      const group = pointGroup(point, view)
      const domain = pointDomain(point, view)
      renderedPoints.push({ point, p3a, p3b, p2a, p2b, group, domain })
      return [...p3a, ...p3b, ...p2a, ...p2b, ...domColor, ...themeColor, ...subColor, alpha0, alpha1, 3.2 + point.r * 1.8 + (point.c3 ? .8 : 0), group, domain, phases[index]]
      })
      pointCount = points.length / 25
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.STATIC_DRAW)
      geometryDirty = false
    }
    const drawSet = (buf: WebGLBuffer, count: number) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buf)
      gl.enableVertexAttribArray(position0); gl.vertexAttribPointer(position0, 3, gl.FLOAT, false, 100, 0)
      gl.enableVertexAttribArray(position1); gl.vertexAttribPointer(position1, 3, gl.FLOAT, false, 100, 12)
      gl.enableVertexAttribArray(flat0); gl.vertexAttribPointer(flat0, 2, gl.FLOAT, false, 100, 24)
      gl.enableVertexAttribArray(flat1); gl.vertexAttribPointer(flat1, 2, gl.FLOAT, false, 100, 32)
      gl.enableVertexAttribArray(color0); gl.vertexAttribPointer(color0, 3, gl.FLOAT, false, 100, 40)
      gl.enableVertexAttribArray(color1); gl.vertexAttribPointer(color1, 3, gl.FLOAT, false, 100, 52)
      gl.enableVertexAttribArray(colorSub); gl.vertexAttribPointer(colorSub, 3, gl.FLOAT, false, 100, 64)
      gl.enableVertexAttribArray(alpha0); gl.vertexAttribPointer(alpha0, 1, gl.FLOAT, false, 100, 76)
      gl.enableVertexAttribArray(alpha1); gl.vertexAttribPointer(alpha1, 1, gl.FLOAT, false, 100, 80)
      gl.enableVertexAttribArray(size); gl.vertexAttribPointer(size, 1, gl.FLOAT, false, 100, 84)
      gl.enableVertexAttribArray(grp); gl.vertexAttribPointer(grp, 1, gl.FLOAT, false, 100, 88)
      gl.enableVertexAttribArray(dm); gl.vertexAttribPointer(dm, 1, gl.FLOAT, false, 100, 92)
      gl.enableVertexAttribArray(phaseAttr); gl.vertexAttribPointer(phaseAttr, 1, gl.FLOAT, false, 100, 96)
      gl.drawArrays(gl.POINTS, 0, count)
    }
    // adaptive aggregation: while a domain is small on screen its points fade
    // out (aggDom/aggSub) and it condenses into one orb per spatial sub-cell;
    // zooming in dissolves the orbs back into points. Points key on domains
    // at overview and on subtopics while a domain is focused.
    const contentView = view === 'content'
    const level = !contentView && focusLevel(focus) !== 'overview' ? 1 : 0
    const m3s: number[][] = []
    const m2s: number[][] = []
    const worlds: number[][] = []
    for (const item of renderedPoints) { const m3 = morph3(item); const m2 = morph2(item); m3s.push(m3); m2s.push(m2); worlds.push(blend(m3, m2)) }
    const ea = angle * dimVal
    const right = [Math.cos(ea), 0, Math.sin(ea)]
    const aggDomArr = new Float32Array(32).fill(1)
    const aggSubArr = new Float32Array(96).fill(1)
    const aggOf = (s: { n: number; centroid: [number, number, number]; radius: number }) => { if (!s.n) return 1; const [x0] = project(s.centroid); const [xr] = project([s.centroid[0] + s.radius * right[0], s.centroid[1] + s.radius * right[1], s.centroid[2] + s.radius * right[2]]); return aggFactor(Math.abs(xr - x0)) }
    const domAggT = groupStats(worlds, renderedPoints.map((item) => item.domain), contentView ? data.content.groups.length : nDom).map(aggOf)
    domAggT.forEach((t, g) => { if (g < 32) aggDomArr[g] = t; if (contentView && g < 96) aggSubArr[g] = t })
    if (!contentView) groupStats(worlds, renderedPoints.map((item) => item.group), nSub).map(aggOf).forEach((t, g) => { if (g < 96) aggSubArr[g] = t })
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    // terrain underlay: drawn before the points, faded by dim (it describes
    // the 2D layout only) and crossfaded between the two views' layouts
    if (lineProgram && lineU && terrainT > .01 && dimVal < .99) {
      gl.useProgram(lineProgram)
      gl.uniform1f(lineU.zoom, scale)
      gl.uniform2f(lineU.pan, offset[0], offset[1])
      gl.uniform1f(lineU.theta, ea)
      gl.uniform1f(lineU.phi, tilt * dimVal)
      for (const key of ['all', 'content'] as const) {
        const weight = key === 'all' ? 1 - morph : morph
        const bufs = terrainBuffers[key]
        if (!bufs || weight <= .01) continue
        const master = terrainT * (1 - dimVal) * weight
        const drawLines = (buf: WebGLBuffer, count: number, col: [number, number, number], mult: number) => {
          if (!count) return
          gl.bindBuffer(gl.ARRAY_BUFFER, buf)
          gl.enableVertexAttribArray(linePos); gl.vertexAttribPointer(linePos, 2, gl.FLOAT, false, 12, 0)
          gl.enableVertexAttribArray(lineAlpha); gl.vertexAttribPointer(lineAlpha, 1, gl.FLOAT, false, 12, 8)
          gl.uniform3f(lineU!.col, col[0], col[1], col[2])
          gl.uniform1f(lineU!.master, master * mult)
          gl.drawArrays(gl.LINES, 0, count)
        }
        drawLines(bufs.contours, bufs.contourCount, CONTOUR_COL, .9)
        drawLines(bufs.ridges, bufs.ridgeCount, RIDGE_COL, .42)
      }
      gl.useProgram(program)
    }
    gl.uniform1f(morphUniform, morph)
    gl.uniform1f(dimUniform, dimVal)
    gl.uniform1f(zoom, scale)
    gl.uniform2f(pan, offset[0], offset[1])
    gl.uniform1f(theta, ea)
    gl.uniform1f(phi, tilt * dimVal)
    gl.uniform1f(dpr, Math.min(devicePixelRatio || 1, 2))
    gl.uniform1fv(aggDomU, aggDomArr)
    gl.uniform1fv(aggSubU, aggSubArr)
    gl.uniform1fv(focDomAU, focA.dom)
    gl.uniform1fv(focDomBU, focB.dom)
    gl.uniform1fv(focSubAU, focA.sub)
    gl.uniform1fv(focSubBU, focB.sub)
    gl.uniform1f(focusTU, focusT)
    gl.uniform1f(levelU, level)
    gl.uniform1f(subColorTU, subColorT)
    gl.uniform1f(introTU, introT)
    gl.uniform1f(timeU, time)
    drawSet(buffer, pointCount)
    const orbs: number[] = []
    for (const sub of (subCache[view] ??= subCells(data.points, view))) {
      // orbs carry grp=-1 / dm=group so the shader applies focus dimming for
      // them too; only the aggregation factor is baked per frame.
      const orbA = 1 - (domAggT[sub.group] ?? 1)
      if (orbA < .02) continue
      let x = 0, y = 0, z = 0, fx = 0, fy = 0
      for (const i of sub.indices) { x += m3s[i][0]; y += m3s[i][1]; z += m3s[i][2]; fx += m2s[i][0]; fy += m2s[i][1] }
      const m = sub.indices.length; x /= m; y /= m; z /= m; fx /= m; fy /= m
      const col = contentView ? rampColor(sub.group / 7) : rampColor(domPosArr[sub.group] ?? 0)
      orbs.push(x, y, z, x, y, z, fx, fy, fx, fy, ...col, ...col, ...col, orbA * .95, orbA * .95, 4.5 + Math.sqrt(m) * 1.5, -1, sub.group, 0)
    }
    if (orbs.length) { gl.bindBuffer(gl.ARRAY_BUFFER, orbBuffer); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(orbs), gl.DYNAMIC_DRAW); drawSet(orbBuffer, orbs.length / 25) }
  }
  let lastFrame = 0
  const render = (now = 0) => {
    const dt = lastFrame ? Math.min(.05, (now - lastFrame) / 1000) : .016; lastFrame = now
    const dm2 = morphTarget - morph; morph = Math.abs(dm2) <= 1e-3 ? morphTarget : morph + dm2 * (1 - Math.exp(-5 * dt))
    const dd = dimTarget - dimVal; dimVal = Math.abs(dd) <= 1e-3 ? dimTarget : dimVal + dd * (1 - Math.exp(-5 * dt))
    // wheel glide: ease scale to its target, holding the anchor point fixed
    if (!flyItem && zoomAnchor && Math.abs(scaleTarget - scale) > 1e-3) {
      const previous = scale
      scale += (scaleTarget - scale) * (1 - Math.exp(-10 * dt))
      const ratio = scale / previous
      offset = [zoomAnchor[0] - (zoomAnchor[0] - offset[0]) * ratio, zoomAnchor[1] - (zoomAnchor[1] - offset[1]) * ratio]
    } else if (zoomAnchor && Math.abs(scaleTarget - scale) <= 1e-3) { scale = scaleTarget; zoomAnchor = null }
    // pan coast: integrate momentum with exponential decay to a soft stop
    if (!drag && (momentum.vx || momentum.vy)) {
      offset = [offset[0] + momentum.vx * dt, offset[1] + momentum.vy * dt]
      momentum = { vx: decay(momentum.vx, dt), vy: decay(momentum.vy, dt) }
      if (Math.hypot(momentum.vx, momentum.vy) < 0.005) killMomentum()
    }
    focusT = Math.min(1, focusT + dt / .9)
    introT = Math.min(1, introT + dt / 1.5)
    if (introT >= 1 && canvas.dataset.intro) delete canvas.dataset.intro
    const subColorTarget = view === 'all' && focus.dom !== undefined ? 1 : 0
    const ds = subColorTarget - subColorT; subColorT = Math.abs(ds) <= 1e-3 ? subColorTarget : subColorT + ds * (1 - Math.exp(-4 * dt))
    const terrainTarget = terrainOn ? 1 : 0
    const dte = terrainTarget - terrainT; terrainT = Math.abs(dte) <= 1e-3 ? terrainTarget : terrainT + dte * (1 - Math.exp(-4 * dt))
    if (flyItem) {
      const e = 1 - Math.exp(-8 * dt)
      scale += (scaleTarget - scale) * e
      const [sx, sy] = project(worldOf(flyItem))
      const ox = offset[0] - (2 * sx / canvas.clientWidth - 1); const oy = offset[1] + (2 * sy / canvas.clientHeight - 1)
      offset = [offset[0] + (ox - offset[0]) * e, offset[1] + (oy - offset[1]) * e]
      if (Math.abs(scaleTarget - scale) < 1e-3 && Math.abs(ox - offset[0]) < 1e-3 && Math.abs(oy - offset[1]) < 1e-3) { scale = scaleTarget; flyItem = undefined }
    }
    draw(now * .001); placeLabels(); frame = requestAnimationFrame(render)
  }
  const placeLabels = () => {
    if (!labels) return
    if (labelsDirty) {
      // Hierarchy-aware label sets: content themes; all-view domains at
      // overview; a focused domain's subtopics; the focused subtopic alone.
      const contentView = view === 'content'
      const entries = contentView
        ? data.content.groups.map((group, key) => ({ key, label: group.label, n: group.n, focus: { dom: key } as MapFocus })).filter((entry) => focus.dom === undefined || focus.dom === entry.key)
        : focus.dom === undefined
          ? data.all.domains.map((domain, key) => ({ key, label: domain.label, n: domain.n, focus: { dom: key } as MapFocus })).filter((entry) => !hiddenDoms.has(entry.key))
          : data.all.groups.map((group, key) => ({ key, label: group.label, n: group.n, focus: { dom: group.domain ?? -1, sub: key } as MapFocus })).filter((entry) => entry.focus.dom === focus.dom && (focus.sub === undefined || focus.sub === entry.key))
      const groupOf = !contentView && focus.dom === undefined ? (item: RenderedPoint) => item.domain : (item: RenderedPoint) => item.group
      const buckets = new Map<number, { x: number; y: number; z: number; fx: number; fy: number; n: number; points: number[][] }>()
      for (const entry of entries) buckets.set(entry.key, { x: 0, y: 0, z: 0, fx: 0, fy: 0, n: 0, points: [] })
      for (const item of renderedPoints) { const bucket = buckets.get(groupOf(item)); if (!bucket) continue; const s3 = contentView ? item.p3b : item.p3a; const s2 = contentView ? item.p2b : item.p2a; bucket.x += s3[0]; bucket.y += s3[1]; bucket.z += s3[2]; bucket.fx += s2[0]; bucket.fy += s2[1]; bucket.n++; bucket.points.push(s3) }
      labels.replaceChildren(); leaders?.replaceChildren()
      const single = contentView ? focus.dom !== undefined : focus.sub !== undefined
      labelItems = entries.filter((entry) => entry.n && buckets.get(entry.key)!.n).sort((a, b) => b.n - a.n).slice(0, single ? 1 : 10).map((entry, rank) => { const bucket = buckets.get(entry.key)!; const c3 = [bucket.x / bucket.n, bucket.y / bucket.n, bucket.z / bucket.n]; const c2 = [bucket.fx / bucket.n, bucket.fy / bucket.n]; const radius = Math.sqrt(Math.max(0, ...bucket.points.map((point) => (point[0] - c3[0]) ** 2 + (point[1] - c3[1]) ** 2 + (point[2] - c3[2]) ** 2))); const node = document.createElement('div'); node.className = 'map-label'; node.textContent = entry.label; node.style.fontSize = `${Math.max(10, Math.min(14, 9 + Math.sqrt(entry.n) * .25))}px`; node.style.pointerEvents = 'auto'; node.style.cursor = 'pointer'; node.onclick = () => { onFocus?.(entry.focus) }; labels.appendChild(node); const line = leaders ? document.createElementNS('http://www.w3.org/2000/svg', 'line') : undefined; if (line) { line.setAttribute('stroke-width', '1'); leaders!.appendChild(line) } return { c3, c2, radius, node, line, rank, n: entry.n } })
      labelsDirty = false
    }
    const placed: Array<{ x: number; y: number; width: number }> = []
    for (const item of labelItems) { const [x, centerY, depth] = project(blend(item.c3, item.c2)); const spread = item.radius * scale * canvas.clientHeight * .25 / depth; let y = centerY - spread - 22; const width = (item.node.textContent?.length ?? 1) * parseFloat(item.node.style.fontSize) * .72; for (let i = 0; i < 10 && placed.some((other) => Math.abs(other.y - y) < 22 && Math.abs(other.x - x) < (other.width + width) / 2 + 10); i++) y -= 22; const visible = depth > 0 && x >= 0 && y >= 40 && x <= canvas.clientWidth - (legendOpen ? 290 : 70) && y <= canvas.clientHeight && !(item.rank >= 6 && spread < 70); item.node.style.display = visible ? 'block' : 'none'; if (item.line) item.line.style.display = 'none'; if (!visible) continue; y = Math.max(46, y); const size = parseFloat(item.node.style.fontSize); item.node.style.left = `${x}px`; item.node.style.top = `${y}px`; const alpha = item.rank < 6 ? .9 : Math.min(.9, (spread - 70) / 120 + .35); item.node.style.opacity = `${alpha}`; const gap = centerY - y - size; if (item.line && gap > 14) { item.line.style.display = 'block'; item.line.setAttribute('stroke', `rgba(255,255,255,${(.16 * alpha).toFixed(3)})`); item.line.setAttribute('x1', `${x}`); item.line.setAttribute('y1', `${centerY - Math.min(spread * .7, gap - 6)}`); item.line.setAttribute('x2', `${x}`); item.line.setAttribute('y2', `${y + size * .8}`) } placed.push({ x, y, width }) }
  }
  const pick = (event: MouseEvent) => { if (drag) return; const rect = canvas.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) { hoveredPoint = undefined; onHover?.(); return } let best: { point: MapPoint; distance: number } | undefined; for (const item of renderedPoints) { if (signalOnly && item.point.r < 1) continue; const target = item.group >= 0 ? focB.sub[item.group] : item.domain >= 0 ? focB.dom[item.domain] : 1; if ((target ?? 1) < .2) continue; const [x, y] = project(worldOf(item)); const distance = (x - (event.clientX - rect.left)) ** 2 + (y - (event.clientY - rect.top)) ** 2; if (distance < 144 && (!best || distance < best.distance)) best = { point: item.point, distance } } hoveredPoint = best?.point; onHover?.(best ? { point: best.point, x: event.clientX, y: event.clientY } : undefined) }
  const down = (event: MouseEvent) => { if (event.button !== 0 && event.button !== 2) return; event.preventDefault(); moved = 0; orbit = dimTarget === 1 && event.button === 0 && !event.shiftKey; drag = { x: event.clientX, y: event.clientY }; canvas.classList.add('dragging'); killMomentum(); samples = [{ x: event.clientX, y: event.clientY, t: performance.now() }] }
  const move = (event: MouseEvent) => { if (!drag) { pick(event); return } const dx = event.clientX - drag.x; const dy = event.clientY - drag.y; moved += Math.abs(dx) + Math.abs(dy); flyItem = undefined; scaleTarget = scale; momentum = { vx: 0, vy: 0 }; if (orbit) { angle -= dx * .005; tilt = Math.max(-1.35, Math.min(1.35, tilt + dy * .005)) } else { offset = [offset[0] + dx / innerWidth * 2, offset[1] - dy / innerHeight * 2]; pushSample(samples, { x: event.clientX, y: event.clientY, t: performance.now() }) } drag = { x: event.clientX, y: event.clientY }; onHover?.() }
  const up = () => {
    if (drag && !orbit && !reduceMotion) {
      const v = releaseVelocity(samples) // px/ms in screen space
      // convert to NDC offset units/second: offset spans 2 across the viewport
      momentum = { vx: v.vx * 1000 * 2 / innerWidth, vy: -v.vy * 1000 * 2 / innerHeight }
      if (Math.hypot(momentum.vx, momentum.vy) < 0.02) killMomentum()
    }
    samples = []
    drag = undefined; orbit = false; canvas.classList.remove('dragging')
  }
  // exact cursor-anchored zoom: screen = world*k*scale + pan, so holding the
  // cursor's NDC point fixed means pan' = c - (c - pan) * (scale'/scale)
  let zoomAnchor: [number, number] | null = null
  const wheel = (event: WheelEvent) => {
    event.preventDefault(); flyItem = undefined; killMomentum()
    const rect = canvas.getBoundingClientRect()
    zoomAnchor = [
      (event.clientX - rect.left) / rect.width * 2 - 1,
      1 - (event.clientY - rect.top) / rect.height * 2,
    ]
    scaleTarget = Math.max(.3, Math.min(12, (scaleTarget || scale) * Math.exp(-event.deltaY * .0012)))
    if (reduceMotion) {
      const ratio = scaleTarget / scale
      scale = scaleTarget
      offset = [zoomAnchor[0] - (zoomAnchor[0] - offset[0]) * ratio, zoomAnchor[1] - (zoomAnchor[1] - offset[1]) * ratio]
      zoomAnchor = null
    }
  }
  const contextmenu = (event: MouseEvent) => event.preventDefault()
  const open = () => { if (hoveredPoint?.u) window.open(hoveredPoint.u, '_blank', 'noopener') }
  const flyTo = (point: MapPoint) => { const item = renderedPoints.find((entry) => entry.point === point); if (item) { scaleTarget = Math.max(scale, 1.8); flyItem = item; killMomentum() } }
  // Drill-down: overview click focuses the point's domain; a second click
  // inside a focused domain focuses its subtopic (noise keeps domain focus);
  // clicking at subtopic depth or on empty space pops one level. The route
  // owns the focus state — the renderer only reports via onFocus.
  const click = () => { if (moved >= 4) return; if (!hoveredPoint) { flyItem = undefined; scaleTarget = scale; onFocus?.(focus.sub !== undefined ? { dom: focus.dom } : {}); return } if (view === 'content') { const th = hoveredPoint.th ?? -1; if (th < 0) return; flyTo(hoveredPoint); onFocus?.({ dom: th }); return } if (focus.dom === undefined) { onFocus?.({ dom: hoveredPoint.dom }); return } if (focus.sub === undefined) { const sub = hoveredPoint.g >= 0 ? hoveredPoint.g : undefined; if (sub !== undefined) flyTo(hoveredPoint); onFocus?.({ dom: focus.dom, sub }); return } onFocus?.({ dom: focus.dom }) }
  resize(); addEventListener('resize', resize); canvas.addEventListener('mousedown', down); canvas.addEventListener('click', click); canvas.addEventListener('dblclick', open); canvas.addEventListener('contextmenu', contextmenu); addEventListener('mousemove', move); addEventListener('mouseup', up); canvas.addEventListener('wheel', wheel, { passive: false }); render()
  return { setView: (next) => { view = next; morphTarget = next === 'content' ? 1 : 0; focus = {}; hover = undefined; hiddenDoms.clear(); flyItem = undefined; scaleTarget = scale; killMomentum(); zoomAnchor = null; retarget(); geometryDirty = true; labelsDirty = true }, setDimension: (next) => { dimTarget = next ? 0 : 1; flyItem = undefined; scaleTarget = scale; killMomentum(); zoomAnchor = null }, setFilters: (signal, recent) => { signalOnly = signal; recentOnly = recent; geometryDirty = true }, setFocus: (next) => { focus = next; retarget(); labelsDirty = true }, setHover: (next) => { hover = next; retarget() }, setHiddenDomains: (doms) => { hiddenDoms = new Set(doms); retarget(); labelsDirty = true }, setLegendOpen: (open) => { legendOpen = open }, setTerrain: (next) => { terrainOn = next }, destroy: () => { cancelAnimationFrame(frame); removeEventListener('resize', resize); canvas.removeEventListener('mousedown', down); canvas.removeEventListener('click', click); canvas.removeEventListener('dblclick', open); canvas.removeEventListener('contextmenu', contextmenu); removeEventListener('mousemove', move); removeEventListener('mouseup', up); canvas.removeEventListener('wheel', wheel); delete canvas.dataset.intro; labels?.replaceChildren(); leaders?.replaceChildren(); gl.deleteBuffer(buffer); gl.deleteBuffer(orbBuffer); for (const bufs of Object.values(terrainBuffers)) { gl.deleteBuffer(bufs.contours); gl.deleteBuffer(bufs.ridges) } if (lineProgram) gl.deleteProgram(lineProgram); gl.deleteProgram(program); killMomentum() } }
}
