import type { MapData, MapPoint } from '../api/map'
import { aggFactor, groupStats, pointGroup, subCells } from './mapAggregation'
import type { SubCell } from './mapAggregation'

export type MapHover = { point: MapPoint; x: number; y: number }
export type MapRenderer = { setView: (view: 'all' | 'content') => void; setDimension: (flat: boolean) => void; setFilters: (signal: boolean, recent: boolean) => void; setGroupFocus: (group?: number) => void; setGroupHover: (group?: number) => void; setHiddenGroups: (groups: Set<number>) => void; setLegendOpen: (open: boolean) => void; destroy: () => void }

// Both layouts ride in the buffer: p0/p1 are the 3D everything/content
// positions, q0/q1 the dedicated 2D embeddings. The morph uniform blends
// everything<->content, the dim uniform blends flat<->volume — so view and
// dimension changes are pure uniform animation over a static buffer.
const vertex = `attribute vec3 p0; attribute vec3 p1; attribute vec2 q0; attribute vec2 q1; attribute vec3 color0; attribute vec3 color1; attribute float alpha0; attribute float alpha1; attribute float size; attribute float grp; uniform float morph; uniform float dim; uniform float zoom; uniform vec2 pan; uniform float theta; uniform float phi; uniform float dpr; uniform float galpha[64]; varying vec3 c; varying float a; void main(){ vec3 p3=mix(p0,p1,morph); vec2 p2=mix(q0,q1,morph); vec3 q=mix(vec3(p2,0.),p3,dim); float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi); q=vec3(ct*q.x+st*q.z,sp*(st*q.x-ct*q.z)+cp*q.y,-cp*(st*q.x-ct*q.z)+sp*q.y); float depth=1.35-q.z*.24; gl_Position=vec4(q.xy*.88*zoom/depth+pan,q.z*.12,1.); gl_PointSize=clamp(size*zoom/depth*dpr,1.8,26.*dpr); c=mix(color0,color1,morph); float ga=grp<0.?1.:galpha[int(grp+.5)]; a=mix(alpha0,alpha1,morph)*ga; }`
const fragment = `precision mediump float; varying vec3 c; varying float a; void main(){ vec2 p=gl_PointCoord*2.-1.; float d2=dot(p,p); float edge=smoothstep(1.,.82,sqrt(d2)); if(edge<=0.) discard; float z=sqrt(max(0.,1.-d2)); vec3 n=vec3(p.x,-p.y,z); vec3 light=normalize(vec3(-.45,.55,.72)); float wrap=(dot(n,light)+.6)/1.6; float diff=.35+.65*clamp(wrap,0.,1.); float spec=pow(max(dot(reflect(-light,n),vec3(0.,0.,1.)),0.),12.)*.10; vec3 shaded=c*diff*(.75+.25*z)+vec3(spec); float alpha=a*edge; gl_FragColor=vec4(shaded*alpha,alpha); }`
const ramp = ['#5b7cfa', '#2fb7c9', '#43c26a', '#d9a520', '#e8703a', '#e0507e', '#9d6bf0']
const gray: [number, number, number] = [.435, .427, .4]
const rgb = (hex: string): [number, number, number] => [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255) as [number, number, number]
function rampColor(value: number): [number, number, number] { const x = Math.max(0, Math.min(.9999, value)) * (ramp.length - 1); const i = Math.floor(x); const f = x - i; const a = rgb(ramp[i]); const b = rgb(ramp[i + 1]); return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f] }
export function mapGroupColor(data: MapData, view: 'all' | 'content', index: number): string { const order = data.all.groups.map((group, i) => ({ i, n: group.n })).sort((a, b) => b.n - a.n); const rank = order.findIndex((item) => item.i === index); const color = rampColor(view === 'content' ? index / 7 : rank / Math.max(1, order.length - 1)); return `rgb(${color.map((channel) => Math.round(channel * 255)).join(', ')})` }

