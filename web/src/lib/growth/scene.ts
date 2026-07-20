import {
  ClampToEdgeWrapping,
  Color,
  DataTexture,
  FloatType,
  HalfFloatType,
  LinearFilter,
  Mesh,
  OrthographicCamera,
  PlaneGeometry,
  RGBAFormat,
  Scene,
  ShaderMaterial,
  Vector2,
  Vector3,
  WebGLRenderer,
  WebGLRenderTarget,
} from 'three'
import { DEFAULT_CONSTRAINTS, dnaToRD, type Constraints, type SeedDNA } from './dna'
import { generateTopology, type TopologyNode } from './topology'
import { workbenchRegions, type Region } from './layout'
import { growthRenderFragment, growthUpdateFragment, growthVertex } from './shaders'

export type GrowthKind = 'related' | 'novel'
export type EventInput = { stem: string; title: string; kind: GrowthKind }
export type OrganismSpec = {
  dna: SeedDNA
  events: EventInput[]
  replayFrom?: number
  constraints?: Constraints
}
export type WorkbenchStatus = {
  themeId: string | null
  replayed: number
  total: number
  phase: 'resting' | 'growing' | 'paused'
  message: string
}
export type WorkbenchHandle = {
  setOrganism(spec: OrganismSpec): void
  setMutations(dnas: SeedDNA[]): void
  setAbstraction(v: number): void
  setPaused(p: boolean): void
  injectDebug(kind: GrowthKind): void
  reset(): void
  snapshot(): string
  replayPosition(): number
  destroy(): void
}

type GrowthEvent = {
  kind: GrowthKind
  from: Vector2
  to: Vector2
  radius: number
  seed: number
  label: string
  counted: boolean
}

const STAGE_SIZE = 1024
const TILE_SIZE = 256
const EVENT_SECONDS = 0.9
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))
const fract = (v: number) => v - Math.floor(v)
const randomFrom = (seed: number) => fract(Math.sin(seed * 91.733) * 43758.5453123)

// Reaction-diffusion initial state: substrate A everywhere, droplets of
// pattern chemical B at the topology's asymmetric node positions. The RD
// dynamics immediately take over — the topology only biases where the
// organism starts, not what it looks like.
function makeSeedTexture(nodes: TopologyNode[], size: number) {
  const data = new Float32Array(size * size * 4)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const px = (x + 0.5) / size
      const py = (y + 0.5) / size
      let b = 0
      let domain = 0
      for (let index = 0; index < nodes.length; index++) {
        const node = nodes[index]
        const d = Math.hypot(px - node.x, py - node.y) / (node.radius * 0.5)
        b = Math.max(b, Math.exp(-d * d * 2.5))
        const dd = Math.hypot(px - node.x, py - node.y) / (node.radius * 1.6)
        const ragged = 0.8 + 0.4 * randomFrom(index * 3.1 + px * 17 + py * 29)
        domain = Math.max(domain, Math.exp(-dd * dd * 2.0) * ragged)
      }
      const offset = (y * size + x) * 4
      data[offset] = 1 - b * 0.5
      data[offset + 1] = b > 0.05 ? b : 0
      data[offset + 2] = 0
      data[offset + 3] = domain > 0.04 ? domain : 0
    }
  }
  const texture = new DataTexture(data, size, size, RGBAFormat, FloatType)
  texture.needsUpdate = true
  texture.minFilter = LinearFilter
  texture.magFilter = LinearFilter
  texture.wrapS = ClampToEdgeWrapping
  texture.wrapT = ClampToEdgeWrapping
  return texture
}

type Slot = {
  targets: [WebGLRenderTarget, WebGLRenderTarget]
  readIndex: number
  size: number
  dna: SeedDNA | null
}

