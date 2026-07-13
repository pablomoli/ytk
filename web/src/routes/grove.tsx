// PROTOTYPE (grove workshop) - the page where we develop and iterate tree
// generation. Foliage won the look bake-off (2026-07-12); the variant
// switcher is gone. Generation knobs persist to localStorage.
import { useEffect, useRef, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { HubControls } from '../components/HubControls'
import { fetchGrovePayload } from '../lib/grove/datatree'
import type { GrovePayload, TopoNode } from '../lib/grove/datatree'
import { DEFAULT_PARAMS } from '../lib/grove/tree'
import type { GroveParams } from '../lib/grove/tree'
import type { GroveHandle } from '../lib/grove/scene'
import '../styles.css'

const STORAGE = 'grove-params-v1'
const DATA_MODE = 'grove-data-mode-v1'

const loadParams = (): GroveParams => {
  try { return { ...DEFAULT_PARAMS, ...JSON.parse(localStorage.getItem(STORAGE) ?? '{}') } } catch { return DEFAULT_PARAMS }
}

type GroveSearch = { readback?: boolean }

export const Route = createFileRoute('/grove')({
  validateSearch: (search: Record<string, unknown>): GroveSearch =>
    search.readback ? { readback: true } : {},
  component: GroveRoute,
})

function GroveRoute() {
  const { readback } = Route.useSearch()
  return readback ? <ReadbackPage /> : <GrovePage />
}

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

// ---------------------------------------------------------------------------
// E7 readback (preregistered protocol, docs/grove-lab/e7-preregistration.md).
// The manifest arrives with truth stripped; responses are appended raw and
// correctness is never shown. Inline styles on purpose - trial UI, not product.
// ---------------------------------------------------------------------------

type E7Stimulus = { id: string; nodes: TopoNode[]; n_notes: number; render_seed: number }
type E7Trial = {
  trial: string; task: string; prompt: string; bucket: string | null
  left?: string; right?: string; anchor?: string; single?: string; options?: string[]
}
type E7Manifest = { sha256: string; stimuli: E7Stimulus[]; trials: E7Trial[] }

function StimulusCanvas({ stim, height }: { stim: E7Stimulus; height: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    let handle: GroveHandle | undefined
    let alive = true
    import('../lib/grove/scene').then((mod) => {
      if (!alive || !ref.current) return
      // fixed neutral preset; render_seed doubles as azimuth randomization.
      // single-bucket payloads are scale-normalized + identically tinted by
      // construction (preregistration amendment 1)
      handle = mod.mountGrove(ref.current, { ...DEFAULT_PARAMS, seed: stim.render_seed, growSeconds: 0.8, wind: 0.2 }, 'foliage')
      handle.setData({ version: 1, buckets: [{ bucket: stim.id, n_notes: stim.n_notes, nodes: stim.nodes }] })
    })
    return () => { alive = false; handle?.destroy() }
  }, [stim.id])
  return <canvas ref={ref} style={{ width: '100%', height, display: 'block', borderRadius: 8, background: '#0a0a0c' }} />
}

const chip: React.CSSProperties = { padding: '10px 22px', borderRadius: 20, border: '1px solid #4a4438', background: '#1a1a19', color: '#e2b04a', cursor: 'pointer', fontSize: 15 }

function ReadbackPage() {
  const [manifest, setManifest] = useState<E7Manifest | null>(null)
  const [error, setError] = useState('')
  const [index, setIndex] = useState(0)
  const [choice, setChoice] = useState<string | null>(null)
  const shownAt = useRef(0)
  const rt = useRef(0)

  useEffect(() => {
    fetch('/api/grove/e7')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(setManifest)
      .catch(() => setError('no manifest - run scripts.grove_lab.e7_manifest first'))
  }, [])
  useEffect(() => { shownAt.current = performance.now(); setChoice(null) }, [index])

  if (error) return <div style={{ padding: 40, color: '#c3c2b7' }}>{error}</div>
  if (!manifest) return <div style={{ padding: 40, color: '#c3c2b7' }}>loading manifest...</div>
  if (index >= manifest.trials.length) {
    return <div style={{ padding: 40, color: '#c3c2b7', fontSize: 18 }}>
      done - {manifest.trials.length} trials logged. thank you, subject.
    </div>
  }

  const trial = manifest.trials[index]
  const stim = (id?: string) => manifest.stimuli.find((s) => s.id === id)!
  const pick = (c: string) => { rt.current = Math.round(performance.now() - shownAt.current); setChoice(c) }
  const submit = (confidence: number) => {
    fetch('/api/grove/e7/response', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trial: trial.trial, choice: choice, confidence, rt_ms: rt.current }),
    }).finally(() => setIndex((i) => i + 1))
  }
  const isPair = trial.task !== 'identification-exploratory'
  const twoHigh = trial.task === 'topology-invariance' ? '34vh' : '56vh'

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0c', padding: '18px 26px', fontFamily: 'inherit' }}>
      <div style={{ color: '#c3c2b7', marginBottom: 12, fontSize: 15 }}>
        trial {index + 1} / {manifest.trials.length}
        {trial.task === 'practice' ? ' - practice (not scored)' : ''} &middot; {trial.prompt}
      </div>
      {trial.anchor ? (
        <div style={{ marginBottom: 10 }}>
          <div style={{ color: '#52514e', fontSize: 12, marginBottom: 4 }}>anchor</div>
          <StimulusCanvas stim={stim(trial.anchor)} height="30vh" />
        </div>
      ) : null}
      {isPair ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          {(['left', 'right'] as const).map((side) => (
            <div key={`${trial.trial}-${side}`}>
              <StimulusCanvas stim={stim(trial[side])} height={twoHigh} />
              {choice === null ? (
                <button style={{ ...chip, marginTop: 10, width: '100%' }} onClick={() => pick(side)}>{side}</button>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div>
          <StimulusCanvas stim={stim(trial.single)} height="52vh" />
          {choice === null ? (
            <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
              {trial.options?.map((o) => (
                <button key={o} style={chip} onClick={() => pick(o)}>{o}</button>
              ))}
            </div>
          ) : null}
        </div>
      )}
      {choice !== null ? (
        <div style={{ marginTop: 16 }}>
          <span style={{ color: '#c3c2b7', marginRight: 12 }}>confidence:</span>
          {[1, 2, 3, 4, 5].map((c) => (
            <button key={c} style={{ ...chip, marginRight: 8 }} onClick={() => submit(c)}>{c}</button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