function shader(gl: WebGLRenderingContext, type: number, source: string) {
  const value = gl.createShader(type)!
  gl.shaderSource(value, source)
  gl.compileShader(value)
  if (!gl.getShaderParameter(value, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(value) || 'shader compilation failed')
  return value
}

type RenderedPoint = { point: MapPoint; p3a: number[]; p3b: number[]; p2a: number[]; p2b: number[]; group: number }

export function mountMapRenderer(canvas: HTMLCanvasElement, data: MapData, onHover?: (hover?: MapHover) => void, labels?: HTMLElement, onFocus?: (group?: number) => void, leaders?: SVGSVGElement): MapRenderer {
  const gl = canvas.getContext('webgl', { antialias: false, alpha: true, premultipliedAlpha: true })
  if (!gl) throw new Error('WebGL is unavailable in this browser')
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
  const position0 = gl.getAttribLocation(program, 'p0')
  const position1 = gl.getAttribLocation(program, 'p1')
  const flat0 = gl.getAttribLocation(program, 'q0')
  const flat1 = gl.getAttribLocation(program, 'q1')
  const color0 = gl.getAttribLocation(program, 'color0')
  const color1 = gl.getAttribLocation(program, 'color1')
  const alpha0 = gl.getAttribLocation(program, 'alpha0')
  const alpha1 = gl.getAttribLocation(program, 'alpha1')
  const size = gl.getAttribLocation(program, 'size')
  const grp = gl.getAttribLocation(program, 'grp')
  const galphaU = gl.getUniformLocation(program, 'galpha[0]')
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
  let angle = .5
  let tilt = .3
  let signalOnly = false
  let recentOnly = false
  let geometryDirty = true
  let pointCount = 0
  let renderedPoints: RenderedPoint[] = []
  let focusedGroup: number | undefined
  let hoveredGroup: number | undefined
  let hiddenGroups = new Set<number>()
  let hoveredPoint: MapPoint | undefined
  let labelsDirty = true
  let labelItems: Array<{ c3: number[]; c2: number[]; radius: number; node: HTMLDivElement; line?: SVGLineElement; rank: number; n: number }> = []
  let morph = location.hash === '#content' ? 1 : 0
  let morphTarget = morph
  let dimVal = location.hash === '#2d' ? 0 : 1
  let dimTarget = dimVal
  let legendOpen = true
  const allCount = data.all.groups.length
  const rankAll = Object.fromEntries(data.all.groups.map((group, index) => ({ index, n: group.n })).sort((a, b) => b.n - a.n).map((group, rank) => [group.index, rank])) as Record<number, number>
  const groupColor = (g: number): [number, number, number] => view === 'content' ? rampColor(g / 7) : rampColor((rankAll[g] ?? 0) / Math.max(1, allCount - 1))
  const subCache: Record<string, SubCell[]> = {}

  const lerp3 = (a: number[], b: number[], t: number) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
  // flat<->volume blend of a morphed 3D position and its 2D counterpart
  const blend = (p3: number[], p2: number[]) => [p2[0] + (p3[0] - p2[0]) * dimVal, p2[1] + (p3[1] - p2[1]) * dimVal, p3[2] * dimVal]
  const morph3 = (item: RenderedPoint) => lerp3(item.p3a, item.p3b, morph)
  const morph2 = (item: RenderedPoint) => [item.p2a[0] + (item.p2b[0] - item.p2a[0]) * morph, item.p2a[1] + (item.p2b[1] - item.p2a[1]) * morph]
  const worldOf = (item: RenderedPoint) => blend(morph3(item), morph2(item))
  const project = (world: number[]) => { const [x, y, z] = world; const ea = angle * dimVal, et = tilt * dimVal; const ct = Math.cos(ea), st = Math.sin(ea), cp = Math.cos(et), sp = Math.sin(et); const rx = ct * x + st * z; const rz = -st * x + ct * z; const ry = sp * -rz + cp * y; const depth = 1.35 - (cp * rz + sp * y) * .24; return [(rx * .88 * scale / depth + offset[0] + 1) * canvas.clientWidth / 2, (1 - (ry * .88 * scale / depth + offset[1])) * canvas.clientHeight / 2, depth] }

  const resize = () => { const ratio = Math.min(devicePixelRatio || 1, 2); canvas.width = innerWidth * ratio; canvas.height = innerHeight * ratio; canvas.style.width = `${innerWidth}px`; canvas.style.height = `${innerHeight}px`; gl.viewport(0, 0, canvas.width, canvas.height) }
  const draw = () => {
    if (geometryDirty) {
      renderedPoints = []
      const contentView = view === 'content'
      const dimOf = (group: number) => hiddenGroups.has(group) ? 0 : focusedGroup !== undefined && group !== focusedGroup || hoveredGroup !== undefined && group !== hoveredGroup ? .08 : 1
      const points = data.points.flatMap((point) => {
      const p3a = point.z3
      const p3b = point.c3 ?? point.z3
      const p2a = [point.x, point.y]
      const p2b = [point.cx ?? point.x, point.cy ?? point.y]
      const days = point.d ? (Date.parse(document.lastModified) - Date.parse(point.d)) / 86_400_000 : Infinity
      const recency = recentOnly ? Math.max(.12, Math.pow(.5, Math.max(0, days) / 90)) : 1
      const sig = signalOnly && point.r < 1 ? .04 : recency
      const alphaFor = (base: number, focus: number) => (sig === .04 ? .04 : base * sig) * focus
      const color0 = point.g < 0 ? gray : rampColor((rankAll[point.g] ?? 0) / Math.max(1, allCount - 1))
      const color1 = point.th !== undefined && point.th >= 0 ? rampColor(point.th / 7) : gray
      const alpha0 = alphaFor(point.g < 0 ? .4 : 1, contentView ? 1 : dimOf(point.g))
      const alpha1 = alphaFor(point.c3 ? .95 : 0, contentView ? dimOf(point.th ?? -1) : 1)
      const group = pointGroup(point, view)
      renderedPoints.push({ point, p3a, p3b, p2a, p2b, group })
      return [...p3a, ...p3b, ...p2a, ...p2b, ...color0, ...color1, alpha0, alpha1, 3.2 + point.r * 1.8 + (point.c3 ? .8 : 0), group]
      })
      pointCount = points.length / 20
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.STATIC_DRAW)
      geometryDirty = false
    }
    const drawSet = (buf: WebGLBuffer, count: number) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buf)
      gl.enableVertexAttribArray(position0); gl.vertexAttribPointer(position0, 3, gl.FLOAT, false, 80, 0)
      gl.enableVertexAttribArray(position1); gl.vertexAttribPointer(position1, 3, gl.FLOAT, false, 80, 12)
      gl.enableVertexAttribArray(flat0); gl.vertexAttribPointer(flat0, 2, gl.FLOAT, false, 80, 24)
      gl.enableVertexAttribArray(flat1); gl.vertexAttribPointer(flat1, 2, gl.FLOAT, false, 80, 32)
      gl.enableVertexAttribArray(color0); gl.vertexAttribPointer(color0, 3, gl.FLOAT, false, 80, 40)
      gl.enableVertexAttribArray(color1); gl.vertexAttribPointer(color1, 3, gl.FLOAT, false, 80, 52)
      gl.enableVertexAttribArray(alpha0); gl.vertexAttribPointer(alpha0, 1, gl.FLOAT, false, 80, 64)
      gl.enableVertexAttribArray(alpha1); gl.vertexAttribPointer(alpha1, 1, gl.FLOAT, false, 80, 68)
      gl.enableVertexAttribArray(size); gl.vertexAttribPointer(size, 1, gl.FLOAT, false, 80, 72)
      gl.enableVertexAttribArray(grp); gl.vertexAttribPointer(grp, 1, gl.FLOAT, false, 80, 76)
      gl.drawArrays(gl.POINTS, 0, count)
    }
    // adaptive aggregation: while a cluster is small on screen its points fade
    // out (galpha) and it condenses into one orb per spatial sub-cell; zooming
    // in dissolves the orbs back into points.
    const groups = view === 'content' ? data.content.groups : data.all.groups
    const m3s: number[][] = []
    const m2s: number[][] = []
    const worlds: number[][] = []
    for (const item of renderedPoints) { const m3 = morph3(item); const m2 = morph2(item); m3s.push(m3); m2s.push(m2); worlds.push(blend(m3, m2)) }
    const stats = groupStats(worlds, renderedPoints.map((item) => item.group), groups.length)
    const ea = angle * dimVal
    const right = [Math.cos(ea), 0, Math.sin(ea)]
    const galphaArr = new Float32Array(64).fill(1)
    const aggT = stats.map((s, g) => { if (!s.n) return 1; const [x0] = project(s.centroid); const [xr] = project([s.centroid[0] + s.radius * right[0], s.centroid[1] + s.radius * right[1], s.centroid[2] + s.radius * right[2]]); const t = aggFactor(Math.abs(xr - x0)); if (g < 64) galphaArr[g] = t; return t })
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.uniform1f(morphUniform, morph)
    gl.uniform1f(dimUniform, dimVal)
    gl.uniform1f(zoom, scale)
    gl.uniform2f(pan, offset[0], offset[1])
    gl.uniform1f(theta, ea)
    gl.uniform1f(phi, tilt * dimVal)
    gl.uniform1f(dpr, Math.min(devicePixelRatio || 1, 2))
    gl.uniform1fv(galphaU, galphaArr)
    drawSet(buffer, pointCount)
    const orbs: number[] = []
    for (const sub of (subCache[view] ??= subCells(data.points, view))) {
      const vis = hiddenGroups.has(sub.group) ? 0 : focusedGroup !== undefined && sub.group !== focusedGroup || hoveredGroup !== undefined && sub.group !== hoveredGroup ? .08 : 1
      const orbA = (1 - (aggT[sub.group] ?? 1)) * vis
      if (orbA < .02) continue
      let x = 0, y = 0, z = 0, fx = 0, fy = 0
      for (const i of sub.indices) { x += m3s[i][0]; y += m3s[i][1]; z += m3s[i][2]; fx += m2s[i][0]; fy += m2s[i][1] }
      const m = sub.indices.length; x /= m; y /= m; z /= m; fx /= m; fy /= m
      const col = groupColor(sub.group)
      orbs.push(x, y, z, x, y, z, fx, fy, fx, fy, ...col, ...col, orbA * .95, orbA * .95, 4.5 + Math.sqrt(m) * 1.5, -1)
    }
    if (orbs.length) { gl.bindBuffer(gl.ARRAY_BUFFER, orbBuffer); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(orbs), gl.DYNAMIC_DRAW); drawSet(orbBuffer, orbs.length / 20) }
  }
  let lastFrame = 0
  const render = (now = 0) => {
    const dt = lastFrame ? Math.min(.05, (now - lastFrame) / 1000) : .016; lastFrame = now
    const dm = morphTarget - morph; morph = Math.abs(dm) <= 1e-3 ? morphTarget : morph + dm * (1 - Math.exp(-5 * dt))
    const dd = dimTarget - dimVal; dimVal = Math.abs(dd) <= 1e-3 ? dimTarget : dimVal + dd * (1 - Math.exp(-5 * dt))
    if (flyItem) {
      const e = 1 - Math.exp(-8 * dt)
      scale += (scaleTarget - scale) * e
      const [sx, sy] = project(worldOf(flyItem))
      const ox = offset[0] - (2 * sx / canvas.clientWidth - 1); const oy = offset[1] + (2 * sy / canvas.clientHeight - 1)
      offset = [offset[0] + (ox - offset[0]) * e, offset[1] + (oy - offset[1]) * e]
      if (Math.abs(scaleTarget - scale) < 1e-3 && Math.abs(ox - offset[0]) < 1e-3 && Math.abs(oy - offset[1]) < 1e-3) { scale = scaleTarget; flyItem = undefined }
    }
    draw(); placeLabels(); frame = requestAnimationFrame(render)
  }
  const placeLabels = () => {
    if (!labels) return
    if (labelsDirty) {
      const groups = view === 'content' ? data.content.groups : data.all.groups
      const buckets = groups.map(() => ({ x: 0, y: 0, z: 0, fx: 0, fy: 0, n: 0, points: [] as number[][] }))
      for (const item of renderedPoints) { const group = view === 'content' ? item.point.th ?? -1 : item.point.g; if (group < 0 || !buckets[group]) continue; const s3 = view === 'content' ? item.p3b : item.p3a; const s2 = view === 'content' ? item.p2b : item.p2a; const bucket = buckets[group]; bucket.x += s3[0]; bucket.y += s3[1]; bucket.z += s3[2]; bucket.fx += s2[0]; bucket.fy += s2[1]; bucket.n++; bucket.points.push(s3) }
      labels.replaceChildren(); leaders?.replaceChildren()
      labelItems = groups.map((group, index) => ({ group, index })).filter(({ group, index }) => group.n && buckets[index].n && !hiddenGroups.has(index) && (focusedGroup === undefined || focusedGroup === index)).sort((a, b) => b.group.n - a.group.n).slice(0, focusedGroup === undefined ? 10 : 1).map(({ group, index }, rank) => { const bucket = buckets[index]; const c3 = [bucket.x / bucket.n, bucket.y / bucket.n, bucket.z / bucket.n]; const c2 = [bucket.fx / bucket.n, bucket.fy / bucket.n]; const radius = Math.sqrt(Math.max(0, ...bucket.points.map((point) => (point[0] - c3[0]) ** 2 + (point[1] - c3[1]) ** 2 + (point[2] - c3[2]) ** 2))); const node = document.createElement('div'); node.className = 'map-label'; node.textContent = group.label; node.style.fontSize = `${Math.max(10, Math.min(14, 9 + Math.sqrt(group.n) * .25))}px`; labels.appendChild(node); const line = leaders ? document.createElementNS('http://www.w3.org/2000/svg', 'line') : undefined; if (line) { line.setAttribute('stroke-width', '1'); leaders!.appendChild(line) } return { c3, c2, radius, node, line, rank, n: group.n } })
      labelsDirty = false
    }
    const placed: Array<{ x: number; y: number; width: number }> = []
    for (const item of labelItems) { const [x, centerY, depth] = project(blend(item.c3, item.c2)); const spread = item.radius * scale * canvas.clientHeight * .25 / depth; let y = centerY - spread - 22; const width = (item.node.textContent?.length ?? 1) * parseFloat(item.node.style.fontSize) * .72; for (let i = 0; i < 10 && placed.some((other) => Math.abs(other.y - y) < 22 && Math.abs(other.x - x) < (other.width + width) / 2 + 10); i++) y -= 22; const visible = depth > 0 && x >= 0 && y >= 40 && x <= canvas.clientWidth - (legendOpen ? 290 : 70) && y <= canvas.clientHeight && !(item.rank >= 6 && spread < 70); item.node.style.display = visible ? 'block' : 'none'; if (item.line) item.line.style.display = 'none'; if (!visible) continue; y = Math.max(46, y); const size = parseFloat(item.node.style.fontSize); item.node.style.left = `${x}px`; item.node.style.top = `${y}px`; const alpha = item.rank < 6 ? .9 : Math.min(.9, (spread - 70) / 120 + .35); item.node.style.opacity = `${alpha}`; const gap = centerY - y - size; if (item.line && gap > 14) { item.line.style.display = 'block'; item.line.setAttribute('stroke', `rgba(255,255,255,${(.16 * alpha).toFixed(3)})`); item.line.setAttribute('x1', `${x}`); item.line.setAttribute('y1', `${centerY - Math.min(spread * .7, gap - 6)}`); item.line.setAttribute('x2', `${x}`); item.line.setAttribute('y2', `${y + size * .8}`) } placed.push({ x, y, width }) }
  }
  const hover = (event: MouseEvent) => { if (drag) return; const rect = canvas.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) { hoveredPoint = undefined; onHover?.(); return } let best: { point: MapPoint; distance: number } | undefined; for (const item of renderedPoints) { const group = view === 'content' ? item.point.th ?? -1 : item.point.g; if (signalOnly && item.point.r < 1 || hiddenGroups.has(group) || focusedGroup !== undefined && group !== focusedGroup) continue; const [x, y] = project(worldOf(item)); const distance = (x - (event.clientX - rect.left)) ** 2 + (y - (event.clientY - rect.top)) ** 2; if (distance < 144 && (!best || distance < best.distance)) best = { point: item.point, distance } } hoveredPoint = best?.point; onHover?.(best ? { point: best.point, x: event.clientX, y: event.clientY } : undefined) }
  const down = (event: MouseEvent) => { if (event.button !== 0 && event.button !== 2) return; event.preventDefault(); moved = 0; orbit = dimTarget === 1 && event.button === 0 && !event.shiftKey; drag = { x: event.clientX, y: event.clientY }; canvas.classList.add('dragging') }
  const move = (event: MouseEvent) => { if (!drag) { hover(event); return } const dx = event.clientX - drag.x; const dy = event.clientY - drag.y; moved += Math.abs(dx) + Math.abs(dy); flyItem = undefined; scaleTarget = scale; if (orbit) { angle -= dx * .005; tilt = Math.max(-1.35, Math.min(1.35, tilt + dy * .005)) } else offset = [offset[0] + dx / innerWidth * 2, offset[1] - dy / innerHeight * 2]; drag = { x: event.clientX, y: event.clientY }; onHover?.() }
  const up = () => { drag = undefined; orbit = false; canvas.classList.remove('dragging') }
  // exact cursor-anchored zoom: screen = world*k*scale + pan, so holding the
  // cursor's NDC point fixed means pan' = c - (c - pan) * (scale'/scale)
  const wheel = (event: WheelEvent) => { event.preventDefault(); flyItem = undefined; const rect = canvas.getBoundingClientRect(); const previous = scale; scale = Math.max(.3, Math.min(12, scale * Math.exp(-event.deltaY * .0012))); scaleTarget = scale; const cx = (event.clientX - rect.left) / rect.width * 2 - 1; const cy = 1 - (event.clientY - rect.top) / rect.height * 2; const ratio = scale / previous; offset = [cx - (cx - offset[0]) * ratio, cy - (cy - offset[1]) * ratio] }
  const contextmenu = (event: MouseEvent) => event.preventDefault()
  const open = () => { if (hoveredPoint?.u) window.open(hoveredPoint.u, '_blank', 'noopener') }
  const click = () => { if (moved >= 4) return; if (!hoveredPoint) { focusedGroup = undefined; flyItem = undefined; scaleTarget = scale; onFocus?.(); geometryDirty = true; labelsDirty = true; return } const group = view === 'content' ? hoveredPoint.th ?? -1 : hoveredPoint.g; if (group < 0) return; focusedGroup = group; const item = renderedPoints.find((entry) => entry.point === hoveredPoint); if (item) { scaleTarget = Math.max(scale, 1.8); flyItem = item } onFocus?.(group); geometryDirty = true; labelsDirty = true }
  resize(); addEventListener('resize', resize); canvas.addEventListener('mousedown', down); canvas.addEventListener('click', click); canvas.addEventListener('dblclick', open); canvas.addEventListener('contextmenu', contextmenu); addEventListener('mousemove', move); addEventListener('mouseup', up); canvas.addEventListener('wheel', wheel, { passive: false }); render()
  return { setView: (next) => { view = next; morphTarget = next === 'content' ? 1 : 0; focusedGroup = undefined; hiddenGroups.clear(); flyItem = undefined; scaleTarget = scale; geometryDirty = true; labelsDirty = true }, setDimension: (next) => { dimTarget = next ? 0 : 1; flyItem = undefined; scaleTarget = scale }, setFilters: (signal, recent) => { signalOnly = signal; recentOnly = recent; geometryDirty = true }, setGroupFocus: (group) => { focusedGroup = group; geometryDirty = true; labelsDirty = true }, setGroupHover: (group) => { hoveredGroup = group; geometryDirty = true }, setHiddenGroups: (groups) => { hiddenGroups = new Set(groups); geometryDirty = true; labelsDirty = true }, setLegendOpen: (open) => { legendOpen = open }, destroy: () => { cancelAnimationFrame(frame); removeEventListener('resize', resize); canvas.removeEventListener('mousedown', down); canvas.removeEventListener('click', click); canvas.removeEventListener('dblclick', open); canvas.removeEventListener('contextmenu', contextmenu); removeEventListener('mousemove', move); removeEventListener('mouseup', up); canvas.removeEventListener('wheel', wheel); labels?.replaceChildren(); leaders?.replaceChildren(); gl.deleteBuffer(buffer); gl.deleteBuffer(orbBuffer); gl.deleteProgram(program) } }
}
