import type { MapData, MapPoint } from '../api/map'

export type MapHover = { point: MapPoint; x: number; y: number }
export type MapRenderer = { setView: (view: 'all' | 'content') => void; setDimension: (flat: boolean) => void; setFilters: (signal: boolean, recent: boolean) => void; setGroupFocus: (group?: number) => void; destroy: () => void }

const vertex = `attribute vec3 p; attribute vec3 color; attribute float alpha; uniform float u_flat; uniform float zoom; uniform vec2 pan; uniform float theta; uniform float phi; varying vec3 c; varying float a; void main(){ vec3 q=mix(p,vec3(p.xy,0.),u_flat); float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi); q=vec3(ct*q.x+st*q.z,sp*(st*q.x-ct*q.z)+cp*q.y,-cp*(st*q.x-ct*q.z)+sp*q.y); float depth=1.35-q.z*.24; gl_Position=vec4(q.xy*.88*zoom/depth+pan,q.z*.12,1.); gl_PointSize=clamp(4./depth,2.,12.); c=color; a=alpha; }`
const fragment = `precision mediump float; varying vec3 c; varying float a; void main(){ float d=length(gl_PointCoord*2.-1.); if(d>1.) discard; gl_FragColor=vec4(c,a); }`
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

export function mountMapRenderer(canvas: HTMLCanvasElement, data: MapData, onHover?: (hover?: MapHover) => void, labels?: HTMLElement): MapRenderer {
  const gl = canvas.getContext('webgl', { antialias: false, alpha: true })
  if (!gl) throw new Error('WebGL is unavailable in this browser')
  const program = gl.createProgram()!
  gl.attachShader(program, shader(gl, gl.VERTEX_SHADER, vertex))
  gl.attachShader(program, shader(gl, gl.FRAGMENT_SHADER, fragment))
  gl.linkProgram(program)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || 'program link failed')
  gl.useProgram(program)
  const buffer = gl.createBuffer()!
  const position = gl.getAttribLocation(program, 'p')
  const color = gl.getAttribLocation(program, 'color')
  const alpha = gl.getAttribLocation(program, 'alpha')
  const flat = gl.getUniformLocation(program, 'u_flat')
  const zoom = gl.getUniformLocation(program, 'zoom')
  const pan = gl.getUniformLocation(program, 'pan')
  const theta = gl.getUniformLocation(program, 'theta')
  const phi = gl.getUniformLocation(program, 'phi')
  let view: 'all' | 'content' = 'all'
  let isFlat = location.hash === '#2d'
  let frame = 0
  let scale = 1
  let offset: [number, number] = [0, 0]
  let drag: { x: number; y: number } | undefined
  let orbit = false
  let angle = .5
  let tilt = .3
  let signalOnly = false
  let recentOnly = false
  let geometryDirty = true
  let pointCount = 0
  let renderedPoints: Array<{ point: MapPoint; position: number[] }> = []
  let focusedGroup: number | undefined
  let hoveredPoint: MapPoint | undefined
  let labelsDirty = true
  let labelItems: Array<{ position: number[]; radius: number; node: HTMLDivElement; rank: number; n: number }> = []

  const resize = () => { const ratio = Math.min(devicePixelRatio || 1, 2); canvas.width = innerWidth * ratio; canvas.height = innerHeight * ratio; canvas.style.width = `${innerWidth}px`; canvas.style.height = `${innerHeight}px`; gl.viewport(0, 0, canvas.width, canvas.height) }
  const draw = () => {
    if (geometryDirty) {
      const rank = Object.fromEntries(data.all.groups.map((group, index) => ({ index, n: group.n })).sort((a, b) => b.n - a.n).map((group, index) => [group.index, index])) as Record<number, number>
      const groupCount = data.all.groups.length
      renderedPoints = []
      const points = data.points.flatMap((point) => {
      if (view === 'content' && !point.c3) return []
      const position = isFlat
        ? view === 'content' ? [point.cx ?? point.x, point.cy ?? point.y, 0] : [point.x, point.y, 0]
        : view === 'content' && point.c3 ? point.c3 : point.z3
      const days = point.d ? (Date.parse(document.lastModified) - Date.parse(point.d)) / 86_400_000 : Infinity
      const recency = recentOnly ? Math.max(.12, Math.pow(.5, Math.max(0, days) / 90)) : 1
      const signal = signalOnly && point.r < 1 ? .04 : recency
      const content = view === 'content'
      const color = content ? point.th !== undefined && point.th >= 0 ? rampColor(point.th / 7) : gray : point.g < 0 ? gray : rampColor((rank[point.g] ?? 0) / Math.max(1, groupCount - 1))
      const base = content ? point.c3 ? .95 : 0 : point.g < 0 ? .4 : 1
      const group = content ? point.th : point.g
      const focus = focusedGroup === undefined || group === focusedGroup ? 1 : .08
      renderedPoints.push({ point, position })
      return [...position, ...color, (signal === .04 ? .04 : base * signal) * focus]
      })
      pointCount = points.length / 7
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.STATIC_DRAW)
      geometryDirty = false
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.enableVertexAttribArray(position)
    gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 28, 0)
    gl.enableVertexAttribArray(color)
    gl.vertexAttribPointer(color, 3, gl.FLOAT, false, 28, 12)
    gl.enableVertexAttribArray(alpha)
    gl.vertexAttribPointer(alpha, 1, gl.FLOAT, false, 28, 24)
    gl.clearColor(0, 0, 0, 1)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.uniform1f(flat, isFlat ? 1 : 0)
    gl.uniform1f(zoom, scale)
    gl.uniform2f(pan, offset[0], offset[1])
    gl.uniform1f(theta, isFlat ? 0 : angle)
    gl.uniform1f(phi, isFlat ? 0 : tilt)
    gl.drawArrays(gl.POINTS, 0, pointCount)
  }
  const render = () => { draw(); placeLabels(); frame = requestAnimationFrame(render) }
  const project = (position: number[]) => { let [x, y, z] = position; if (isFlat) z = 0; const ct = Math.cos(isFlat ? 0 : angle), st = Math.sin(isFlat ? 0 : angle), cp = Math.cos(isFlat ? 0 : tilt), sp = Math.sin(isFlat ? 0 : tilt); const rx = ct * x + st * z; const rz = -st * x + ct * z; const ry = sp * -rz + cp * y; const depth = 1.35 - (cp * rz + sp * y) * .24; return [(rx * .88 * scale / depth + offset[0] + 1) * canvas.clientWidth / 2, (1 - (ry * .88 * scale / depth + offset[1])) * canvas.clientHeight / 2, depth] }
  const placeLabels = () => {
    if (!labels) return
    if (labelsDirty) {
      const groups = view === 'content' ? data.content.groups : data.all.groups
      const buckets = groups.map(() => ({ x: 0, y: 0, z: 0, n: 0, points: [] as number[][] }))
      for (const item of renderedPoints) { const group = view === 'content' ? item.point.th ?? -1 : item.point.g; if (group < 0 || !buckets[group]) continue; const bucket = buckets[group]; bucket.x += item.position[0]; bucket.y += item.position[1]; bucket.z += item.position[2]; bucket.n++; bucket.points.push(item.position) }
      labels.replaceChildren()
      labelItems = groups.map((group, index) => ({ group, index })).filter(({ group, index }) => group.n && buckets[index].n && (focusedGroup === undefined || focusedGroup === index)).sort((a, b) => b.group.n - a.group.n).slice(0, focusedGroup === undefined ? 10 : 1).map(({ group, index }, rank) => { const bucket = buckets[index]; const position = [bucket.x / bucket.n, bucket.y / bucket.n, bucket.z / bucket.n]; const radius = Math.sqrt(Math.max(0, ...bucket.points.map((point) => (point[0] - position[0]) ** 2 + (point[1] - position[1]) ** 2 + (point[2] - position[2]) ** 2))); const node = document.createElement('div'); node.className = 'map-label'; node.textContent = group.label; node.style.fontSize = `${Math.max(10, Math.min(14, 9 + Math.sqrt(group.n) * .25))}px`; labels.appendChild(node); return { position, radius, node, rank, n: group.n } })
      labelsDirty = false
    }
    const placed: Array<{ x: number; y: number; width: number }> = []
    for (const item of labelItems) { const [x, centerY, depth] = project(item.position); const spread = item.radius * scale * canvas.clientHeight * .25 / depth; let y = centerY - spread - 22; const width = (item.node.textContent?.length ?? 1) * parseFloat(item.node.style.fontSize) * .72; for (let i = 0; i < 10 && placed.some((other) => Math.abs(other.y - y) < 22 && Math.abs(other.x - x) < (other.width + width) / 2 + 10); i++) y -= 22; const visible = depth > 0 && x >= 0 && y >= 40 && x <= canvas.clientWidth - 290 && y <= canvas.clientHeight && !(item.rank >= 6 && spread < 70); item.node.style.display = visible ? 'block' : 'none'; if (!visible) continue; y = Math.max(46, y); item.node.style.left = `${x}px`; item.node.style.top = `${y}px`; item.node.style.opacity = `${item.rank < 6 ? .9 : Math.min(.9, (spread - 70) / 120 + .35)}`; placed.push({ x, y, width }) }
  }
  const hover = (event: MouseEvent) => { if (drag) return; const rect = canvas.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) { hoveredPoint = undefined; onHover?.(); return } let best: { point: MapPoint; distance: number } | undefined; for (const item of renderedPoints) { if (signalOnly && item.point.r < 1) continue; const [x, y] = project(item.position); const distance = (x - (event.clientX - rect.left)) ** 2 + (y - (event.clientY - rect.top)) ** 2; if (distance < 144 && (!best || distance < best.distance)) best = { point: item.point, distance } } hoveredPoint = best?.point; onHover?.(best ? { point: best.point, x: event.clientX, y: event.clientY } : undefined) }
  const down = (event: MouseEvent) => { if (event.button !== 0 && event.button !== 2) return; event.preventDefault(); orbit = !isFlat && event.button === 0 && !event.shiftKey; drag = { x: event.clientX, y: event.clientY }; canvas.classList.add('dragging') }
  const move = (event: MouseEvent) => { if (!drag) { hover(event); return } const dx = event.clientX - drag.x; const dy = event.clientY - drag.y; if (orbit) { angle -= dx * .005; tilt = Math.max(-1.35, Math.min(1.35, tilt + dy * .005)) } else offset = [offset[0] + dx / innerWidth * 2, offset[1] - dy / innerHeight * 2]; drag = { x: event.clientX, y: event.clientY }; onHover?.() }
  const up = () => { drag = undefined; orbit = false; canvas.classList.remove('dragging') }
  const wheel = (event: WheelEvent) => { event.preventDefault(); const previous = scale; scale = Math.max(.3, Math.min(12, scale * Math.exp(-event.deltaY * .0012))); const x = event.clientX / innerWidth * 2 - 1; const y = 1 - event.clientY / innerHeight * 2; const delta = (scale - previous) * .88; offset = [offset[0] - x * delta, offset[1] - y * delta] }
  const contextmenu = (event: MouseEvent) => event.preventDefault()
  const open = () => { if (hoveredPoint?.u) window.open(hoveredPoint.u, '_blank', 'noopener') }
  resize(); addEventListener('resize', resize); canvas.addEventListener('mousedown', down); canvas.addEventListener('dblclick', open); canvas.addEventListener('contextmenu', contextmenu); addEventListener('mousemove', move); addEventListener('mouseup', up); canvas.addEventListener('wheel', wheel, { passive: false }); render()
  return { setView: (next) => { view = next; focusedGroup = undefined; geometryDirty = true; labelsDirty = true }, setDimension: (next) => { isFlat = next; geometryDirty = true; labelsDirty = true }, setFilters: (signal, recent) => { signalOnly = signal; recentOnly = recent; geometryDirty = true }, setGroupFocus: (group) => { focusedGroup = group; geometryDirty = true; labelsDirty = true }, destroy: () => { cancelAnimationFrame(frame); removeEventListener('resize', resize); canvas.removeEventListener('mousedown', down); canvas.removeEventListener('dblclick', open); canvas.removeEventListener('contextmenu', contextmenu); removeEventListener('mousemove', move); removeEventListener('mouseup', up); canvas.removeEventListener('wheel', wheel); labels?.replaceChildren(); gl.deleteBuffer(buffer); gl.deleteProgram(program) } }
}
