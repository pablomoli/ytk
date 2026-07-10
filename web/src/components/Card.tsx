import { useState } from 'react'
import type { MouseEvent } from 'react'
import type { QueueItem } from '../api/queue'
import { sourceIcon } from './icons'

type ImageStage = 'cover' | 'preview' | 'fallback'

export function Card({ item, onOpen }: { item: QueueItem; onOpen: (i: QueueItem) => void }) {
  const [stage, setStage] = useState<ImageStage>('cover')

  const handleClick = (e: MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('a')) return
    onOpen(item)
  }

  const handleImageError = () => {
    if (stage === 'cover') {
      setStage(item.preview_url ? 'preview' : 'fallback')
    } else if (stage === 'preview') {
      setStage('fallback')
    }
  }

  if (item.source === 'imessage') {
    return (
      <div className="card" onClick={handleClick}>
        <div className="textcard">
          <p>{item.text}</p>
          <span>{item.author}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="card" onClick={handleClick}>
      {stage === 'fallback' ? (
        <div className="noimg">{item.source}</div>
      ) : (
        <img
          src={stage === 'preview' ? item.preview_url : `/api/cover?u=${encodeURIComponent(item.url)}`}
          loading="lazy"
          alt=""
          onError={handleImageError}
        />
      )}
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
