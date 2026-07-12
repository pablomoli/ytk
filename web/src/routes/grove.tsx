// PROTOTYPE (grove workshop) - the page where we develop and iterate tree
// generation; throwaway until a look wins a real spec. Three looks switchable
// via ?variant= and arrow keys; generation knobs persist to localStorage.
import { useEffect, useRef, useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { HubControls } from '../components/HubControls'
import { DEFAULT_PARAMS } from '../lib/grove/tree'
import type { GroveParams } from '../lib/grove/tree'
import type { GroveHandle, GroveLook } from '../lib/grove/scene'
import '../styles.css'

const STORAGE = 'grove-params-v1'
const LOOKS: GroveLook[] = ['tubes', 'wires', 'foliage']

const loadParams = (): GroveParams => {
  try { return { ...DEFAULT_PARAMS, ...JSON.parse(localStorage.getItem(STORAGE) ?? '{}') } } catch { return DEFAULT_PARAMS }
}

type GroveSearch = { variant?: GroveLook }

export const Route = createFileRoute('/grove')({
  validateSearch: (search: Record<string, unknown>): GroveSearch => (LOOKS.includes(search.variant as GroveLook) ? { variant: search.variant as GroveLook } : {}),
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
  const { variant = 'foliage' } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const canvas = useRef<HTMLCanvasElement>(null)
  const handle = useRef<GroveHandle>(undefined)
  const [params, setParams] = useState<GroveParams>(loadParams)
  const [panelOpen, setPanelOpen] = useState(true)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let alive = true
    // dynamic import keeps three out of every other route's bundle
    import('../lib/grove/scene').then((mod) => {
      if (!alive || !canvas.current) return
      handle.current = mod.mountGrove(canvas.current, loadParams(), variant)
      setReady(true)
    })
    return () => { alive = false; handle.current?.destroy(); handle.current = undefined }
    // mount once; look and params are pushed through the handle below
  }, [])
  useEffect(() => { handle.current?.setLook(variant) }, [variant, ready])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        const delta = event.key === 'ArrowLeft' ? -1 : 1
        const next = LOOKS[(LOOKS.indexOf(variant) + delta + LOOKS.length) % LOOKS.length]
        navigate({ search: { variant: next }, replace: true })
      }
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [variant, navigate])

  const regenTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const apply = (next: GroveParams) => {
    setParams(next)
    localStorage.setItem(STORAGE, JSON.stringify(next))
    // debounce: slider drags fire per pixel; regenerate once the hand settles
    clearTimeout(regenTimer.current)
    regenTimer.current = setTimeout(() => handle.current?.regenerate(next), 160)
  }
  const reseed = () => apply({ ...params, seed: Math.floor(Math.random() * 1e6) })
  const cycle = (delta: number) => navigate({ search: { variant: LOOKS[(LOOKS.indexOf(variant) + delta + LOOKS.length) % LOOKS.length] }, replace: true })

  return (
    <div className="grove-page">
      <HubControls>
        <button className="fchip" onClick={() => handle.current?.replay()}>replay growth</button>
        <button className="fchip" onClick={reseed}>reseed</button>
        <button className={`fchip${panelOpen ? ' on' : ''}`} onClick={() => setPanelOpen((open) => !open)}>knobs</button>
        <span className="count">seed {params.seed}</span>
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
      <div className="grove-switcher">
        <button onClick={() => cycle(-1)} aria-label="Previous look">&#8592;</button>
        <span>PROTOTYPE &middot; {variant}</span>
        <button onClick={() => cycle(1)} aria-label="Next look">&#8594;</button>
      </div>
    </div>
  )
}
