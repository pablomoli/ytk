import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useMap, isMapV2 } from '../api/map'
import { ErrorState } from '../components/StateViews'
import { mapGroupColor, mountMapRenderer } from '../lib/mapRenderer'
import type { MapHover } from '../lib/mapRenderer'
import { HubControls } from '../components/HubControls'
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
  const leaders = useRef<SVGSVGElement>(null)
  const [view, setView] = useState<'all' | 'content'>(location.hash === '#content' ? 'content' : 'all')
  const [flat, setFlat] = useState(location.hash === '#2d')
  const [signal, setSignal] = useState(false)
  const [recent, setRecent] = useState(false)
  const [hover, setHover] = useState<MapHover>()
  const [focus, setFocus] = useState<number>()
  const [hoverGroupIndex, setHoverGroupIndex] = useState<number>()
  const [hidden, setHidden] = useState<Set<number>>(new Set())
  const [legendOpen, setLegendOpen] = useState(true)
  const renderer = useRef<ReturnType<typeof mountMapRenderer> | undefined>(undefined)
  useEffect(() => {
    if (!map.data || !canvas.current) return
    renderer.current = mountMapRenderer(canvas.current, map.data, setHover, labels.current ?? undefined, setFocus, leaders.current ?? undefined)
    return () => renderer.current?.destroy()
  }, [map.data])
  useEffect(() => { renderer.current?.setView(view) }, [view])
  useEffect(() => { renderer.current?.setDimension(flat) }, [flat])
  useEffect(() => { renderer.current?.setFilters(signal, recent) }, [signal, recent])
  useEffect(() => { renderer.current?.setGroupFocus(focus) }, [focus])
  useEffect(() => { renderer.current?.setGroupHover(hoverGroupIndex) }, [hoverGroupIndex])
  useEffect(() => { renderer.current?.setHiddenGroups(hidden) }, [hidden])
  useEffect(() => { renderer.current?.setLegendOpen(legendOpen) }, [legendOpen])
  if (map.isLoading) return <div className="map-state">loading map...</div>
  if (map.isError) return <div className="map-state"><ErrorState error={map.error} /></div>
  if (map.data && !isMapV2(map.data)) return <div className="map-state">map data predates the domain hierarchy - run `uv run python scripts/build_map.py`</div>
  const hoverGroup = hover ? (view === 'content' ? map.data!.content.groups[hover.point.th ?? -1]?.label : map.data!.all.groups[hover.point.g]?.label) || 'dust' : ''
  const layout = view === 'content' ? map.data!.content : map.data!.all
  const visibleNotes = view === 'content' ? map.data!.points.filter((point) => point.c3).length : map.data!.points.length
  const trust = layout.params.trustworthiness_3d ?? layout.params.trustworthiness
  return (
    <div className="map-page">
      <HubControls><button className={`fchip${view === 'all' ? ' on' : ''}`} onClick={() => { setView('all'); setFocus(undefined); setHidden(new Set()); setHoverGroupIndex(undefined) }}>everything</button><button className={`fchip${view === 'content' ? ' on' : ''}`} onClick={() => { setView('content'); setFocus(undefined); setHidden(new Set()); setHoverGroupIndex(undefined) }}>content</button><button className={`fchip${signal ? ' on' : ''}`} onClick={() => setSignal((current) => !current)}>signal</button><button className={`fchip${recent ? ' on' : ''}`} onClick={() => setRecent((current) => !current)}>recent</button><button className="fchip" onClick={() => setFlat((current) => !current)}>{flat ? '3d' : '2d'}</button><span className="count">{map.data?.points.length ?? 0} notes</span></HubControls>
      <div className="map-stage" aria-label="Knowledge map renderer"><canvas ref={canvas} /><svg ref={leaders} className="map-leaders" /><div ref={labels} className="map-labels" />
        <aside className={`map-legend${legendOpen ? '' : ' collapsed'}`}><button className="map-legend-toggle" onClick={() => setLegendOpen((open) => !open)} aria-label={legendOpen ? 'Collapse cluster legend' : 'Expand cluster legend'}>{legendOpen ? '›' : '‹'}</button>{legendOpen ? <>{layout.groups.map((group, index) => group.n ? <button key={index} className={hidden.has(index) || focus !== undefined && focus !== index ? 'off' : ''} onMouseEnter={() => setHoverGroupIndex(index)} onMouseLeave={() => setHoverGroupIndex(undefined)} onClick={(event) => { if (event.altKey) setHidden((current) => { const next = new Set(current); if (next.has(index)) next.delete(index); else next.add(index); return next }); else setFocus((current) => current === index ? undefined : index) }}><i style={{ background: mapGroupColor(map.data!, view, index) }} />{group.label}<span>{group.n}</span></button> : null)}<footer>{visibleNotes} notes · trust {trust?.toFixed(2) ?? 'n/a'} · sil {layout.params.silhouette?.toFixed(2) ?? 'n/a'}<br />drag orbit · right-drag pan · scroll zoom</footer></> : <div className="map-legend-dots">{layout.groups.filter((group) => group.n).sort((a, b) => b.n - a.n).slice(0, 10).map((group) => { const index = layout.groups.indexOf(group); return <i key={index} style={{ background: mapGroupColor(map.data!, view, index) }} /> })}</div>}</aside>
        {hover ? <MapTooltip hover={hover} group={hoverGroup} /> : null}
      </div>
    </div>
  )
}
