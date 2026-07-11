import { createFileRoute } from '@tanstack/react-router'
import { useMap } from '../api/map'
import { ErrorState } from '../components/StateViews'
import '../styles.css'

export const Route = createFileRoute('/map')({ component: MapPage })

function MapPage() {
  const map = useMap()
  if (map.isLoading) return <div className="map-state">loading map...</div>
  if (map.isError) return <div className="map-state"><ErrorState error={map.error} /></div>
  return (
    <div className="map-page">
      <header className="map-header"><span>map</span><span>{map.data?.points.length ?? 0} notes</span></header>
      <div className="map-stage" aria-label="Knowledge map renderer" />
    </div>
  )
}
