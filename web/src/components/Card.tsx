import type { MouseEvent } from 'react'
import type { QueueItem } from '../api/queue'
import { sourceIcon } from './icons'

export function Card({ item, onOpen }: { item: QueueItem; onOpen: (i: QueueItem) => void }) {
  const handleClick = (e: MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('a')) return
    onOpen(item)
  }

  return (
    <div className="card" onClick={handleClick}>
      <img src={`/api/cover?u=${encodeURIComponent(item.url)}`} loading="lazy" alt="" />
      <div className="meta">
        <div className="title">{item.text || item.author || item.url}</div>
        <div className="sub">
          {sourceIcon(item.source)}
          <span data-testid="card-source">{item.source}</span>
        </div>
      </div>
    </div>
  )
}
