import type { MapData } from '../api/map'

export type MapRenderer = { setView: (view: 'all' | 'content') => void; setDimension: (flat: boolean) => void; destroy: () => void }

const vertex = `attribute vec3 p; uniform float flat; uniform float zoom; uniform vec2 pan; void main(){ vec3 q=mix(p,vec3(p.xy,0.),flat); gl_Position=vec4(q.xy*.88*zoom+pan,q.z*.12,1.); gl_PointSize=4.; }`
const fragment = `precision mediump float; void main(){ float d=length(gl_PointCoord*2.-1.); if(d>1.) discard; gl_FragColor=vec4(.47,.72,.95,.78); }`

function shader(gl: WebGLRenderingContext, type: number, source: string) {
  const value = gl.createShader(type)!
  gl.shaderSource(value, source)
  gl.compileShader(value)
  if (!gl.getShaderParameter(value, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(value) || 'shader compilation failed')
  return value
}

export function mountMapRenderer(canvas: HTMLCanvasElement, data: MapData): MapRenderer {
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
  const flat = gl.getUniformLocation(program, 'flat')
  const zoom = gl.getUniformLocation(program, 'zoom')
  const pan = gl.getUniformLocation(program, 'pan')
  let view: 'all' | 'content' = 'all'
  let isFlat = location.hash === '#2d'
  let frame = 0
  let scale = 1
  let offset: [number, number] = [0, 0]
  let drag: { x: number; y: number } | undefined

  const resize = () => { const ratio = Math.min(devicePixelRatio || 1, 2); canvas.width = innerWidth * ratio; canvas.height = innerHeight * ratio; canvas.style.width = `${innerWidth}px`; canvas.style.height = `${innerHeight}px`; gl.viewport(0, 0, canvas.width, canvas.height) }
  const draw = () => {
    const points = data.points.flatMap((point) => {
      if (view === 'content' && !point.c3) return []
      const position = isFlat
        ? view === 'content' ? [point.cx ?? point.x, point.cy ?? point.y, 0] : [point.x, point.y, 0]
        : view === 'content' && point.c3 ? point.c3 : point.z3
      return position
    })
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.STATIC_DRAW)
    gl.enableVertexAttribArray(position)
    gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 0, 0)
    gl.clearColor(0, 0, 0, 1)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.uniform1f(flat, isFlat ? 1 : 0)
    gl.uniform1f(zoom, scale)
    gl.uniform2f(pan, offset[0], offset[1])
    gl.drawArrays(gl.POINTS, 0, points.length / 3)
  }
  const render = () => { draw(); frame = requestAnimationFrame(render) }
  const down = (event: MouseEvent) => { drag = { x: event.clientX, y: event.clientY }; canvas.classList.add('dragging') }
  const move = (event: MouseEvent) => { if (!drag) return; offset = [offset[0] + (event.clientX - drag.x) / innerWidth * 2, offset[1] - (event.clientY - drag.y) / innerHeight * 2]; drag = { x: event.clientX, y: event.clientY } }
  const up = () => { drag = undefined; canvas.classList.remove('dragging') }
  const wheel = (event: WheelEvent) => { event.preventDefault(); scale = Math.max(.3, Math.min(12, scale * Math.exp(-event.deltaY * .0012))) }
  resize(); addEventListener('resize', resize); canvas.addEventListener('mousedown', down); addEventListener('mousemove', move); addEventListener('mouseup', up); canvas.addEventListener('wheel', wheel, { passive: false }); render()
  return { setView: (next) => { view = next }, setDimension: (next) => { isFlat = next }, destroy: () => { cancelAnimationFrame(frame); removeEventListener('resize', resize); canvas.removeEventListener('mousedown', down); removeEventListener('mousemove', move); removeEventListener('mouseup', up); canvas.removeEventListener('wheel', wheel); gl.deleteBuffer(buffer); gl.deleteProgram(program) } }
}
