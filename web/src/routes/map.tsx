import { useEffect, useRef, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useMap } from '../api/map'
import { ErrorState } from '../components/StateViews'
import { mountMapRenderer } from '../lib/mapRenderer'
import '../styles.css'

export const Route = createFileRoute('/map')({ component: MapPage })

function MapPage() {
  const map = useMap()
  const canvas = useRef<HTMLCanvasElement>(null)
  const [view, setView] = useState<'all' | 'content'>(location.hash === '#content' ? 'content' : 'all')
  const [flat, setFlat] = useState(location.hash === '#2d')
  const renderer = useRef<ReturnType<typeof mountMapRenderer>>()
  useEffect(() => {
    if (!map.data || !canvas.current) return
    renderer.current = mountMapRenderer(canvas.current, map.data)
    return () => renderer.current?.destroy()
  }, [map.data])
  useEffect(() => { renderer.current?.setView(view) }, [view])
  useEffect(() => { renderer.current?.setDimension(flat) }, [flat])
  if (map.isLoading) return <div className="map-state">loading map...</div>
  if (map.isError) return <div className="map-state"><ErrorState error={map.error} /></div>
  return (
    <div className="map-page">
      <header className="map-header"><span>map</span><button className={`fchip${view === 'all' ? ' on' : ''}`} onClick={() => setView('all')}>everything</button><button className={`fchip${view === 'content' ? ' on' : ''}`} onClick={() => setView('content')}>content</button><button className="fchip" onClick={() => setFlat((current) => !current)}>{flat ? '3d' : '2d'}</button><span>{map.data?.points.length ?? 0} notes</span></header>
      <div className="map-stage" aria-label="Knowledge map renderer"><canvas ref={canvas} /></div>
    </div>
  )
}
