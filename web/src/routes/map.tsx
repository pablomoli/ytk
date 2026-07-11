import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useMap } from '../api/map'
import { ErrorState } from '../components/StateViews'
import { mapGroupColor, mountMapRenderer } from '../lib/mapRenderer'
import type { MapHover } from '../lib/mapRenderer'
import '../styles.css'

export const Route = createFileRoute('/map')({ component: MapPage })

function MapTooltip({ hover, group }: { hover: MapHover; group: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ left: hover.x + 14, top: hover.y + 14 })
  useLayoutEffect(() => {
    const height = ref.current?.offsetHeight ?? 0
    setPosition({ left: Math.min(hover.x + 14, innerWidth - 320), top: Math.min(hover.y + 14, innerHeight - height - 16) })
  }, [hover])
  const signal = ['', 'saved', 'thought', 'directive'][hover.point.r] || ''
  return <div ref={ref} className="map-tip" style={position}>{hover.point.img && hover.point.u ? <img src={`/api/cover?u=${encodeURIComponent(hover.point.u)}`} alt="" /> : null}<div>{hover.point.t}</div><small>{hover.point.c} · {group}{signal ? ` · ${signal}` : ''}{hover.point.d ? ` · ${hover.point.d}` : ''}</small></div>
}

function MapPage() {
  const map = useMap()
  const canvas = useRef<HTMLCanvasElement>(null)
  const labels = useRef<HTMLDivElement>(null)
  const [view, setView] = useState<'all' | 'content'>(location.hash === '#content' ? 'content' : 'all')
  const [flat, setFlat] = useState(location.hash === '#2d')
  const [signal, setSignal] = useState(false)
  const [recent, setRecent] = useState(false)
  const [hover, setHover] = useState<MapHover>()
  const [focus, setFocus] = useState<number>()
  const renderer = useRef<ReturnType<typeof mountMapRenderer>>()
  useEffect(() => {
    if (!map.data || !canvas.current) return
    renderer.current = mountMapRenderer(canvas.current, map.data, setHover, labels.current ?? undefined)
    return () => renderer.current?.destroy()
  }, [map.data])
  useEffect(() => { renderer.current?.setView(view) }, [view])
  useEffect(() => { renderer.current?.setDimension(flat) }, [flat])
  useEffect(() => { renderer.current?.setFilters(signal, recent) }, [signal, recent])
  useEffect(() => { renderer.current?.setGroupFocus(focus) }, [focus])
  if (map.isLoading) return <div className="map-state">loading map...</div>
  if (map.isError) return <div className="map-state"><ErrorState error={map.error} /></div>
  const hoverGroup = hover ? (view === 'content' ? map.data!.content.groups[hover.point.th ?? -1]?.label : map.data!.all.groups[hover.point.g]?.label) || 'dust' : ''
  return (
    <div className="map-page">
      <header className="map-header"><span>map</span><button className={`fchip${view === 'all' ? ' on' : ''}`} onClick={() => { setView('all'); setFocus(undefined) }}>everything</button><button className={`fchip${view === 'content' ? ' on' : ''}`} onClick={() => { setView('content'); setFocus(undefined) }}>content</button><button className={`fchip${signal ? ' on' : ''}`} onClick={() => setSignal((current) => !current)}>signal</button><button className={`fchip${recent ? ' on' : ''}`} onClick={() => setRecent((current) => !current)}>recent</button><button className="fchip" onClick={() => setFlat((current) => !current)}>{flat ? '3d' : '2d'}</button><span>{map.data?.points.length ?? 0} notes</span></header>
      <div className="map-stage" aria-label="Knowledge map renderer"><canvas ref={canvas} /><div ref={labels} className="map-labels" />
        <aside className="map-legend">{(view === 'content' ? map.data!.content.groups : map.data!.all.groups).map((group, index) => group.n ? <button key={index} className={focus !== undefined && focus !== index ? 'off' : ''} onClick={() => setFocus((current) => current === index ? undefined : index)}><i style={{ background: mapGroupColor(map.data!, view, index) }} />{group.label}<span>{group.n}</span></button> : null)}</aside>
        {hover ? <MapTooltip hover={hover} group={hoverGroup} /> : null}
      </div>
    </div>
  )
}