function makeSlot(size: number): Slot {
  const options = {
    type: HalfFloatType,
    format: RGBAFormat,
    minFilter: LinearFilter,
    magFilter: LinearFilter,
    depthBuffer: false,
    stencilBuffer: false,
  }
  const targets: [WebGLRenderTarget, WebGLRenderTarget] = [
    new WebGLRenderTarget(size, size, options),
    new WebGLRenderTarget(size, size, options),
  ]
  for (const t of targets) {
    t.texture.wrapS = ClampToEdgeWrapping
    t.texture.wrapT = ClampToEdgeWrapping
  }
  return { targets, readIndex: 0, size, dna: null }
}

const opsA = (dna: SeedDNA) => new Vector3(dna.operators.DEEPEN, dna.operators.BUD, dna.operators.LACE)
const opsB = (dna: SeedDNA) => new Vector3(dna.operators.STIPPLE, dna.operators.BLEED, dna.operators.MEMBRANE)

export function mountWorkbench(
  canvas: HTMLCanvasElement,
  onStatus: (s: WorkbenchStatus) => void,
): WorkbenchHandle {
  const renderer = new WebGLRenderer({
    canvas,
    antialias: false,
    alpha: false,
    powerPreference: 'high-performance',
    preserveDrawingBuffer: true,
  })
  renderer.setClearColor(0x050607, 1)
  const camera = new OrthographicCamera(-1, 1, 1, -1, 0, 1)
  const geometry = new PlaneGeometry(2, 2)
  const simulationScene = new Scene()
  const displayScene = new Scene()

  const updateUniforms = {
    uState: { value: null as unknown as THREE_TEX },
    uTexel: { value: new Vector2(1 / STAGE_SIZE, 1 / STAGE_SIZE) },
    uFrom: { value: new Vector2(0.5, 0.5) },
    uTo: { value: new Vector2(0.5, 0.5) },
    uRadius: { value: 0.08 },
    uProgress: { value: 0 },
    uSeed: { value: 1 },
    uActive: { value: 0 },
    uCopy: { value: 1 },
    uFeed: { value: 0.03 },
    uKill: { value: 0.06 },
    uDiffA: { value: 1 },
    uDiffB: { value: 0.5 },
    uStipple: { value: 0.3 },
  }
  type THREE_TEX = WebGLRenderTarget['texture']
  const updateMaterial = new ShaderMaterial({
    vertexShader: growthVertex,
    fragmentShader: growthUpdateFragment,
    uniforms: updateUniforms,
  })
  simulationScene.add(new Mesh(geometry, updateMaterial))

  const displayUniforms = {
    uState: { value: null as unknown as THREE_TEX },
    uTexel: { value: new Vector2(1 / STAGE_SIZE, 1 / STAGE_SIZE) },
    uTime: { value: 0 },
    uAspect: { value: 1 },
    uPulse: { value: 0 },
    uPalette0: { value: new Color('#1a1d24') },
    uPalette1: { value: new Color('#3d4455') },
    uPalette2: { value: new Color('#7c8499') },
    uPalette3: { value: new Color('#c7ccd9') },
    uPalette4: { value: new Color('#e8e4d8') },
    uOpsA: { value: new Vector3(0.5, 0.5, 0.5) },
    uOpsB: { value: new Vector3(0.5, 0.5, 0.5) },
    uGlowMax: { value: DEFAULT_CONSTRAINTS.glow_max },
    uAbstraction: { value: 0 },
    uMini: { value: 0 },
  }
  const displayMaterial = new ShaderMaterial({
    vertexShader: growthVertex,
    fragmentShader: growthRenderFragment,
    uniforms: displayUniforms,
  })
  displayScene.add(new Mesh(geometry, displayMaterial))

  const stage = makeSlot(STAGE_SIZE)
  const tiles = [makeSlot(TILE_SIZE), makeSlot(TILE_SIZE), makeSlot(TILE_SIZE), makeSlot(TILE_SIZE)]
  const slots = [stage, ...tiles]

  let spec: OrganismSpec | null = null
  let constraints = DEFAULT_CONSTRAINTS
  let nodes: TopologyNode[] = []
  let seedTexture: DataTexture | null = null
  let tileSeedTexture: DataTexture | null = null
  let queue: GrowthEvent[] = []
  let current: GrowthEvent | null = null
  let eventElapsed = 0
  let replayed = 0
  let total = 0
  let paused = false
  let destroyed = false
  let frame = 0
  let lastTime = performance.now()

  const setUpdateDNA = (dna: SeedDNA | null) => {
    if (!dna) return
    const rd = dnaToRD(dna)
    updateUniforms.uFeed.value = rd.feed
    updateUniforms.uKill.value = rd.kill
    updateUniforms.uDiffA.value = rd.diffA
    updateUniforms.uDiffB.value = rd.diffB
    updateUniforms.uStipple.value = dna.operators.STIPPLE
  }

  const setDisplayDNA = (dna: SeedDNA | null) => {
    if (!dna) return
    const p = dna.palette
    displayUniforms.uPalette0.value.set(p[0])
    displayUniforms.uPalette1.value.set(p[1])
    displayUniforms.uPalette2.value.set(p[2])
    displayUniforms.uPalette3.value.set(p[3])
    displayUniforms.uPalette4.value.set(p[4])
    displayUniforms.uOpsA.value.copy(opsA(dna))
    displayUniforms.uOpsB.value.copy(opsB(dna))
  }

  const simulateSlot = (slot: Slot, source: DataTexture | null = null) => {
    const writeIndex = 1 - slot.readIndex
    updateUniforms.uState.value = source ?? slot.targets[slot.readIndex].texture
    updateUniforms.uTexel.value.set(1 / slot.size, 1 / slot.size)
    setUpdateDNA(slot.dna)
    renderer.setRenderTarget(slot.targets[writeIndex])
    renderer.render(simulationScene, camera)
    renderer.setRenderTarget(null)
    slot.readIndex = writeIndex
  }

  const seedSlot = (slot: Slot) => {
    const source = slot.size === STAGE_SIZE ? seedTexture : tileSeedTexture
    if (!source) return
    updateUniforms.uCopy.value = 1
    slot.readIndex = 1
    simulateSlot(slot, source)
    updateUniforms.uCopy.value = 0
  }

  // Settled-event reconstruction: inject the droplet, then free-run the
  // reaction so the pattern absorbs it before the next event lands.
  const replayEventOnSlot = (slot: Slot, ev: GrowthEvent, settleSteps = 24) => {
    updateUniforms.uFrom.value.copy(ev.from)
    updateUniforms.uTo.value.copy(ev.to)
    updateUniforms.uRadius.value = ev.radius
    updateUniforms.uSeed.value = ev.seed
    updateUniforms.uActive.value = 1
    for (const progress of [0.6, 1]) {
      updateUniforms.uProgress.value = progress
      simulateSlot(slot)
    }
    updateUniforms.uActive.value = 0
    for (let i = 0; i < settleSteps; i++) simulateSlot(slot)
  }

  const history: GrowthEvent[] = []

  const catchUpTiles = () => {
    for (const tile of tiles) {
      seedSlot(tile)
      for (const ev of history) replayEventOnSlot(tile, ev, 10)
    }
  }

  const emitStatus = (message: string) => {
    onStatus({
      themeId: spec?.dna.themeId ?? null,
      replayed,
      total,
      phase: paused ? 'paused' : current ? 'growing' : 'resting',
      message,
    })
  }

  const eventFor = (kind: GrowthKind, index: number, label: string): GrowthEvent => {
    const seed = 800 + index * 37 + (kind === 'novel' ? 17 : 0)
    const root = nodes[0] ?? { x: 0.5, y: 0.5, radius: 0.1, parent: -1 }
    let parentIndex: number
    let angle: number
    let distance: number
    if (kind === 'related' && nodes.length > 1) {
      parentIndex = 1 + Math.floor(randomFrom(seed) * (nodes.length - 1))
      angle = randomFrom(seed + 3) * Math.PI * 2
      distance = 0.07 + randomFrom(seed + 5) * 0.06
    } else {
      parentIndex = nodes.reduce((best, node, i) => {
        const r = Math.hypot(node.x - root.x, node.y - root.y)
        const bestR = Math.hypot(nodes[best].x - root.x, nodes[best].y - root.y)
        return r > bestR ? i : best
      }, 0)
      const parent = nodes[parentIndex]
      angle = Math.atan2(parent.y - root.y, parent.x - root.x) + (randomFrom(seed + 7) - 0.5) * 0.9
      distance = 0.12 + randomFrom(seed + 11) * 0.08
    }
    const parent = nodes[parentIndex]
    // Keep droplets within the organism's reach: growth stays one specimen,
    // never a scatter across the whole field.
    const cx = nodes.reduce((s, n) => s + n.x, 0) / nodes.length
    const cy = nodes.reduce((s, n) => s + n.y, 0) / nodes.length
    let tx = parent.x + Math.cos(angle) * distance
    let ty = parent.y + Math.sin(angle) * distance
    const spread = Math.hypot(tx - cx, ty - cy)
    const maxSpread = 0.3
    if (spread > maxSpread) {
      tx = cx + ((tx - cx) / spread) * maxSpread
      ty = cy + ((ty - cy) / spread) * maxSpread
    }
    const to = new Vector2(clamp(tx, 0.08, 0.92), clamp(ty, 0.08, 0.92))
    return {
      kind,
      from: new Vector2(parent.x, parent.y),
      to,
      radius:
        kind === 'novel'
          ? 0.075 + randomFrom(seed + 13) * 0.025
          : 0.05 + randomFrom(seed + 13) * 0.02,
      seed,
      label,
      counted: true,
    }
  }

  const rebuildQueue = () => {
    if (!spec) return
    queue = spec.events
      .slice(replayed)
      .map((e, i) => eventFor(e.kind, replayed + i, `${e.kind} · ${e.title.slice(0, 60)}`))
  }

  const startNext = () => {
    if (current || !queue.length || paused) return
    current = queue.shift()!
    eventElapsed = 0
    updateUniforms.uFrom.value.copy(current.from)
    updateUniforms.uTo.value.copy(current.to)
    updateUniforms.uRadius.value = current.radius
    updateUniforms.uSeed.value = current.seed
    updateUniforms.uActive.value = 1
    emitStatus(current.label)
  }

  let regions: { stage: Region; mutations: Region[] } = workbenchRegions(1, 1)
  const resize = () => {
    const width = canvas.clientWidth || innerWidth
    const height = canvas.clientHeight || innerHeight
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2))
    renderer.setSize(width, height, false)
    regions = workbenchRegions(width, height)
  }

  const drawRegion = (slot: Slot, region: Region, height: number, pulse: number) => {
    if (!slot.dna) return
    setDisplayDNA(slot.dna)
    displayUniforms.uState.value = slot.targets[slot.readIndex].texture
    displayUniforms.uTexel.value.set(1 / slot.size, 1 / slot.size)
    displayUniforms.uAspect.value = region.w / Math.max(1, region.h)
    displayUniforms.uMini.value = slot.size === STAGE_SIZE ? 0 : 1
    displayUniforms.uPulse.value = pulse
    const glY = height - (region.y + region.h)
    renderer.setViewport(region.x, glY, region.w, region.h)
    renderer.setScissor(region.x, glY, region.w, region.h)
    renderer.render(displayScene, camera)
  }

  const render = (now: number) => {
    if (destroyed) return
    const dt = Math.min(0.05, Math.max(0.001, (now - lastTime) / 1000))
    lastTime = now
    let pulse = 0
    if (!paused && spec) {
      displayUniforms.uTime.value += dt
      startNext()
      if (current) {
        eventElapsed += dt
        const progress = Math.min(1, eventElapsed / EVENT_SECONDS)
        updateUniforms.uProgress.value = progress
        updateUniforms.uActive.value = 1
        pulse = Math.sin(progress * Math.PI)
        emitStatus(current.label)
        if (progress >= 1) {
          nodes.push({
            x: current.to.x,
            y: current.to.y,
            radius: current.radius,
            parent: 0,
          })
          history.push(current)
          if (current.counted) replayed++
          const done = current
          current = null
          updateUniforms.uActive.value = 0
          emitStatus(`${done.kind} settled`)
        }
      }
      // The reaction runs every frame, event or not — the organism is alive.
      // Each slot advances by its own DNA's step count; the active droplet
      // (if any) injects during the same passes.
      for (const slot of slots) {
        if (!slot.dna) continue
        const steps = slot === stage ? dnaToRD(slot.dna).steps : Math.min(6, dnaToRD(slot.dna).steps)
        for (let i = 0; i < steps; i++) simulateSlot(slot)
      }
    }
    const height = canvas.clientHeight || innerHeight
    renderer.setScissorTest(true)
    drawRegion(stage, regions.stage, height, pulse)
    tiles.forEach((tile, i) => drawRegion(tile, regions.mutations[i], height, pulse))
    renderer.setScissorTest(false)
    frame = requestAnimationFrame(render)
  }

  resize()
  addEventListener('resize', resize)
  frame = requestAnimationFrame(render)

  return {
    setOrganism(next) {
      spec = next
      constraints = next.constraints ?? DEFAULT_CONSTRAINTS
      replayed = Math.min(next.replayFrom ?? 0, next.events.length)
      total = next.events.length
      current = null
      history.length = 0
      nodes = generateTopology(next.dna.themeId, next.dna.params, constraints)
      seedTexture?.dispose()
      tileSeedTexture?.dispose()
      seedTexture = makeSeedTexture(nodes, STAGE_SIZE)
      tileSeedTexture = makeSeedTexture(nodes, TILE_SIZE)
      stage.dna = next.dna
      seedSlot(stage)
      // Already-replayed events settle instantly; only the remainder animates.
      const settled = next.events
        .slice(0, replayed)
        .map((e, i) => eventFor(e.kind, i, e.title))
      for (const ev of settled) {
        replayEventOnSlot(stage, ev)
        nodes.push({ x: ev.to.x, y: ev.to.y, radius: ev.radius, parent: 0 })
        history.push(ev)
      }
      for (const tile of tiles) {
        if (!tile.dna) tile.dna = next.dna
      }
      catchUpTiles()
      rebuildQueue()
      emitStatus(`organism loaded · ${replayed}/${total} notes settled`)
    },
    setMutations(dnas) {
      tiles.forEach((tile, i) => {
        tile.dna = dnas[i] ?? tile.dna
      })
      catchUpTiles()
    },
    setAbstraction(v) {
      displayUniforms.uAbstraction.value = clamp(v, 0, 1)
    },
    setPaused(p) {
      paused = p
      emitStatus(p ? 'paused' : 'resumed')
    },
    injectDebug(kind) {
      const ev = eventFor(kind, 900 + history.length, `debug ${kind}`)
      ev.counted = false
      queue.unshift(ev)
      startNext()
    },
    reset() {
      if (!spec) return
      replayed = 0
      this.setOrganism({ ...spec, replayFrom: 0 })
    },
    snapshot() {
      // Crop the main dish (centered circle, radius 0.42 of region height).
      const region = regions.stage
      const scale = Math.min(devicePixelRatio || 1, 2)
      const side = region.h * 0.9 * scale
      const sx = (region.w * scale - side) / 2
      const sy = (region.h * scale - side) / 2
      const out = document.createElement('canvas')
      out.width = 128
      out.height = 128
      const ctx = out.getContext('2d')
      if (ctx) ctx.drawImage(canvas, sx, sy, side, side, 0, 0, 128, 128)
      return out.toDataURL('image/png')
    },
    replayPosition() {
      return replayed
    },
    destroy() {
      destroyed = true
      cancelAnimationFrame(frame)
      removeEventListener('resize', resize)
      seedTexture?.dispose()
      tileSeedTexture?.dispose()
      for (const slot of slots) slot.targets.forEach((t) => t.dispose())
      updateMaterial.dispose()
      displayMaterial.dispose()
      geometry.dispose()
      renderer.dispose()
    },
  }
}
