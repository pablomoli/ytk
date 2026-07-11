import type { MapData, MapPoint } from '../api/map'

export type MapHover = { point: MapPoint; x: number; y: number }
export type MapRenderer = { setView: (view: 'all' | 'content') => void; setDimension: (flat: boolean) => void; setFilters: (signal: boolean, recent: boolean) => void; setGroupFocus: (group?: number) => void; setGroupHover: (group?: number) => void; setHiddenGroups: (groups: Set<number>) => void; destroy: () => void }

const vertex = `attribute vec3 p0; attribute vec3 p1; attribute vec3 color; attribute float alpha; attribute float size; uniform float morph; uniform float zoom; uniform vec2 pan; uniform float theta; uniform float phi; uniform float dpr; varying vec3 c; varying float a; void main(){ vec3 q=mix(p0,p1,morph); float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi); q=vec3(ct*q.x+st*q.z,sp*(st*q.x-ct*q.z)+cp*q.y,-cp*(st*q.x-ct*q.z)+sp*q.y); float depth=1.35-q.z*.24; gl_Position=vec4(q.xy*.88*zoom/depth+pan,q.z*.12,1.); gl_PointSize=clamp(size*zoom/depth*dpr,1.8,26.*dpr); c=color; a=alpha; }`
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
  const position0 = gl.getAttribLocation(program, 'p0')
  const position1 = gl.getAttribLocation(program, 'p1')
  const color = gl.getAttribLocation(program, 'color')
  const alpha = gl.getAttribLocation(program, 'alpha')
  const size = gl.getAttribLocation(program, 'size')
  const morphUniform = gl.getUniformLocation(program, 'morph')
  const zoom = gl.getUniformLocation(program, 'zoom')
  const pan = gl.getUniformLocation(program, 'pan')
  const theta = gl.getUniformLocation(program, 'theta')
  const phi = gl.getUniformLocation(program, 'phi')
  const dpr = gl.getUniformLocation(program, 'dpr')
  let view: 'all' | 'content' = 'all'
  let isFlat = location.hash === '#2d'
  let frame = 0
  let scale = 1
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
  let renderedPoints: Array<{ point: MapPoint; position: number[]; target: number[] }> = []
  let focusedGroup: number | undefined
  let hoveredGroup: number | undefined
  let hiddenGroups = new Set<number>()
  let hoveredPoint: MapPoint | undefined
  let labelsDirty = true
  let labelItems: Array<{ position: number[]; radius: number; node: HTMLDivElement; line?: SVGLineElement; rank: number; n: number }> = []
  let morph = location.hash === '#content' ? 1 : 0
  let morphTarget = morph

  const resize = () => { const ratio = Math.min(devicePixelRatio || 1, 2); canvas.width = innerWidth * ratio; canvas.height = innerHeight * ratio; canvas.style.width = `${innerWidth}px`; canvas.style.height = `${innerHeight}px`; gl.viewport(0, 0, canvas.width, canvas.height) }
  const draw = () => {
    if (geometryDirty) {
      const rank = Object.fromEntries(data.all.groups.map((group, index) => ({ index, n: group.n })).sort((a, b) => b.n - a.n).map((group, index) => [group.index, index])) as Record<number, number>
      const groupCount = data.all.groups.length
      renderedPoints = []
      const points = data.points.flatMap((point) => {
      const position = isFlat ? [point.x, point.y, 0] : point.z3
      const target = isFlat ? [point.cx ?? point.x, point.cy ?? point.y, 0] : point.c3 ?? point.z3
      const days = point.d ? (Date.parse(document.lastModified) - Date.parse(point.d)) / 86_400_000 : Infinity
      const recency = recentOnly ? Math.max(.12, Math.pow(.5, Math.max(0, days) / 90)) : 1
      const signal = signalOnly && point.r < 1 ? .04 : recency
      const content = view === 'content'
      const color = content ? point.th !== undefined && point.th >= 0 ? rampColor(point.th / 7) : gray : point.g < 0 ? gray : rampColor((rank[point.g] ?? 0) / Math.max(1, groupCount - 1))
      const base = content ? point.c3 ? .95 : 0 : point.g < 0 ? .4 : 1
      const group = content ? point.th ?? -1 : point.g
      const focus = hiddenGroups.has(group) ? 0 : focusedGroup !== undefined && group !== focusedGroup || hoveredGroup !== undefined && group !== hoveredGroup ? .08 : 1
      renderedPoints.push({ point, position, target })
      return [...position, ...target, ...color, (signal === .04 ? .04 : base * signal) * focus, 3.2 + point.r * 1.8 + (content ? .8 : 0)]
      })
      pointCount = points.length / 11
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.STATIC_DRAW)
      geometryDirty = false
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.enableVertexAttribArray(position0)
    gl.vertexAttribPointer(position0, 3, gl.FLOAT, false, 44, 0)
    gl.enableVertexAttribArray(position1)
    gl.vertexAttribPointer(position1, 3, gl.FLOAT, false, 44, 12)
    gl.enableVertexAttribArray(color)
    gl.vertexAttribPointer(color, 3, gl.FLOAT, false, 44, 24)
    gl.enableVertexAttribArray(alpha)
    gl.vertexAttribPointer(alpha, 1, gl.FLOAT, false, 44, 36)
    gl.enableVertexAttribArray(size)
    gl.vertexAttribPointer(size, 1, gl.FLOAT, false, 44, 40)
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.uniform1f(morphUniform, morph)
    gl.uniform1f(zoom, scale)
    gl.uniform2f(pan, offset[0], offset[1])
    gl.uniform1f(theta, isFlat ? 0 : angle)
    gl.uniform1f(phi, isFlat ? 0 : tilt)
    gl.uniform1f(dpr, Math.min(devicePixelRatio || 1, 2))
    gl.drawArrays(gl.POINTS, 0, pointCount)
  }
  const render = () => { morph += (morphTarget - morph) * .08; draw(); placeLabels(); frame = requestAnimationFrame(render) }
  const project = (position: number[], target = position) => { let x = position[0] + (target[0] - position[0]) * morph; let y = position[1] + (target[1] - position[1]) * morph; let z = position[2] + (target[2] - position[2]) * morph; const ct = Math.cos(isFlat ? 0 : angle), st = Math.sin(isFlat ? 0 : angle), cp = Math.cos(isFlat ? 0 : tilt), sp = Math.sin(isFlat ? 0 : tilt); const rx = ct * x + st * z; const rz = -st * x + ct * z; const ry = sp * -rz + cp * y; const depth = 1.35 - (cp * rz + sp * y) * .24; return [(rx * .88 * scale / depth + offset[0] + 1) * canvas.clientWidth / 2, (1 - (ry * .88 * scale / depth + offset[1])) * canvas.clientHeight / 2, depth] }
  const placeLabels = () => {
    if (!labels) return
    if (labelsDirty) {
      const groups = view === 'content' ? data.content.groups : data.all.groups
      const buckets = groups.map(() => ({ x: 0, y: 0, z: 0, n: 0, points: [] as number[][] }))
      for (const item of renderedPoints) { const group = view === 'content' ? item.point.th ?? -1 : item.point.g; if (group < 0 || !buckets[group]) continue; const source = view === 'content' ? item.target : item.position; const bucket = buckets[group]; bucket.x += source[0]; bucket.y += source[1]; bucket.z += source[2]; bucket.n++; bucket.points.push(source) }
      labels.replaceChildren(); leaders?.replaceChildren()
      labelItems = groups.map((group, index) => ({ group, index })).filter(({ group, index }) => group.n && buckets[index].n && !hiddenGroups.has(index) && (focusedGroup === undefined || focusedGroup === index)).sort((a, b) => b.group.n - a.group.n).slice(0, focusedGroup === undefined ? 10 : 1).map(({ group, index }, rank) => { const bucket = buckets[index]; const position = [bucket.x / bucket.n, bucket.y / bucket.n, bucket.z / bucket.n]; const radius = Math.sqrt(Math.max(0, ...bucket.points.map((point) => (point[0] - position[0]) ** 2 + (point[1] - position[1]) ** 2 + (point[2] - position[2]) ** 2))); const node = document.createElement('div'); node.className = 'map-label'; node.textContent = group.label; node.style.fontSize = `${Math.max(10, Math.min(14, 9 + Math.sqrt(group.n) * .25))}px`; labels.appendChild(node); const line = leaders ? document.createElementNS('http://www.w3.org/2000/svg', 'line') : undefined; if (line) { line.setAttribute('stroke', 'rgba(255,255,255,.14)'); line.setAttribute('stroke-width', '1'); leaders!.appendChild(line) } return { position, radius, node, line, rank, n: group.n } })
      labelsDirty = false
    }
    const placed: Array<{ x: number; y: number; width: number }> = []
    for (const item of labelItems) { const [x, centerY, depth] = project(item.position); const spread = item.radius * scale * canvas.clientHeight * .25 / depth; let y = centerY - spread - 22; const width = (item.node.textContent?.length ?? 1) * parseFloat(item.node.style.fontSize) * .72; for (let i = 0; i < 10 && placed.some((other) => Math.abs(other.y - y) < 22 && Math.abs(other.x - x) < (other.width + width) / 2 + 10); i++) y -= 22; const visible = depth > 0 && x >= 0 && y >= 40 && x <= canvas.clientWidth - 290 && y <= canvas.clientHeight && !(item.rank >= 6 && spread < 70); item.node.style.display = visible ? 'block' : 'none'; if (item.line) item.line.style.display = 'none'; if (!visible) continue; y = Math.max(46, y); const size = parseFloat(item.node.style.fontSize); item.node.style.left = `${x}px`; item.node.style.top = `${y}px`; item.node.style.opacity = `${item.rank < 6 ? .9 : Math.min(.9, (spread - 70) / 120 + .35)}`; const gap = centerY - y - size; if (item.line && gap > 14) { item.line.style.display = 'block'; item.line.setAttribute('x1', `${x}`); item.line.setAttribute('y1', `${centerY - Math.min(spread * .7, gap - 6)}`); item.line.setAttribute('x2', `${x}`); item.line.setAttribute('y2', `${y + size * .8}`) } placed.push({ x, y, width }) }
  }
  const hover = (event: MouseEvent) => { if (drag) return; const rect = canvas.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) { hoveredPoint = undefined; onHover?.(); return } let best: { point: MapPoint; distance: number } | undefined; for (const item of renderedPoints) { const group = view === 'content' ? item.point.th ?? -1 : item.point.g; if (signalOnly && item.point.r < 1 || hiddenGroups.has(group) || focusedGroup !== undefined && group !== focusedGroup) continue; const [x, y] = project(item.position, item.target); const distance = (x - (event.clientX - rect.left)) ** 2 + (y - (event.clientY - rect.top)) ** 2; if (distance < 144 && (!best || distance < best.distance)) best = { point: item.point, distance } } hoveredPoint = best?.point; onHover?.(best ? { point: best.point, x: event.clientX, y: event.clientY } : undefined) }
  const down = (event: MouseEvent) => { if (event.button !== 0 && event.button !== 2) return; event.preventDefault(); moved = 0; orbit = !isFlat && event.button === 0 && !event.shiftKey; drag = { x: event.clientX, y: event.clientY }; canvas.classList.add('dragging') }
  const move = (event: MouseEvent) => { if (!drag) { hover(event); return } const dx = event.clientX - drag.x; const dy = event.clientY - drag.y; moved += Math.abs(dx) + Math.abs(dy); if (orbit) { angle -= dx * .005; tilt = Math.max(-1.35, Math.min(1.35, tilt + dy * .005)) } else offset = [offset[0] + dx / innerWidth * 2, offset[1] - dy / innerHeight * 2]; drag = { x: event.clientX, y: event.clientY }; onHover?.() }
  const up = () => { drag = undefined; orbit = false; canvas.classList.remove('dragging') }
  const wheel = (event: WheelEvent) => { event.preventDefault(); const previous = scale; scale = Math.max(.3, Math.min(12, scale * Math.exp(-event.deltaY * .0012))); const x = event.clientX / innerWidth * 2 - 1; const y = 1 - event.clientY / innerHeight * 2; const delta = (scale - previous) * .88; offset = [offset[0] - x * delta, offset[1] - y * delta] }
  const contextmenu = (event: MouseEvent) => event.preventDefault()
  const open = () => { if (hoveredPoint?.u) window.open(hoveredPoint.u, '_blank', 'noopener') }
  const click = () => { if (moved >= 4) return; if (!hoveredPoint) { focusedGroup = undefined; onFocus?.(); geometryDirty = true; labelsDirty = true; return } const group = view === 'content' ? hoveredPoint.th ?? -1 : hoveredPoint.g; if (group < 0) return; focusedGroup = group; const item = renderedPoints.find((entry) => entry.point === hoveredPoint); if (item) { scale = Math.max(scale, 1.8); const [x, y] = project(item.position, item.target); offset = [offset[0] + 1 - x / canvas.clientWidth * 2, offset[1] - (1 - y / canvas.clientHeight * 2)] } onFocus?.(group); geometryDirty = true; labelsDirty = true }
  resize(); addEventListener('resize', resize); canvas.addEventListener('mousedown', down); canvas.addEventListener('click', click); canvas.addEventListener('dblclick', open); canvas.addEventListener('contextmenu', contextmenu); addEventListener('mousemove', move); addEventListener('mouseup', up); canvas.addEventListener('wheel', wheel, { passive: false }); render()
  return { setView: (next) => { view = next; morphTarget = next === 'content' ? 1 : 0; focusedGroup = undefined; hiddenGroups.clear(); geometryDirty = true; labelsDirty = true }, setDimension: (next) => { isFlat = next; geometryDirty = true; labelsDirty = true }, setFilters: (signal, recent) => { signalOnly = signal; recentOnly = recent; geometryDirty = true }, setGroupFocus: (group) => { focusedGroup = group; geometryDirty = true; labelsDirty = true }, setGroupHover: (group) => { hoveredGroup = group; geometryDirty = true }, setHiddenGroups: (groups) => { hiddenGroups = new Set(groups); geometryDirty = true; labelsDirty = true }, destroy: () => { cancelAnimationFrame(frame); removeEventListener('resize', resize); canvas.removeEventListener('mousedown', down); canvas.removeEventListener('click', click); canvas.removeEventListener('dblclick', open); canvas.removeEventListener('contextmenu', contextmenu); removeEventListener('mousemove', move); removeEventListener('mouseup', up); canvas.removeEventListener('wheel', wheel); labels?.replaceChildren(); leaders?.replaceChildren(); gl.deleteBuffer(buffer); gl.deleteProgram(program) } }
}
