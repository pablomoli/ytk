// PROTOTYPE (grove workshop) - the page where we develop and iterate tree
// generation. Foliage won the look bake-off (2026-07-12); the variant
// switcher is gone. Generation knobs persist to localStorage.
import { useEffect, useRef, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { HubControls } from '../components/HubControls'
import { fetchGrovePayload } from '../lib/grove/datatree'
import type { GrovePayload } from '../lib/grove/datatree'
import { DEFAULT_PARAMS } from '../lib/grove/tree'
import type { GroveParams } from '../lib/grove/tree'
import type { GroveHandle } from '../lib/grove/scene'
import '../styles.css'

const STORAGE = 'grove-params-v1'
const DATA_MODE = 'grove-data-mode-v1'

const loadParams = (): GroveParams => {
  try { return { ...DEFAULT_PARAMS, ...JSON.parse(localStorage.getItem(STORAGE) ?? '{}') } } catch { return DEFAULT_PARAMS }
}

export const Route = createFileRoute('/grove')({
  component: GrovePage,
})

const KNOBS: Array<{ key: keyof GroveParams; label: string; min: number; max: number; step: number }> = [
  { key: 'trees', label: 'trees', min: 1, max: 5, step: 1 },
  { key: 'initialChildren', label: 'first limbs', min: 1, max: 4, step: 1 },
  { key: 'branchChance', label: 'branching', min: 0, max: 0.7, step: 0.05 },
  { key: 'stepScale', label: 'step', min: 0.25, max: 1.2, step: 0.05 },
  { key: 'noise', label: 'noise', min: 0, max: 0.6, step: 0.02 },
  { key: 'reach', label: 'reach', min: 1.5, max: 6, step: 0.1 },
  { key: 'upBias', label: 'up bias', min: 0, max: 1, step: 0.05 },
  { key: 'girth', label: 'girth', min: 0.02, max: 0.2, step: 0.01 },
  { key: 'girthDecay', label: 'taper', min: 0.6, max: 0.97, step: 0.01 },
  { key: 'stiffness', label: 'stiffness', min: 0, max: 0.95, step: 0.05 },
  { key: 'wind', label: 'wind', min: 0, max: 1, step: 0.05 },
  { key: 'ringSegments', label: 'ring verts', min: 4, max: 12, step: 1 },
  { key: 'growSeconds', label: 'grow time', min: 1, max: 15, step: 0.5 },
  { key: 'leafDensity', label: 'leaf density', min: 0, max: 120, step: 2 },
  { key: 'leafSpread', label: 'leaf spread', min: 0.1, max: 0.9, step: 0.02 },
  { key: 'leafSize', label: 'leaf size', min: 0.5, max: 4, step: 0.1 },
]

function GrovePage() {
  const canvas = useRef<HTMLCanvasElement>(null)
  const handle = useRef<GroveHandle>(undefined)
  const [params, setParams] = useState<GroveParams>(loadParams)
  const [panelOpen, setPanelOpen] = useState(true)
  const [ready, setReady] = useState(false)
  const [payload, setPayload] = useState<GrovePayload | null>(null)
  const [dataMode, setDataMode] = useState(() => localStorage.getItem(DATA_MODE) === 'on')

  useEffect(() => {
    let alive = true
    // dynamic import keeps three out of every other route's bundle
    import('../lib/grove/scene').then((mod) => {
      if (!alive || !canvas.current) return
      handle.current = mod.mountGrove(canvas.current, loadParams(), 'foliage')
      setReady(true)
    })
    fetchGrovePayload().then((p) => { if (alive) setPayload(p) })
    return () => { alive = false; handle.current?.destroy(); handle.current = undefined }
    // mount once; params are pushed through the handle below
  }, [])
  // data mode: structure from bucket topology (/api/grove); aesthetic BFS
  // stays one click away — the calibrated look is never lost, only bypassed
  useEffect(() => {
    if (!ready) return
    handle.current?.setData(dataMode && payload ? payload : null)
  }, [dataMode, payload, ready])
  const regenTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const apply = (next: GroveParams) => {
    setParams(next)
    localStorage.setItem(STORAGE, JSON.stringify(next))
    // debounce: slider drags fire per pixel; regenerate once the hand settles
    clearTimeout(regenTimer.current)
    regenTimer.current = setTimeout(() => handle.current?.regenerate(next), 160)
  }
  const reseed = () => apply({ ...params, seed: Math.floor(Math.random() * 1e6) })

  return (
    <div className="grove-page">
      <HubControls>
        <button className="fchip" onClick={() => handle.current?.replay()}>replay growth</button>
        <button className="fchip" onClick={reseed}>reseed</button>
        {payload ? (
          <button
            className={`fchip${dataMode ? ' on' : ''}`}
            onClick={() => setDataMode((on) => { localStorage.setItem(DATA_MODE, on ? 'off' : 'on'); return !on })}
          >data trees</button>
        ) : null}
        <button className={`fchip${panelOpen ? ' on' : ''}`} onClick={() => setPanelOpen((open) => !open)}>knobs</button>
        <span className="count">{dataMode && payload ? `${payload.buckets.length} topics` : `seed ${params.seed}`}</span>
      </HubControls>
      <canvas ref={canvas} className="grove-canvas" />
      {panelOpen ? (
        <aside className="grove-panel">
          {KNOBS.map(({ key, label, min, max, step }) => (
            <label key={key}>
              <span>{label}</span>
              <input type="range" min={min} max={max} step={step} value={params[key]} onChange={(event) => apply({ ...params, [key]: Number(event.target.value) })} />
              <em>{params[key]}</em>
            </label>
          ))}
        </aside>
      ) : null}
    </div>
  )
}
